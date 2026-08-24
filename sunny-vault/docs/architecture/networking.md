---
id: sunny-networking
type: component
status: active
created: 2026-08-18
tags: [networking, tailscale, security, mesh]
---

# Networking — Tailscale Mesh

All devices (Lenovo [[brain]], ESP32 [[clock]], TrueNAS, phone) join a secure Tailscale network mesh. End-to-end encrypted, no open ports, works even when away from home.

## Architecture

```
Home Network (WiFi):
  ├─ Lenovo mini PC [[brain]]
  ├─ ESP32-S3 Clock [[clock]]
  ├─ TrueNAS server
  └─ Phone (mobile)

        ↓ (all join Tailscale)

Tailscale Mesh (Encrypted VPN):
  ├─ Lenovo: 100.x.x.x (stable private IP)
  ├─ Clock: 100.x.x.x (stable private IP)
  ├─ TrueNAS: 100.x.x.x
  └─ Phone: 100.x.x.x

Remote Access:
  └─ Anywhere via Tailscale (DERP relays if NAT)
```

## Tailscale Setup

### Lenovo Mini PC [[brain]]

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --advertise-routes=<home-network-ip>/24

# Check connection
tailscale ip -4
# Output: 100.x.x.x (stable private IP)
```

**Purpose**: Joins mesh, stable IP for Clock to reach

### ESP32-S3 Clock [[clock]]

```cpp
// Use MicroLink: Tailscale-compatible client for ESP32
// GitHub: tailscale/tailscale-esp32

#include <MicroLink.h>

void setup() {
  MicroLink.begin("SSID", "password");
  // Connects to Tailscale automatically
}
```

**MicroLink features**:
- WireGuard encryption
- DERP relay (works behind NAT)
- STUN support (NAT traversal)
- Low power (optimized for ESP32)

### TrueNAS Server

```bash
# Add Tailscale via TrueNAS GUI
# Settings → System → Tailscale
# Or CLI: tailscale up
```

### Phone

```
iOS/Android:
  1. Install Tailscale app
  2. Sign in with same account
  3. Joins mesh automatically
  4. Can reach Lenovo at 100.x.x.x
```

## Device Communication

Once on mesh, all devices reach each other:

- **Clock → Brain**: Sends wake word audio, receives TTS stream
  ```
  Clock (100.x.x.x) → Brain (100.117.41.53:8000)
  ```

- **Brain → TrueNAS**: Push logs, pull media metadata
  ```
  Brain (100.117.41.53) → TrueNAS (100.123.58.119:8080)
  ```

- **Phone → Brain**: Access local dashboard
  ```
  Phone (100.73.98.114) → Brain (100.117.41.53:5000)
  ```

- **Outside home**: Same addresses work via DERP relays
  ```
  Phone (anywhere) → Tailscale DERP → Brain (100.117.41.53)
  ```

## Current Tailscale Network (Phase 1 Active)

| Device | Hostname | IP | OS | Status |
|--------|----------|----|----|--------|
| Brain | sunshine-m700 | 100.117.41.53 | Ubuntu 26.04 LTS | Active, reachable |
| TrueNAS | caliop-truenas | 100.123.58.119 | TrueNAS Scale | Active, reachable |
| Phone | iphone181 | 100.73.98.114 | iOS | Active |
| Workstation | keaton-pc | 100.82.153.78 | Windows | Active |
| Clock | (pending) | TBD | ESP32-S3 | Not yet configured |

## Security Model

### Zero Trust

- No port forwarding
- No open firewall holes
- No exposed internet
- Only members of tailnet can reach devices
- Connections are encrypted end-to-end

### Access Control

**Tailscale ACLs** (optional, configured in Tailscale console):
```hujson
{
  "acls": [
    // All devices can reach each other
    {"action": "accept", "src": ["autogroup:members"], "dst": ["autogroup:members:*"]},
  ],
  "hosts": {
    "brain": "100.1.1.2",
    "clock": "100.1.1.5",
    "truenas": "100.1.1.10",
  },
}
```

**In practice**: Personal use → all devices trust each other (no ACL needed)

## DNS

Tailscale provides DNS within the mesh:

- `brain` → resolves to 100.1.1.2
- `clock` → resolves to 100.1.1.5
- `truenas` → resolves to 100.1.1.10

**Clock can reach Brain via**:
```python
# Instead of hardcoding IP
socket.connect("brain:8000")

# Or DNS name
requests.get("http://brain:5000/api/status")
```

## Latency & Reliability

| Scenario | Latency | Notes |
|----------|---------|-------|
| Local network (same WiFi) | <5ms | Direct peer-to-peer |
| Local network (different WiFi) | <10ms | Via home router |
| Away from home (DERP relay) | 50-200ms | Via Tailscale infrastructure |
| Network switch/failover | <1s | Automatic re-routing |
| Tailscale down | N/A | Devices still work locally (Clock still listens) |

## Tailscale Pricing

- **Personal**: Free (unlimited devices)
- **Organization**: Paid tier (advanced features not needed)
- **Usage**: Minimal bandwidth (only encrypted traffic)

## Remote Dashboard Access

The [[dashboard]] is bound to Tailscale interface only:

```python
# FastAPI
from fastapi import FastAPI

app = FastAPI()

@app.get("/status")
def status():
    return {"cpu": 45, "ram": 60, "tokens_today": 2500}

# Listen on Tailscale interface only (not 0.0.0.0)
if __name__ == "__main__":
    import uvicorn
    tailscale_ip = get_tailscale_ip() # 100.x.x.x
    uvicorn.run(app, host=tailscale_ip, port=5000)
```

**Result**: Dashboard accessible from phone anywhere via Tailscale, but not exposed to internet.

## Optional: Public Exit Node

If needed (advanced):
```bash
# Lenovo can act as exit node for phone
tailscale up --advertise-exit-node

# Then on phone
tailscale set --exit-node=brain
# All phone traffic routes through Lenovo
```

**Use case**: Public WiFi safety, or masking phone's public IP

## Failover Scenarios

**Lenovo offline**:
- Clock still boots, listens for wake word (local, no network needed)
- Commands queued, executed when [[brain]] comes back online
- Alarm still fires (battery-backed)

**Network down**:
- Clock offline → queued commands lost (acceptable, alarm still works)
- Phone outside home → can't reach dashboard (expected)

**Tailscale service down** (rare):
- Devices fall back to local network (if on same WiFi)
- Remote access fails temporarily
- Devices sync when Tailscale recovers

## Future: Multi-Clock Setup

Tailscale scales easily for multiple devices:
```
Kitchen Clock (100.1.1.6)
Living Room Clock (100.1.1.7)
Bedroom Clock (100.1.1.5) ← original

All reach [[brain]] the same way
```

## Dependencies

- [[brain]] — Tailscale daemon + IP assignment
- [[clock]] — MicroLink ESP32 client
- TrueNAS — Tailscale integration
- Tailscale infrastructure — DERP relays, PKI
- Home router — WiFi access (not Tailscale dependent)

## Implementation Checklist (Phase 1)

- [ ] Install Tailscale on Lenovo [[brain]]
- [ ] Join TrueNAS to mesh
- [ ] Flash MicroLink on ESP32 [[clock]]
- [ ] Test Clock ↔ Brain connectivity
- [ ] Install Tailscale on phone
- [ ] Test phone dashboard access
- [ ] Document stable private IPs
- [ ] Test remote access (away from home)
- [ ] Set up optional exit node
- [ ] Monitor DNS resolution
