# 🟢 Veeam Backup Monitor - Grafana Stack

Monitor Veeam Backup & Replication 11 với Grafana + InfluxDB.

## 📁 Cấu trúc thư mục

```
veeam-grafana/
├── docker-compose.yml
├── .env.example              ← Copy thành .env và điền thông tin
├── collector/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── collector.py          ← Script thu thập data từ Veeam API
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── influxdb.yml
    │   └── dashboards/
    │       └── dashboard.yml
    └── dashboards/
        └── veeam-monitor.json
```

## 🚀 Cài đặt

### Bước 1: Chuẩn bị file .env
```bash
cp .env.example .env
nano .env   # Điền thông tin Veeam server và password
```

### Bước 2: Khởi động stack
```bash
docker compose up -d
```

### Bước 3: Kiểm tra logs
```bash
# Xem collector có kết nối Veeam được không
docker logs veeam-collector -f

# Xem InfluxDB
docker logs veeam-influxdb -f
```

### Bước 4: Truy cập Grafana
```
URL      : http://localhost:3000
Username : admin
Password : (xem file .env - GRAFANA_PASSWORD)
```

Dashboard sẽ nằm trong folder **Veeam** → **Veeam Backup Monitor**

---

## 🔗 Ports

| Service   | Port |
|-----------|------|
| Grafana   | 3000 |
| InfluxDB  | 8086 |

---

## 🔧 Tùy chỉnh

### Thay đổi tần suất thu thập
Trong file `.env`:
```
COLLECT_INTERVAL=120   # Thu thập mỗi 2 phút
```

### Xem metrics thủ công trong InfluxDB
Truy cập: `http://localhost:8086`
- Username/Password: xem file `.env`
- Vào **Data Explorer** → chọn bucket `veeam`

---

## 🐛 Troubleshoot

```bash
# Restart collector
docker restart veeam-collector

# Xem logs lỗi
docker logs veeam-collector --tail 50

# Kiểm tra kết nối từ collector tới Veeam
docker exec veeam-collector curl -k https://<veeam-ip>:9419/api/v1/token
```
