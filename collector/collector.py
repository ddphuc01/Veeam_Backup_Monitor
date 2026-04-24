#!/usr/bin/env python3
"""
Veeam Backup & Replication - Metrics Collector (FIXED)
Thu thập data từ Veeam REST API v1-rev1 và ghi vào InfluxDB
"""

import os
import time
import logging
import requests
import urllib3
from datetime import datetime, timezone
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# Tắt warning SSL (Veeam dùng self-signed cert)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ============================================================
# Config từ environment variables
# ============================================================
VEEAM_HOST = os.getenv("VEEAM_HOST", "https://192.168.4.2:9419")  # ← Cập nhật IP của bạn
VEEAM_USER = os.getenv("VEEAM_USER", "svc_veeam_monitor")
VEEAM_PASS = os.getenv("VEEAM_PASS", "")

INFLUX_URL = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG = os.getenv("INFLUX_ORG", "veeam-org")
INFLUX_BUCKET = os.getenv("INFLUX_BUCKET", "veeam")

COLLECT_INTERVAL = int(os.getenv("COLLECT_INTERVAL", "300"))

# ============================================================
# Logging
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/app/logs/collector.log"),
    ]
)
log = logging.getLogger(__name__)

# ============================================================
# Veeam API - FIXED ENDPOINTS
# ============================================================
class VeeamAPI:
    def __init__(self):
        self.token = None
        self.headers = {"x-api-version": "1.0-rev1"}
        self.session = requests.Session()
        self.session.verify = False

    def authenticate(self):
        # ✅ FIX: Dùng đúng endpoint oauth2
        url = f"{VEEAM_HOST}/api/oauth2/token"
        data = f"grant_type=password&username={VEEAM_USER}&password={VEEAM_PASS}"
        resp = self.session.post(
            url, 
            headers={**self.headers, "Content-Type": "application/x-www-form-urlencoded"}, 
            data=data
        )
        resp.raise_for_status()
        self.token = resp.json()["access_token"]
        self.headers["Authorization"] = f"Bearer {self.token}"
        log.info("✅ Đăng nhập Veeam API thành công")

    def get(self, path, params=None):
        # ✅ FIX: path đã bao gồm /api/v1/ từ caller
        url = f"{VEEAM_HOST}{path}"
        resp = self.session.get(url, headers=self.headers, params=params)
        if resp.status_code == 401:
            log.warning("Token hết hạn, đăng nhập lại...")
            self.authenticate()
            resp = self.session.get(url, headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def get_jobs(self):
        # ✅ FIX: Lấy Job States thay vì Jobs tĩnh để khai thác objectsCount
        return self.get("/api/v1/jobs/states").get("data", [])

    def get_sessions(self, limit=200):
        # ✅ FIX: /api/v1/sessions (không phải /jobSessions)
        return self.get("/api/v1/sessions", params={"limit": limit}).get("data", [])

    def get_repositories(self):
        # ✅ FIX: Lấy Repositories States
        return self.get("/api/v1/backupInfrastructure/repositories/states").get("data", [])

    def get_managed_servers(self):
        try:
            return self.get("/api/v1/backupInfrastructure/managedServers").get("data", [])
        except Exception:
            return []

    def get_proxies(self):
        try:
            return self.get("/api/v1/backupInfrastructure/proxies").get("data", [])
        except Exception:
            return []

# ============================================================
# InfluxDB Writer
# ============================================================
class InfluxWriter:
    def __init__(self):
        self.client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)

    def write(self, points):
        self.write_api.write(bucket=INFLUX_BUCKET, record=points)

    def close(self):
        self.client.close()

# ============================================================
# Metrics Builder
# ============================================================
STATUS_MAP = {
    "Success": 1, "Warning": 2, "Failed": 3, "Running": 0, "None": -1,
}

def build_job_points(jobs):
    points = []
    now = datetime.now(timezone.utc)
    for job in jobs:
        last_result = job.get("lastResult", "None")
        status = job.get("status", "unknown")
        objects_count = int(job.get("objectsCount", 0)) if job.get("objectsCount") else 0
        p = (
            Point("veeam_job")
            .tag("job_name", job.get("name", "unknown"))
            .tag("job_type", job.get("type", "unknown"))
            .tag("last_result", last_result)
            .tag("status", status)
            .field("is_enabled", 0 if status == "Disabled" else 1)
            .field("objects_count", objects_count)
            .field("status_code", STATUS_MAP.get(last_result, -1))
            .time(now)
        )
        points.append(p)
    return points

def build_session_points(sessions):
    points = []
    now = datetime.now(timezone.utc)
    for s in sessions:
        result_obj = s.get("result", {})
        status = result_obj.get("result", "None") if result_obj else "None"
        p = (
            Point("veeam_session")
            .tag("job_name", s.get("jobName", "unknown"))
            .tag("job_type", s.get("jobType", "unknown"))
            .tag("status", status)
            .field("status_code", STATUS_MAP.get(status, -1))
            .field("progress_percent", float(s.get("progressPercent", 0)))
            .field("is_retry", 1 if s.get("isRetry") else 0)
            .time(now)
        )
        points.append(p)
    return points

def build_repo_points(repos):
    points = []
    now = datetime.now(timezone.utc)
    for repo in repos:
        # repository/states đổi tên biến (bỏ hậu tố GB)
        capacity = repo.get("capacity", 0) or 0
        free_space = repo.get("freeSpace", 0) or 0
        used_space = repo.get("usedSpace", capacity - free_space)
        used_pct = round((used_space / capacity * 100), 2) if capacity > 0 else 0

        p = (
            Point("veeam_repository")
            .tag("repo_name", repo.get("name", "unknown"))
            .tag("repo_type", repo.get("type", "unknown"))
            .field("capacity_gb", float(capacity))
            .field("free_space_gb", float(free_space))
            .field("used_space_gb", float(used_space))
            .field("used_percent", float(used_pct))
            .time(now)
        )
        points.append(p)
    return points

def build_proxy_points(proxies):
    points = []
    now = datetime.now(timezone.utc)
    for px in proxies:
        p = (
            Point("veeam_proxy")
            .tag("proxy_name", px.get("name", "unknown"))
            .tag("proxy_type", px.get("type", "unknown"))
            .field("max_tasks", px.get("server", {}).get("maxTasksCount", 0) if px.get("server") else 0)
            .field("status_code", 1)  # Giả định tồn tại
            .time(now)
        )
        points.append(p)
    return points

def build_server_points(servers):
    points = []
    now = datetime.now(timezone.utc)
    for sv in servers:
        p = (
            Point("veeam_managed_server")
            .tag("server_name", sv.get("name", "unknown"))
            .tag("server_type", sv.get("type", "unknown"))
            .field("status_code", 1)
            .time(now)
        )
        points.append(p)
    return points

# ============================================================
# Main Loop
# ============================================================
def collect_once(veeam: VeeamAPI, writer: InfluxWriter):
    points = []

    try:
        jobs = veeam.get_jobs()
        points += build_job_points(jobs)
        log.info(f" 📋 Jobs: {len(jobs)}")
    except Exception as e:
        log.error(f"Lỗi lấy jobs: {e}")

    try:
        sessions = veeam.get_sessions()
        points += build_session_points(sessions)
        log.info(f" 📁 Sessions: {len(sessions)}")
    except Exception as e:
        log.error(f"Lỗi lấy sessions: {e}")

    try:
        repos = veeam.get_repositories()
        points += build_repo_points(repos)
        log.info(f" 🗄️ Repositories: {len(repos)}")
    except Exception as e:
        log.error(f"Lỗi lấy repositories: {e}")

    try:
        proxies = veeam.get_proxies()
        points += build_proxy_points(proxies)
        log.info(f" 🛡️ Backup Proxies: {len(proxies)}")
    except Exception as e:
        log.error(f"Lỗi lấy proxies: {e}")

    try:
        servers = veeam.get_managed_servers()
        points += build_server_points(servers)
        log.info(f" 🖥️ Managed Servers: {len(servers)}")
    except Exception as e:
        log.error(f"Lỗi lấy managed servers: {e}")

    if points:
        writer.write(points)
        log.info(f"✅ Đã ghi {len(points)} metrics vào InfluxDB")

def main():
    log.info("🚀 Veeam Collector khởi động...")
    log.info(f" Veeam Host : {VEEAM_HOST}")
    log.info(f" InfluxDB : {INFLUX_URL}")
    log.info(f" Interval : {COLLECT_INTERVAL}s")

    veeam = VeeamAPI()
    writer = InfluxWriter()

    # Đăng nhập lần đầu (retry nếu thất bại)
    while True:
        try:
            veeam.authenticate()
            break
        except Exception as e:
            log.error(f"Không thể đăng nhập Veeam: {e}. Thử lại sau 30s...")
            time.sleep(30)

    # Vòng lặp chính
    while True:
        try:
            log.info("🔄 Bắt đầu thu thập metrics...")
            collect_once(veeam, writer)
        except Exception as e:
            log.error(f"Lỗi trong vòng lặp chính: {e}")

        log.info(f"⏳ Chờ {COLLECT_INTERVAL}s...")
        time.sleep(COLLECT_INTERVAL)

if __name__ == "__main__":
    main()