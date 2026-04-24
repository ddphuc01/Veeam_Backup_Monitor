#!/usr/bin/env python3
"""
=============================================================
  Veeam API Test Script - Không ghi vào InfluxDB
  Chạy script này để verify kết nối Veeam trước khi deploy
=============================================================
  Cách chạy trên server:
    python3 test_veeam_api.py
  
  Hoặc dùng biến môi trường:
    VEEAM_HOST=https://x.x.x.x:9419 \
    VEEAM_USER=admin \
    VEEAM_PASS=password \
    python3 test_veeam_api.py
=============================================================
"""

import os
import sys
import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─── Config (đọc từ env hoặc điền trực tiếp để test) ────────
VEEAM_HOST    = os.getenv("VEEAM_HOST",  "https://192.168.4.2:9419")
VEEAM_USER    = os.getenv("VEEAM_USER",  "svc_veeam_monitor")
VEEAM_PASS    = os.getenv("VEEAM_PASS",  "7z;V)7Me32xdvbKUmR97")
API_VERSION   = os.getenv("API_VERSION", "1.0-rev1")   # Veeam v11=1.0-rev1, v12=1.1

# ─── Helpers ─────────────────────────────────────────────────
BOLD  = "\033[1m"
GREEN = "\033[92m"
RED   = "\033[91m"
CYAN  = "\033[96m"
YELLOW= "\033[93m"
RESET = "\033[0m"

def ok(msg):   print(f"  {GREEN}✅ {msg}{RESET}")
def err(msg):  print(f"  {RED}❌ {msg}{RESET}")
def info(msg): print(f"  {CYAN}ℹ️  {msg}{RESET}")
def warn(msg): print(f"  {YELLOW}⚠️  {msg}{RESET}")
def header(msg): print(f"\n{BOLD}{'─'*55}\n  {msg}\n{'─'*55}{RESET}")

# ─── Step 1: Authenticate ─────────────────────────────────────
def authenticate():
    header("BƯỚC 1: Đăng nhập Veeam API")
    info(f"Host       : {VEEAM_HOST}")
    info(f"User       : {VEEAM_USER}")
    info(f"API Version: {API_VERSION}")

    url  = f"{VEEAM_HOST}/api/v1/token"
    data = f"grant_type=password&username={VEEAM_USER}&password={VEEAM_PASS}"
    hdrs = {
        "Content-Type": "application/x-www-form-urlencoded",
        "x-api-version": API_VERSION,
    }

    try:
        resp = requests.post(url, headers=hdrs, data=data, verify=False, timeout=10)
        print(f"  HTTP Status: {resp.status_code}")

        if resp.status_code == 200:
            token = resp.json().get("access_token", "")
            ok(f"Đăng nhập thành công! Token: {token[:30]}...")
            return token
        elif resp.status_code == 401:
            err("401 Unauthorized — Sai username/password")
            print(f"  Response: {resp.text[:300]}")
        elif resp.status_code == 404:
            err("404 Not Found — Sai API path hoặc API version header")
            warn("Thử đổi API_VERSION: export API_VERSION=1.1 rồi chạy lại")
            print(f"  URL thử: {url}")
        else:
            err(f"Lỗi không xác định: {resp.status_code}")
            print(f"  Response: {resp.text[:300]}")

    except requests.exceptions.ConnectionError as e:
        err(f"Không kết nối được đến {VEEAM_HOST}")
        print(f"  Chi tiết: {e}")
    except requests.exceptions.Timeout:
        err("Timeout sau 10 giây — server không phản hồi")
    except Exception as e:
        err(f"Lỗi: {e}")

    sys.exit(1)

# ─── Step 2: Get data ─────────────────────────────────────────
def get(session, path, label):
    url = f"{VEEAM_HOST}/api/v1{path}"
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            ok(f"{label}: {len(data)} items")
            return data
        else:
            err(f"{label}: HTTP {resp.status_code}")
            print(f"  Response: {resp.text[:200]}")
            return []
    except Exception as e:
        err(f"{label}: {e}")
        return []

# ─── Print helpers ────────────────────────────────────────────
def print_jobs(jobs):
    header("BƯỚC 2: Danh sách Backup Jobs")
    if not jobs:
        warn("Không có jobs nào")
        return
    fmt = f"  {{:<35}} {{:<15}} {{:<10}}"
    print(fmt.format("Job Name", "Type", "Last Result"))
    print(f"  {'─'*60}")
    for j in jobs:
        name   = j.get("name", "?")[:34]
        jtype  = j.get("type", "?")[:14]
        result = j.get("lastResult", "?")
        color  = GREEN if result == "Success" else (RED if result == "Failed" else YELLOW)
        print(f"  {name:<35} {jtype:<15} {color}{result}{RESET}")

def print_sessions(sessions):
    header("BƯỚC 3: Job Sessions gần đây (top 10)")
    if not sessions:
        warn("Không có sessions nào")
        return
    fmt = f"  {{:<35}} {{:<12}} {{:<6}}"
    print(fmt.format("Job Name", "Status", "Progress%"))
    print(f"  {'─'*56}")
    for s in sessions[:10]:
        name    = s.get("jobName", "?")[:34]
        result  = s.get("result", {})
        status  = result.get("result", "?") if result else "?"
        pct     = s.get("progressPercent", 0)
        color   = GREEN if status == "Success" else (RED if status == "Failed" else YELLOW)
        print(f"  {name:<35} {color}{status:<12}{RESET} {pct}%")

def print_repos(repos):
    header("BƯỚC 4: Repositories")
    if not repos:
        warn("Không có repository nào")
        return
    fmt = f"  {{:<30}} {{:>10}} {{:>10}} {{:>8}}"
    print(fmt.format("Repo Name", "Total(GB)", "Free(GB)", "Used%"))
    print(f"  {'─'*62}")
    for r in repos:
        name  = r.get("name", "?")[:29]
        cap   = r.get("capacity", 0) or 0
        free  = r.get("freeSpace", 0) or 0
        used  = cap - free
        pct   = round(used / cap * 100, 1) if cap > 0 else 0
        color = RED if pct > 85 else (YELLOW if pct > 70 else GREEN)
        print(f"  {name:<30} {cap:>10.1f} {free:>10.1f} {color}{pct:>7.1f}%{RESET}")

# ─── Main ─────────────────────────────────────────────────────
def main():
    print(f"\n{BOLD}{'='*55}")
    print(f"  VEEAM API TEST SCRIPT")
    print(f"{'='*55}{RESET}")

    # Auth
    token = authenticate()

    # Setup session
    session = requests.Session()
    session.verify = False
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "x-api-version": API_VERSION,
    })

    # Fetch data
    jobs     = get(session, "/jobs",             "Jobs")
    sessions = get(session, "/jobSessions?limit=50", "Sessions")
    repos    = get(session, "/backupRepositories","Repositories")

    # Print results
    print_jobs(jobs)
    print_sessions(sessions)
    print_repos(repos)

    # Summary
    header("KẾT QUẢ TỔNG HỢP")
    ok(f"Tổng Jobs        : {len(jobs)}")
    ok(f"Tổng Sessions    : {len(sessions)}")
    ok(f"Tổng Repositories: {len(repos)}")
    ok("API hoạt động bình thường — sẵn sàng ghi vào InfluxDB!")
    print()

if __name__ == "__main__":
    main()
