---
id: sunny-dashboard
type: component
status: active
created: 2026-08-18
tags: [dashboard, monitoring, ui, metrics]
---

# Dashboard — Local Web UI

A lightweight web-based control panel for monitoring Sunny's health, spending, and system status. Bound to Tailscale interface only (never exposed to internet).

## Overview

**Framework**: FastAPI (Python async web framework)
**Binding**: `0.0.0.0:5000` — listens on all interfaces so it's reachable both locally and over Tailscale; security comes from Tailscale being the only network that can route to the box, not from interface binding
**Port**: 5000
**Access**: From phone anywhere via Tailscale mesh
**Authentication**: None (Tailscale itself provides security)
**Storage**: SQLite sunny.db (local metrics)

> **Implementation note**: The panels below (Spend, Health, Clock Battery, Tailscale, Activity) describe the target design. What's actually built today is one combined page at `/console` — chat on one side, live system stats (CPU, RAM, disk, network, temperature) and Google sign-in status on the other (`/` and the old `/chatbot` both redirect there now; there is no separate chat page anymore). A JSON backend for this dashboard also exists (`/api/dashboard/health`, `/metrics/latest`, `/metrics/record`, `/spend/today`, `/spend/month`, `/usage/live`, `/status`), but the `/console` page itself renders none of it — `/metrics/record`/`/metrics/latest` are genuinely dead (nothing calls `record_metric()`, so the Host Resources/CPU-temp/disk panel below stays target-only), and service health tracking (`update_service_health()`) has no caller either, so the Health and Clock Battery panels are also still unbuilt. Spend is the exception: `/spend/today`, `/spend/month`, and `/usage/live` are real, backed by `token_tracker.py` — but the visibility surface for that data is Discord (`/usage` chart, the persistent `#health` dashboard), not a panel on this page — see [[usage-tracking]]. See [[../phases.md]] for status.

## Architecture

```
Sunny Core Process
    ├─→ Metrics collection (every 30s)
    │ ├─→ CPU, RAM, disk, temperature
    │ ├─→ Token usage (from circuit breaker)
    │ ├─→ API health (last-success timestamps)
    │ ├─→ Battery status (Clock device)
    │ └─→ Process uptime (systemd)
    │
    └─→ SQLite sunny.db
        ├─→ Metrics table (30-second samples)
        ├─→ Health table (API timestamps)
        └─→ Token usage table (daily rollup)

FastAPI Dashboard Server
    ├─→ Read from sunny.db
    ├─→ Render JSON or HTML views
    └─→ Listen on Tailscale IP:5000
```

## Dashboard Panels

### 1. Spend Panel

**Purpose**: Track LLM and API token spending
**Updates**: Real-time (on every LLM call)

**Displays**:
```
SPEND TODAY
  Tokens used: 12,500 prompt + 3,400 completion = 15,900
  Cost: $0.27 (Haiku rate)
  Budget remaining: $19.73 (of $20/day)
  Monthly projected: $8.10 (of $100 budget)

BREAKDOWN BY SURFACE
  Clock wake word: 2,000 tokens ($0.03)
  Phone conversation: 8,500 tokens ($0.14)
  Email triage: 5,400 tokens ($0.09)
  Background jobs: 0 tokens ($0.00)
  
ALERTS
  Under budget (daily)
  Under budget (monthly)
```

**Data Source**: Token circuit breaker logs
**Refresh**: On demand + every 60s

---

### 2. Health Panel

**Purpose**: See which services are up/down
**Updates**: On service calls + every 60s heartbeat

**Displays**:
```
SERVICE HEALTH
  Claude API ........... Last seen 2 min ago
  Sonic API ............ Last seen 8 min ago
  Twilio ............... Last seen 1 hour ago
  Discord bot .......... Last seen 30 sec ago
  Calendar API ......... Last seen 4 hours ago
  Weather API .......... Last seen 12 hours ago
  Traffic API .......... Last seen 2 hours ago
  Tailscale ............ Connected
  Clock device ......... Last ping 5 min ago
  TrueNAS .............. Reachable
```

**Why timestamps, not green/red?**
- "Last seen 12 hours ago" → weather API not critical for briefing
- "Last seen 2 min ago" → real-time services working
- Easy to spot which service hasn't been used recently

---

### 3. Host Resources Panel

**Purpose**: Monitor [[brain]] system performance
**Updates**: Every 30 seconds (psutil sampling)

**Displays**:
```
LENOVO MINI PC
  CPU: 45% (load avg: 1.2, 0.9, 0.8)
  CPU Temp: 62°C (fan: idle, no throttling)
  RAM: 620MB / 1024MB (60% used)
  Disk (root): 52GB / 100GB (52% used)
  Disk (boot): 1.5GB / 2GB (75% used)
  Uptime: 28 days, 3 hours, 14 min
  Last restart: 2026-08-18 07:30:22 UTC (systemd auto-restart)
```

**Why CPU temp matters?**
Whisper (speech recognition) on mini PC can thermally throttle before erroring. Temperature trend shows when performance will degrade.

**Why disk tracking?**
Filling the root disk crashes Obsidian vault, logs, and sunny.db. Separate `/boot` tracking shows if partitions are out of balance.

---

### 4. Clock Battery Panel

**Purpose**: Monitor [[clock]] ESP32 battery status
**Updates**: Every heartbeat (5-minute checks)

**Displays** (per device, scalable for multiple clocks):
```
CLOCK BATTERY STATUS
  Device ID: clock-bedroom-001
  Charge state: ON MAINS (charging)
  Cell voltage: 3.62V (3.2-3.65V LFP range)
  Uptime: 2 days, 14 hours (since last boot)
  Runtime remaining: 11 hours 45 min (if unplugged now)

  ALERT: Battery on mains → charging normally
  Health: Good (cell voltage nominal)
  
  Estimated discharge rate: 40mA idle, 80mA speaking
  12-hour target: PASS (11h 45m > 12h minimum)
```

**Key metrics**:
- **Charge state** (mains vs battery) → actionable, not a percentage
- **Runtime remaining** → tells you how long alarm survives power cut
- **Voltage** → better than % for LFP (discharge curve is flat)

---

### 5. Tailscale Network Panel

**Purpose**: Monitor device connectivity and mesh status
**Updates**: Every 60 seconds (tailscale status command)

**Displays**:
```
TAILSCALE MESH NETWORK
  Tailscale account: T3R4Bit@github
  Tailnet: default (personal)
  Self IP: 100.1.1.2 (Lenovo brain)

CONNECTED DEVICES (in tailnet)
  brain (100.1.1.2)
     OS: Linux (Ubuntu 26.04 LTS)
     Hostname: lenovo-mini-pc
     Status: Active, online
     Last seen: now
     Connection: Direct (local network)
  
  clock-bedroom (100.1.1.5)
     OS: ESP32-S3 (MicroLink)
     Hostname: esp32-clock-01
     Status: Active, online
     Last seen: 3 min ago
     Connection: Via DERP relay (Tailscale infrastructure)
  
  truenas (100.1.1.10)
     OS: TrueNAS Scale
     Hostname: truenas-scale
     Status: Active, online
     Last seen: now
     Connection: Direct (local network)
  
  phone (100.1.1.20)
     OS: iOS
     Hostname: keaton-iphone
     Status: Active, online (away from home)
     Last seen: now
     Connection: Via DERP relay (remote)

NETWORK SECURITY
  Encryption: WireGuard (end-to-end)
  ACLs: Default (all devices trust each other)
  Exit node: None (no masking)
  
  All devices encrypted
  No open ports exposed
  Remote access working (DERP relays healthy)
```

**What to watch**:
- **Connection type** (Direct vs DERP) → shows if local network is healthy
- **Last seen** → tells you if device is stale or alive
- **DERP relays** → indicates if internet connectivity is working
- **All devices present** → confirms mesh is intact

**Alerts**:
```
Clock offline (>10 min) → Alarm might not work
TrueNAS offline → Can't sync logs
All devices online → Full system operational
```

---

### 6. Needs Attention Panel

**Purpose**: Flags that need immediate action
**Updates**: Real-time + every 60s refresh

**Example alerts**:
```
NEEDS ATTENTION
  API key expiring (Twilio): 15 days remaining
  Disk warning: Root at 75%, need cleanup
  Obsidian staging backlog: 3 items pending Notion sync (12 hours old)
  Clock battery: On battery for 2+ hours (power outage?)
  Token spend: 90% of daily budget used (1 hour into day)
  Email API: Unavailable 4 hours (skip triage in briefing)
```

---

### 7. Recent Activity Panel

**Purpose**: See what Sunny has been doing
**Updates**: Log tail (last 50 actions)

**Displays**:
```
RECENT ACTIVITY (last 50)
  14:32:15 Morning briefing delivered (12 words/sec, Sonic TTS)
  14:32:08 Calendar: Fetched today's events (3 events)
  14:31:45 Weather: Fetched forecast (72°F, partly cloudy)
  14:31:22 Task created: "Buy milk" (from phone call)
  14:30:50 Phone call: Incoming from +1-555-0123 (5m 22s duration)
  14:30:10 Claude API: Email triage (8 emails processed)
  14:29:55 Email: Fetched 12 new messages
  ...
```

**Filterable by**:
- Type (briefing, task, email, phone, etc.)
- Time range (today, last 24h, week)
- Status (success, warning, error)

---

## Technical Details

### Data Storage (sunny.db)

```sql
-- Metrics table (30-second samples, 30-day retention)
CREATE TABLE metrics (
  timestamp DATETIME,
  cpu_percent REAL,
  ram_percent REAL,
  disk_percent REAL,
  cpu_temp REAL,
  tokens_used INTEGER,
  tokens_cost REAL
);

-- Health table (timestamps of last successful API calls)
CREATE TABLE service_health (
  service_name TEXT PRIMARY KEY,
  last_success DATETIME,
  last_error TEXT,
  error_count INTEGER
);

-- Token usage (daily rollup)
CREATE TABLE token_usage (
  date DATE PRIMARY KEY,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  total_cost REAL,
  by_model TEXT -- JSON breakdown
);
```

### API Endpoints

```python
@app.get("/api/spend")
def get_spend() -> dict:
    """Current day spending and budget"""
    
@app.get("/api/health")
def get_health() -> dict:
    """Service health (last-success timestamps)"""
    
@app.get("/api/resources")
def get_resources() -> dict:
    """CPU, RAM, disk, temperature"""
    
@app.get("/api/clock/<device_id>")
def get_clock_status(device_id: str) -> dict:
    """Battery, voltage, uptime for specific clock"""
    
@app.get("/api/tailscale")
def get_tailscale_status() -> dict:
    """Tailscale mesh status (devices, IPs, connections)"""
    
@app.get("/api/alerts")
def get_alerts() -> dict:
    """Things needing attention"""
    
@app.get("/api/activity")
def get_activity(limit: int = 50) -> list:
    """Recent activity log (last N actions)"""
```

### Frontend

**Technology**: Vanilla HTML/CSS/JavaScript (no build step)
**Refresh**: Auto-refresh every 60 seconds
**Mobile-friendly**: Responsive design (works on phone via Tailscale)
**No authentication**: Security via Tailscale only

---

## Access from Phone

1. Phone must be joined to Tailscale mesh (done: iphone181 at 100.73.98.114)
2. Navigate to: `http://sunshine-m700:5000/` or `http://100.117.41.53:5000/`
3. See real-time metrics from anywhere (home or away)

**Example**: Check spending while out of house via Tailscale DERP relay

**Phase 1 Status**: Brain (Lenovo sunshine-m700) at 100.117.41.53, verified reachable via Tailscale (5ms latency)

---

## Performance & Overhead

- **Memory**: ~50-100MB for FastAPI + SQLite
- **Disk**: ~1KB per 30-second sample = ~2.5MB/month
- **CPU**: Negligible (idle most of time)
- **Retention**: 30 days of samples, then auto-purge

---

## Implementation Checklist

- [ ] FastAPI setup (basic hello-world)
- [ ] Bind to Tailscale IP only (not 0.0.0.0)
- [ ] SQLite schema creation
- [ ] Metrics collection loop (30s sampling)
- [ ] Spend panel (token circuit breaker integration)
- [ ] Health panel (service heartbeat tracking)
- [ ] Resources panel (psutil queries)
- [ ] Clock battery panel (device status from [[clock]])
- [ ] Tailscale panel (tailscale status parsing)
- [ ] Alerts panel (hardcoded rules)
- [ ] Activity panel (log tail)
- [ ] HTML template (responsive design)
- [ ] Auto-refresh JavaScript (60s interval)
- [ ] Test from phone via Tailscale
- [ ] Documentation (this file)

---

## Dependencies

- [[brain]] — Runs FastAPI server
- [[clock]] — Provides battery status
- [[networking]] — Tailscale mesh
- [[usage-tracking]] — token spend data (`token_tracker.py`), the real implementation behind `/spend/today`/`/spend/month`/`/usage/live`; see [[llm-integration]] for the circuit breaker itself
- [[voice-io]] — Activity logging
- [[briefing-engine]] — Activity logging
- psutil (Python) — System metrics
- sqlite3 (Python) — Local database

---

## Future Enhancements

- **Graphs**: Historical token spend, CPU/RAM trends
- **Notifications**: Push alerts to Discord on critical events
- **Export**: Download metrics as CSV
- **Remote trigger**: Manually run briefing from dashboard
- **Settings**: Adjust thresholds (e.g., battery low alert at 30%)
- **Multi-device**: Track stats per [[clock]] device separately
