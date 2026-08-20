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
- [ ] Single command/entry point that starts **all** services together (briefing engine, dashboard, task system, voice I/O, etc.) instead of launching each manually
- [ ] Per-service **toggle while running** — enable/disable an individual service (e.g. voice I/O, briefing scheduler) without restarting the whole Sunny process. Likely exposed via the dashboard and/or a CLI command.
- [ ] **Config for "start on Sunny launch" per service** — a settings file (e.g. `services.yaml` or a section in the existing config) marking each service as AutoStart-on-boot vs. manual-start-only, read at launch to decide what to bring up
- [ ] Location optimization. every time I ask for something and it needs my location it always pings my current location with my phone. But at a 30minute interval unless deemed immediate
      OR, find a completely free way to ping the location of my phone
- [ ] Storm mode: Only on request weather is no longer being pulled by the API, It switches to an LLM
      on activation it asks for an "update interval" and updates me on the current weather every interval IE 10min then also any updates or changes to the weather
      also asks for how long storm mode should be active for before auto updates turn off
- [ ] A vacation mode so that my local clock is not waiting every day for goodnight / morning
- [ ] morning prep, preps brief before My  alarm goes off to reduce delay, but Email is pulled right before alarm (5min max) to get the latest info
- [ ] Project system creates a project folder in obsidian under vault/project/project-name/ and asks for a short description of what it is (ALL OF THIS IS HARD CODED) with more then one variation of responses or questions to keep it human. then askes if you would like to build not NO = end of conversation, YES = all hard coded is done and chat switches to LLM
- [ ] ANY api with usage gets a chart  that is in its own discord channel with a leaderboard type screen (a persestant message that is a char)