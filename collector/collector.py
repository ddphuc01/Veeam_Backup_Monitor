#!/usr/bin/env python3
"""
Veeam Backup & Replication - Metrics Collector
Thu thập data từ Veeam REST API và ghi vào InfluxDB
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
VEEAM_HOST     = os.getenv("VEEAM_HOST", "https://192.168.1.10:9419")
VEEAM_USER     = os.getenv("VEEAM_USER", "Administrator")
VEEAM_PASS     = os.getenv("VEEAM_PASS", "password")

INFLUX_URL     = os.getenv("INFLUX_URL", "http://influxdb:8086")
INFLUX_TOKEN   = os.getenv("INFLUX_TOKEN", "")
INFLUX_ORG     = os.getenv("INFLUX_ORG", "veeam-org")
INFLUX_BUCKET  = os.getenv("INFLUX_BUCKET", "veeam")

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
# Veeam API
# ============================================================
class VeeamAPI:
    def __init__(self):
        self.token = None
        self.headers = {"x-api-version": "1.1"}
        self.session = requests.Session()
        self.session.verify = False

    def authenticate(self):
        url = f"{VEEAM_HOST}/api/v1/token"
        data = f"grant_type=password&username={VEEAM_USER}&password={VEEAM_PASS}"
        resp = self.session.post(url, headers={**self.headers, "Content-Type": "application/x-www-form-urlencoded"}, data=data)
        resp.raise_for_status()
        self.token = resp.json()["access_token"]
        self.headers["Authorization"] = f"Bearer {self.token}"
        log.info("✅ Đăng nhập Veeam API thành công")

    def get(self, path, params=None):
        url = f"{VEEAM_HOST}/api/v1{path}"
        resp = self.session.get(url, headers=self.headers, params=params)
        if resp.status_code == 401:
            log.warning("Token hết hạn, đăng nhập lại...")
            self.authenticate()
            resp = self.session.get(url, headers=self.headers, params=params)
        resp.raise_for_status()
        return resp.json()

    def get_jobs(self):
        return self.get("/jobs").get("data", [])

    def get_job_sessions(self, limit=200):
        return self.get("/jobSessions", params={"limit": limit}).get("data", [])

    def get_repositories(self):
        return self.get("/backupRepositories").get("data", [])

    def get_managed_servers(self):
        try:
            return self.get("/backupServers").get("data", [])
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
    "Success": 1,
    "Warning": 2,
    "Failed":  3,
    "Running": 0,
    "None":    -1,
}

def build_job_points(jobs):
    points = []
    now = datetime.now(timezone.utc)
    for job in jobs:
        last_result = job.get("lastResult", "None")
        p = (
            Point("veeam_job")
            .tag("job_name", job.get("name", "unknown"))
            .tag("job_type", job.get("type", "unknown"))
            .tag("last_result", last_result)
            .field("is_enabled", 1 if job.get("isEnabled") else 0)
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
        capacity   = repo.get("capacityGB", 0) or 0
        free_space = repo.get("freeSpaceGB", 0) or 0
        used_space = capacity - free_space
        used_pct   = round((used_space / capacity * 100), 2) if capacity > 0 else 0

        p = (
            Point("veeam_repository")
            .tag("repo_name", repo.get("name", "unknown"))
            .tag("repo_type", repo.get("type", "unknown"))
            .field("capacity_gb",   float(capacity))
            .field("free_space_gb", float(free_space))
            .field("used_space_gb", float(used_space))
            .field("used_percent",  used_pct)
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
        log.info(f"  📋 Jobs: {len(jobs)}")
    except Exception as e:
        log.error(f"Lỗi lấy jobs: {e}")

    try:
        sessions = veeam.get_job_sessions()
        points += build_session_points(sessions)
        log.info(f"  📁 Sessions: {len(sessions)}")
    except Exception as e:
        log.error(f"Lỗi lấy sessions: {e}")

    try:
        repos = veeam.get_repositories()
        points += build_repo_points(repos)
        log.info(f"  🗄️  Repositories: {len(repos)}")
    except Exception as e:
        log.error(f"Lỗi lấy repositories: {e}")

    if points:
        writer.write(points)
        log.info(f"✅ Đã ghi {len(points)} metrics vào InfluxDB")

def main():
    log.info("🚀 Veeam Collector khởi động...")
    log.info(f"   Veeam Host : {VEEAM_HOST}")
    log.info(f"   InfluxDB   : {INFLUX_URL}")
    log.info(f"   Interval   : {COLLECT_INTERVAL}s")

    veeam  = VeeamAPI()
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
