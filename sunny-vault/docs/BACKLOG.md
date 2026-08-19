---
id: sunny-backlog
type: planning
status: active
created: 2026-08-18
tags: [backlog, later, deferred, planning]
---

# Later / Backlog

Items worth doing but not blocking the current phase. Pull items into [[phases.md]] when their dependencies are actually in front of you.

---

## Service Orchestration

**Problem**: Right now there's no single entry point that brings up every Sunny service together, and no way to manage them individually once running.

- [ ] Package Sunny as a **systemd unit** (`Restart=always`) so it survives crashes and starts on boot (
- [ ] Single command/entrypoint that starts **all** services together (briefing engine, dashboard, task system, voice I/O, etc.) instead of launching each manually
- [ ] Per-service **toggle while running** — enable/disable an individual service (e.g. voice I/O, briefing scheduler) without restarting the whole Sunny process. Likely exposed via the dashboard and/or a CLI command.
- [ ] **Config for "start on Sunny launch" per service** — a settings file (e.g. `services.yaml` or a section in the existing config) marking each service as autostart-on-boot vs. manual-start-only, read at launch to decide what to bring up

**Why this matters**: as more services get added (voice, telephony, wake word), starting/stopping them all by hand won't scale, and some services (e.g. telephony) may need to be disabled temporarily without killing the whole process.

**Touches**: [[dashboard]] (toggle UI), `sunny_code/main.py` (orchestration/entrypoint), `sunny_code/config.py` (per-service config), systemd unit file (new)
