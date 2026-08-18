---
id: sunny-hardware
type: reference
status: active
source: notion
created: 2026-08-18
tags: [hardware, specs, clock, power, battery]
---

# Hardware Specifications

## Lenovo Mini PC (Brain)

**Role**: Always-on compute for Sunny core, LLM API calls, voice processing

- **Model**: Lenovo ThinkCentre (existing, always-on)
- **OS**: Ubuntu Server 20.04, headless
- **Monitor**: Optional, for setup/debugging only
- **Systemd**: Sunny runs as `Restart=always` unit
- **BIOS Critical Settings**:
  - ✅ Restore Power State on AC Loss: **Enabled** (auto-boots when power returns)
  - ✅ Boot order: Local disk first, no USB/PXE
  - ✅ Disable unattended-upgrades auto-reboot
  - ❌ Disable PXE IPv4/IPv6
  - ❌ Disable sleep/suspend modes

## The Clock (ESP32-S3 Bedside Device)

### Concept
Dedicated physical device, hard-baked with local commands (like pre-AI Alexa), rather than routing everything through LLM. Wakes you up, shows time, accepts voice commands, displays status.

### Budget & Battery
- **Target cost**: Under $100
- **Battery backup target**: 12 hours (so you don't miss alarm if power cuts)

### Brain
- **Chip**: ESP32-S3, low power, handles:
  - Wake word detection (local)
  - Hardwired commands
  - Hands off complex requests to Lenovo
- **Networking**: MicroLink (Tailscale-compatible WireGuard client for ESP32)

### Display
- **Type**: Small OLED screen
- **Advantage**: Self-lit, low power, visible in dark without backlight draining battery
- **Shows**: Time, status icons, simple messages

### Power System

**Battery Type**: LiFePO4 (LFP) 26650, **not Li-ion or LiPo**
- Why LFP:
  - Thermal runaway threshold: ~270°C (vs 150°C for LiPo)
  - Cycle life: 2000-5000 cycles (vs 300-500 for LiPo)
  - **Critical**: Tolerates sitting at full charge indefinitely (exact bedside use case)
  - LiPo/Li-ion degrade and swell under float charge
- Nominal: 3.2V, full: 3.65V
- Capacity: ~3000mAh (26650) for 12-hour backup target

**Charger**: TP5000 (LFP-compatible), **NOT TP4056**
- TP4056 is 4.2V Li-ion charger → will overcharge LFP and damage it
- TP5000 is configurable for LFP voltage curve
- Alternative: CN3058-based LFP charging module

**Boost Converter**: Required for stable 5V output
- Benefits from LFP's flat discharge curve (steadier input voltage)
- Powers ESP32 + OLED + mic/speaker amplifier

**Cell Sizing**: 
- LFP has lower energy density (~1500mAh per 18650 vs 3000+ for Li-ion)
- Single 18650 LFP marginal for 12-hour target
- **Recommended**: 26650 single cell (~3000mAh) or two 18650 LFP in parallel

### Audio I/O
- **Microphone**: Capture wake word + voice commands
- **Speaker**: Play voice responses, alarms
- **Voice codec**: Opus or PCM depending on bandwidth
- **Streaming**: Sonic API for TTS, streamed down from Lenovo (thin client model)

### Wake Word Detection
- **Engine**: openWakeWord or Porcupine (local, no cloud)
- **Variants** learned:
  - "Hey Sunny"
  - "Hello Sunny"
  - "Sunny [command]" (direct command suffix)
- **Local processing**: No privacy loss, works offline

### Enclosure
- **Material**: 3D-printed (custom designed)
- **Size**: Compact bedside form factor
- **Future refinement**: Custom PCB once design proven (currently using off-the-shelf breakout boards)

### Planned Features
- **Adaptive volume**: Measure ambient noise before/during response, scale output volume relative to noise floor
- **Talk-over ducking**: Briefly lower or pause output if user talks over it
- **Status LEDs**: Indicate state (listening, thinking, speaking, battery)
- **Button**: Manual alarm dismiss, manual wake word reset

## TrueNAS Scale Server

**Role**: Media storage, future GPU host for local LLM inference

- **Current**: Media server only (NAS storage)
- **Future**: Host GPUs for local Claude inference once affordable
- **Network**: Joined to Tailscale mesh

## Desktop PC

**Role**: Primary workstation, powered on/off via Wake-on-LAN or smart plug

- **Power control**: Smart plug (Tasmota) or WOL via Lenovo
- **Triggered by**: Sunny voice command or scheduled job
- **Network**: Can be reached via Tailscale when powered on

---

## Component BOM (Clock Assembly, Phase 3)

| Component | Model | Cost | Notes |
|-----------|-------|------|-------|
| ESP32-S3 Dev Board | AzDelivery or similar | $10-15 | S3 variant for best performance |
| OLED Display | 128x64 0.96" I2C | $5-10 | SSD1306 driver |
| LiFePO4 Cell | 26650 3000mAh | $15-20 | Not 18650 alone |
| Charger Module | TP5000 | $5-8 | Must be LFP-compatible |
| Boost Converter | MT3608 or similar 5V | $2-3 | 5V stable output |
| Microphone | INMP441 or similar | $3-5 | I2S digital mic |
| Speaker | 3W 4Ω mini | $3-5 | Or larger if budget allows |
| Enclosure | 3D-printed custom | $0 + filament | Design yourself |
| Misc (wiring, headers, etc.) | — | $5-10 | — |
| **Estimated Total** | — | **$50-75** | Under $100 target |

---

## Power Resilience

### Single Point of Failure Mitigation
- **Lenovo boots after power loss** → auto-boot via BIOS setting ✅
- **Clock has 12-hour battery backup** → alarm survives power cut even if Lenovo doesn't boot immediately ✅
- **Systemd Restart=always** → if Sunny crashes, it restarts ✅
- **No unattended-upgrades reboot** → security patches don't reboot at 3am and miss alarm ✅

### Testing Protocol
1. Power off Lenovo while running
2. Verify Clock stays on battery for at least 1 hour
3. Restore power, verify Lenovo auto-boots
4. Verify Sunny process starts via systemd
5. Verify Clock reconnects over Tailscale
6. Test alarm fires successfully

---

## Networking

- **Tailscale mesh**: All devices (Lenovo, Clock, TrueNAS, phone)
- **No port forwarding**, no exposed internet
- **Clock uses MicroLink**: Tailscale client for ESP32 with WireGuard, DERP, STUN support
- **Recommended**: ESP32-S3 for best MicroLink performance

---

## Future Upgrades

- **Local LLM**: Once GPUs are affordable, move Claude to TrueNAS + local inference
- **Custom PCB**: Replace breakout boards with single-layer PCB for Clock
- **Additional Clocks**: Multi-clock support (bedroom, kitchen, car)
- **Display variants**: Larger OLED, e-ink for lower power
