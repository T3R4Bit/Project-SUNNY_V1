# Project SUNNY — Quick Start

Get started in 30 seconds.

## 1. Make Executable
```bash
chmod +x run.sh
```

## 2. Run
```bash
./run.sh
```

**Done!** Server starts at `http://127.0.0.1:5000`, which redirects to the console at `http://127.0.0.1:5000/console`

No manual Python setup needed — `run.sh` creates and manages its own virtual environment automatically on first run.

## Commands

```bash
./run.sh # Start web server (default)
./run.sh chatbot # Console, non-reload mode
./run.sh reload # Web server with auto-reload (local dev only)
./run.sh chat # Terminal chat — same router as everywhere else, no browser
./run.sh cli briefing # Interactive briefing CLI
./run.sh cli tasks # Interactive task CLI
./run.sh test all # Run all tests
./run.sh dev # Dev shell (auto-managed venv pre-activated)
```

## Try in the Console

```
help → What Sunny can do
setup → What's connected, what needs setup
morning → Morning briefing
show my tasks → List tasks
add Title to my tasks → Create task
mark Title as done → Complete a task
add milk to my grocery list → Add to a list (creates it if new)
what's on my grocery list → Show a list
set an alarm for 7am → Create an alarm
remind me to call Mom at 5pm → Create a reminder
add dentist appointment to my calendar at 3pm tomorrow → Real Google Calendar event
cancel dentist appointment from my calendar → Deletes it (no confirmation step)
play Reptilia by The Strokes → Spotify playback (needs "setup spotify" first)
new project → Answer 3 quick questions, get a real project folder drafted
set up my classes → Paste a syllabus, get recurring calendar events + reminders
study review for BUS 2100 → Night-before review from your real class notes
storm mode → Live web-searched weather updates on a timer, not the API
health check → Latest weekly report (or triggers one on demand)
What's the weather? → Weather info
Tell me a joke / what's the capital of France → Anything open-ended gets
                                a real answer from Claude, not a canned reply
```

Everything above also works as plain-text chat in Sunny's Discord channel — same router, same answers, no separate setup.

## Discord-Only Slash Commands

Real registered slash commands, no plain-text equivalent:

```
/speak <text>     → Sunny says it out loud in the channel (one-shot, no
                    need to be in a voice channel)
/classsetup       → Start the class-setup wizard (paste a syllabus per class)
/category         → Add or remove a task category
/service, /services → Enable/disable a background service, check status
/vacation         → Pause proactive morning/evening nudging
/usage            → Chart of Claude API cost over the last N days
/version          → Show the commit Sunny is currently running
/ip               → Paste the Lenovo box's current Tailscale IP + console link
```

## Talk to Sunny in Discord Voice

No join command — Sunny stays connected to whatever channel is set as
`DISCORD_VOICE_CHANNEL_ID`, automatically, all the time. Toggle it with
`/service voice_join enable|disable`. See
`sunny-vault/docs/architecture/voice-join.md` and `tts-piper.md` for how
it works under the hood.

Say **"Hey Sunny"** before every request — there's no listening window,
each request needs its own wake word (this is deliberate: an always-
listening open mic reacting to any speech in the channel isn't what
persistent presence means here). A short chime confirms she heard the
wake word before you keep talking. Everything you say routes through the
exact same brain as text chat — tasks, lists, alarms, weather, calendar,
and open-ended questions all work the same way, just spoken back instead
of typed, and recent exchanges are remembered within the conversation so
a real follow-up ("what about tomorrow") makes sense.

Entirely local and free (Piper for speech out, Vosk for speech in) — no
API cost either direction, only the LLM fallback for open-ended
questions costs anything, and that's the same Claude Haiku call text
chat already uses.

## Access from Phone

1. Phone on Tailscale mesh
2. Open: `http://100.117.41.53:5000`
   (or `http://sunshine-m700:5000`)

## Troubleshooting

**Port in use?**
```bash
nano run.sh # Edit file
# Change: --port 5000 to --port 5001
./run.sh
```

**Something broken after an update?**
`run.sh` manages its own virtual environment — you never create or activate it yourself. If dependencies get into a bad state, just delete the auto-created folder and let the launcher rebuild it:
```bash
rm -rf venv
./run.sh
```

**Update packages?**
```bash
./run.sh dev
pip install --upgrade -r requirements.txt
exit
```

## Full Setup

See [SETUP_LINUX.md](SETUP_LINUX.md) for complete installation and deployment guide.

Enjoy!
