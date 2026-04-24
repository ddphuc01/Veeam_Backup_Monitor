import json

path = "grafana/dashboards/veeam-monitor.json"
with open(path, "r", encoding="utf-8") as f:
    dashboard = json.load(f)

# Shift items down
for panel in dashboard["panels"]:
    panel["gridPos"]["y"] += 6

# Add Infrastructure Row
dashboard["panels"].insert(0, {
    "collapsed": False,
    "gridPos": { "h": 1, "w": 24, "x": 0, "y": 0 },
    "id": 200,
    "title": "Infrastructure Health",
    "type": "row"
})

# Add Managed Server Stat
dashboard["panels"].insert(1, {
    "datasource": {"type": "influxdb"},
    "fieldConfig": {
    "defaults": {
        "color": {"mode": "thresholds"},
        "mappings": [],
        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
    },
    "overrides": []
    },
    "gridPos": { "h": 5, "w": 5, "x": 0, "y": 1 },
    "id": 201,
    "options": {"reduceOptions": {"calcs": ["count"], "fields": "", "values": False}, "textMode": "auto"},
    "targets": [{
    "datasource": {"type": "influxdb"},
    "query": "from(bucket: \"veeam\") |> range(start: -10m) |> filter(fn: (r) => r[\"_measurement\"] == \"veeam_managed_server\") |> group(columns: [\"server_name\"]) |> count() |> group() |> count()",
    "refId": "A"
    }],
    "title": "Managed Servers",
    "type": "stat"
})

# Add Proxy Stat
dashboard["panels"].insert(2, {
    "datasource": {"type": "influxdb"},
    "fieldConfig": {
    "defaults": {
        "color": {"mode": "thresholds"},
        "mappings": [],
        "thresholds": {"mode": "absolute", "steps": [{"color": "red", "value": None}, {"color": "green", "value": 1}]}
    },
    "overrides": []
    },
    "gridPos": { "h": 5, "w": 5, "x": 5, "y": 1 },
    "id": 202,
    "options": {"reduceOptions": {"calcs": ["count"], "fields": "", "values": False}, "textMode": "auto"},
    "targets": [{
    "datasource": {"type": "influxdb"},
    "query": "from(bucket: \"veeam\") |> range(start: -10m) |> filter(fn: (r) => r[\"_measurement\"] == \"veeam_proxy\") |> group(columns: [\"proxy_name\"]) |> count() |> group() |> count()",
    "refId": "A"
    }],
    "title": "Backup Proxies",
    "type": "stat"
})

# Update Job Details Query
for panel in dashboard["panels"]:
    if panel.get("title") == "Job Historical Information (Detailed)":
        for target in panel.get("targets", []):
            target["query"] = """from(bucket: "veeam")
  |> range(start: -24h)
  |> filter(fn: (r) => r["_measurement"] == "veeam_job")
  |> filter(fn: (r) => r["_field"] == "status_code" or r["_field"] == "objects_count")
  |> group(columns: ["job_name", "job_type", "last_result", "status", "_field"])
  |> last()
  |> group()
  |> pivot(rowKey:["job_name", "job_type", "last_result", "status"], columnKey: ["_field"], valueColumn: "_value")
  |> keep(columns: ["_time", "job_name", "job_type", "last_result", "status", "objects_count"])"""
        
        # update transformations
        if "transformations" in panel:
            panel["transformations"][0]["options"]["renameByName"].update({
                "objects_count": "VMs/Objects",
                "status": "Veeam State"
            })

with open(path, "w", encoding="utf-8") as f:
    json.dump(dashboard, f, indent=2)
print("Updated dashboard!")
