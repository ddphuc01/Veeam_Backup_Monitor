# 🟢 Veeam Backup Monitor - Grafana Stack

Monitor Veeam Backup & Replication với Grafana + InfluxDB.

## 📁 Cấu trúc thư mục

```
veeam-grafana/
├── docker-compose.yml
├── .env.example              ← Copy thành .env và điền thông tin
├── collector/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── collector.py          ← Script thu thập data từ Veeam API (Python)
│   └── veeam_backup_and_replication.sh  ← Script bash từ VeeamHub (tham khảo)
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── influxdb.yml
    │   └── dashboards/
    │       └── dashboard.yml
    └── dashboards/
        ├── veeam-monitor.json            ← Dashboard gốc (đơn giản)
        └── veeam-backup-replication.json ← Dashboard từ VeeamHub (chi tiết)
```

## 🚀 Cài đặt nhanh

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

Dashboard sẽ nằm trong folder **Veeam Dashboards**:
- **Veeam Backup Monitor** (đơn giản, Python collector)
- **Grafana Dashboard for Veeam Backup & Replication** (chi tiết, từ VeeamHub)

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

## 📊 Dashboard từ VeeamHub

Dự án này đã tích hợp dashboard chính thức từ [VeeamHub/grafana](https://github.com/VeeamHub/grafana/tree/master/veeam-backup-and-replication-grafana):

- File: `grafana/dashboards/veeam-backup-replication.json`
- Dashboard này yêu cầu dữ liệu từ script `veeam_backup_and_replication.sh` (bash)
- Script bash đã được tải về trong thư mục `collector/` để tham khảo

### Lưu ý quan trọng:
- **Collector hiện tại (Python)**: Thu thập metrics cơ bản cho dashboard `veeam-monitor.json`
- **Script bash từ VeeamHub**: Cần chạy riêng nếu muốn dùng dashboard đầy đủ từ VeeamHub
- Để sử dụng dashboard VeeamHub, bạn cần:
  1. Chỉnh sửa `collector/veeam_backup_and_replication.sh` với thông tin Veeam của bạn
  2. Chạy script này trên máy host hoặc trong container riêng
  3. Đảm bảo dữ liệu ghi vào cùng InfluxDB bucket `veeam`

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

---

## 📄 Tài liệu tham khảo

- [VeeamHub Dashboard gốc](https://github.com/VeeamHub/grafana/tree/master/veeam-backup-and-replication-grafana)
- [Blog hướng dẫn chi tiết](https://jorgedelacruz.uk/2023/05/31/looking-for-the-perfect-dashboard-influxdb-telegraf-and-grafana-part-xliv-monitoring-veeam-backup-replication-api/)
