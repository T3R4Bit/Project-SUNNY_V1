---
id: sunny-clock
type: component
status: active
created: 2026-08-18
tags: [hardware, esp32, clock, device]
---

# Clock — ESP32-S3 Bedside Device

A dedicated, hard-baked voice assistant device for the bedside. Handles wake word detection, simple commands locally, communicates with [[brain]] for complex tasks.

## Concept

Like pre-AI Alexa or Google Home Mini — not routing everything through an LLM, but using local hardwired commands plus remote judgment when needed.

- **On-device**: Wake word detection, mic input, speaker output, OLED display
- **Thin client**: Complex processing (LLM, TTS) delegated to [[brain]] or hosted APIs
- **Battery-backed**: Survives power cuts so alarms don't fail

## Hardware

### Brain
- **Chip**: ESP32-S3 (recommended S3 variant for best performance)
- **Cost**: $10-15
- **Clock speed**: 240 MHz (sufficient for wake word + audio)
- **RAM**: 8MB (adequate for buffering)
- **Storage**: 16MB flash (firmware + voice samples)

### Display
- **Type**: 128x64 OLED, 0.96", I2C interface
- **Advantage**: Self-lit (no backlight), low power, readable in dark
- **Cost**: $5-10
- **Driver**: SSD1306
- **Shows**: Time, status icons, simple messages

### Audio

**Microphone**:
- **Type**: INMP441 I2S digital microphone
- **Cost**: $3-5
- **Benefit**: Digital output, cleaner signal than analog

**Speaker**:
- **Type**: 3W 4Ω mini speaker
- **Cost**: $3-5
- **Output**: Voice responses, alarms, notification sounds
- **Volume**: Adaptive based on ambient noise (planned feature)

### Power System

**Battery**: LiFePO4 (LFP), not Li-ion or LiPo
- **Chemistry**: LFP 26650 cell, ~3000mAh
- **Why LFP**:
  - Tolerates sitting at full charge indefinitely (bedside use case)
  - Thermal runaway: ~270°C (vs 150°C for LiPo)
  - Cycle life: 2000-5000 cycles (vs 300-500 for LiPo)
  - Stable discharge curve
- **Cost**: $15-20

**Charger Module**:
- **Type**: TP5000 (LFP-compatible, configurable 3.65V max)
- **Cost**: $5-8
- **WARNING**: NOT TP4056 (4.2V Li-ion charger, will overcharge LFP)
- **Alternate**: CN3058-based LFP module

**Boost Converter**:
- **Type**: MT3608 or similar, 5V output
- **Cost**: $2-3
- **Purpose**: Stable 5V for ESP32, audio amplifier, display
- **Input**: LFP cell (3.2-3.65V) → Output: 5V stable

**Enclosure**:
- **Material**: 3D-printed PLA/PETG (custom design)
- **Cost**: Filament + design time
- **Purpose**: Bedside form factor, protects battery/circuitry

### Total BOM
| Component | Cost |
|-----------|------|
| ESP32-S3 board | $10-15 |
| OLED display | $5-10 |
| LiFePO4 cell | $15-20 |
| TP5000 charger | $5-8 |
| Boost converter | $2-3 |
| Microphone | $3-5 |
| Speaker | $3-5 |
| 3D enclosure | $5-10 (filament) |
| Wiring/headers | $5-10 |
| **Total** | **$50-75** |

**Target**: Under $100

## Networking

- **Protocol**: Tailscale via MicroLink (Tailscale-compatible WireGuard client for ESP32)
- **Security**: End-to-end encrypted, no open internet
- **Connectivity**: WiFi 802.11ac, joins mesh
- **Range**: Entire home via Tailscale (works even away from home)

**MicroLink details**:
- Tailscale client for ESP32
- WireGuard encryption
- DERP relay for NAT traversal
- STUN support
- Recommended: ESP32-S3 for best performance

## Wake Word Detection

- **Engine**: openWakeWord (local, open-source) or Porcupine (paid)
- **Processing**: 100% on-device, no cloud
- **Variants learned**:
  - "Hey Sunny"
  - "Hello Sunny"
  - "Sunny [command]" (direct command after name)
- **False positive rate**: Tuned to minimize false wakes but catch real voice

## Audio Pipeline

### Incoming (Voice Command)
```
Mic → I2S buffer → Wake word detector (local)
  │
  └─→ Match? → STT (Whisper API or local)
              → Intent parser (hardcoded patterns)
              → [[brain]] for complex requests
              → TTS response
```

### Outgoing (Voice Response)
```
[[brain]] text → Sonic API TTS (or Piper fallback)
  → Stream audio chunks
  → Boost converter + speaker amp
  → Speaker output
  → Optional: Adaptive volume scaling (ambient noise)
  → Optional: Talk-over ducking (pause if user speaks)
```

## Display

**Shows**:
- Current time (HH:MM, 24-hour)
- Status icons:
  - Listening (wake word armed)
  - Processing (thinking)
  - Speaking (outputting)
  - Battery status (charging, battery%, on mains)
- Simple messages (no rich graphics)

## Local Hardwired Commands

Commands that execute **without contacting [[brain]]**:

- **Wake word**: "Hey Sunny" → Arm, ready to listen
- **Alarm dismiss**: Hold button 3s → Stop alarm
- **Manual wake**: Say "good morning" → Exit sleep mode
- **Manual sleep**: Say "good night" → Enter sleep mode (no incoming calls)
- **Status**: "Hey Sunny, status" → Speak battery %, time to next briefing

All other requests forward to [[brain]] for LLM reasoning.

## Features

### Current (Phase 3)
- [x] Wake word detection
- [x] Microphone input
- [x] Speaker output
- [x] OLED display
- [x] Battery monitoring
- [x] Alarm scheduling
- [x] Tailscale networking

### Planned (Phase 3+)
- [ ] Adaptive volume (measure ambient noise, scale output)
- [ ] Talk-over ducking (pause output if user talks)
- [ ] Status LEDs (visual feedback for state)
- [ ] Manual button (alarm dismiss, reset)

## Battery Life & Monitoring

**On mains power**:
- Always charging via TP5000
- LFP tolerates float charge indefinitely

**On battery**:
- Typical idle: 5-8mA (ESP32 light sleep + minimal display)
- Speaking: 50-100mA (amplifier + WiFi active)
- **Target**: 12-hour survival time
- **Reality**: ~15-18 hours on 3000mAh under typical use

**Monitoring**:
- TP4056 status pin → Read charge state (on mains vs on battery)
- ADC voltage reading → Battery voltage (3.2-3.65V)
- Calculated: Remaining time based on voltage curve

## Dashboard Integration

The [[dashboard]] displays per-Clock:
- **Charge state**: "On mains" or "On battery"
- **Voltage**: Raw cell voltage
- **Uptime**: Seconds since last boot
- **Headline metric**: "On battery, 6h 30m remaining" (not %)

**Why not percentage?** LFP discharge curve is flat. Percentage is near-useless; time-on-battery is actionable.

## Dependencies

**Internal**:
- [[brain]] — LLM calls, TTS, complex intent
- [[networking]] — Tailscale mesh
- [[voice-io]] — TTS fallback (Piper)
- [[wake-word]] — Wake word detection

**External APIs**:
- Sonic API (TTS)
- Whisper API (STT, optional; can use local)

## Failure Modes

| Scenario | Behavior | Recovery |
|----------|----------|----------|
| Power cut | Clock on battery, alarm works | [[brain]] boots when power returns |
| WiFi down | Clock still functional (Tailscale cached) | Re-sync when WiFi returns |
| [[brain]] offline | Clock still listens, can't execute complex tasks | Queued requests when [[brain]] back |
| Battery dead | Clock stops, needs charging | Plug in or replace cell |
| Microphone fail | Can't hear commands | Manual commands via button |

## Next Steps (Phase 3)

- [ ] Order ESP32-S3 board
- [ ] Assemble power system (charger, boost, battery)
- [ ] Solder microphone, speaker, display
- [ ] Flash MicroLink firmware
- [ ] Test wake word detection
- [ ] 3D print enclosure
- [ ] Test battery life under load
- [ ] Join [[brain]] to Tailscale first (Phase 1)
