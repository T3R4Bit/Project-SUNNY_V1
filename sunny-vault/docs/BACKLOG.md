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
- [ ] ANY api with usage gets a chart  that is in its own discord channel with a leaderboard type screen (a persestant message that is a chart that updates) and pings me in that channel when a token will expire or usage is running within 70% of my self imposed limit of spending
- [ ] All chats that were forced to an llm (except weather mode or project builds) get a copy of the message logged with a time stamp into the obsidian vault
- [ ] A system health function that runs once a week at sunday 4am (this is a llm) - compacts logs checks for any errors anything that was not phrased in hardcode and forced to switch to an LLM gets sent to me in discord as a report and a message to my good morning on sunday tells me to check it (not what it is) also checks if any api keys will expire within the next week also looks for way to improve the system with usage (try to keep low for usage)