---
id: sunny-voice-io
type: component
status: active
created: 2026-08-18
tags: [voice, audio, stt, tts, io]
---

# Voice I/O Pipeline

Audio input (speech-to-text) and output (text-to-speech) handling. Streams from [[clock]] microphone, processes on [[brain]], outputs back to [[clock]] speaker.

## Overview

```
Microphone (Clock)
    ↓
I2S Buffer → Audio Stream
    ↓
STT (Whisper or local Vosk)
    ↓
Text transcript → [[priority-queue]]
    ↓
Intent router → Action
    ↓
Response text
    ↓
TTS (Sonic API or Piper)
    ↓
Audio stream
    ↓
Speaker (Clock)
```

## Speech-to-Text (STT)

### Sonic API (Preferred)

- **Provider**: Sonic
- **Latency**: 0.5-2 seconds
- **Accuracy**: High (trained on general English)
- **Cost**: ~$0.01-0.02 per minute of audio
- **Fallback**: If API down, buffer audio, retry later

### Whisper (Alternative)

- **Provider**: OpenAI Whisper API
- **Latency**: 1-3 seconds
- **Accuracy**: Very high (multilingual)
- **Cost**: ~$0.02 per minute
- **Local option**: Run Whisper locally (requires compute, slower)

### Vosk (Budget/Offline)

- **Local inference**: No API calls (privacy)
- **Latency**: 1-5 seconds (CPU-bound)
- **Accuracy**: Medium (smaller model)
- **Cost**: Free
- **Use case**: Fallback if APIs down, or privacy-critical

### Selection

**Default**: Sonic API (fast, cheap, reliable)
**Fallback 1**: Whisper API (higher accuracy, slightly more expensive)
**Fallback 2**: Vosk local (free, works offline)

## Text-to-Speech (TTS)

### Sonic API (Preferred)

- **Provider**: Sonic
- **Latency**: 0.5-1 second per sentence
- **Voice**: Natural, human-like
- **Languages**: English + others
- **Cost**: ~$0.008 per 1000 characters (~$0.05-0.10 per briefing)
- **Streaming**: Returns audio chunks, start playing before full completion

**Example**: "Good morning. You have 3 events today..." → Start playing first sentence while computing next.

### Piper TTS (Fallback)

- **Local inference**: Runs on [[brain]], no API calls
- **Latency**: 2-5 seconds per sentence
- **Voice**: Robot-like but understandable
- **Cost**: Free (one-time model download ~200MB)
- **Use case**:
  - Sonic API is down
  - Long conversation (50+ minutes) → suggest switching to Piper to save cost
  - Privacy-critical situations

### Playback

- **Device**: [[clock]] speaker (3W 4Ω mini)
- **Streaming**: Audio chunks → Buffer → Play while next chunk arrives
- **Volume**: Start at normal, adapt based on ambient noise (planned)
- **Interruption**: Stop playback if user talks (talk-over ducking, planned)

## End-to-End Examples

### Simple Command

```
User: "Hey Sunny, what time is it?"
  ↓
Wake word detected (local, Clock)
  ↓
STT: Capture "what time is it?" (Sonic API, 0.5s)
  ↓
Intent: Time query (hardcoded pattern match)
  ↓
Action: Get system time (no LLM needed)
  ↓
Response: "It is 7:34 AM"
  ↓
TTS: Generate speech (Sonic API, 1s)
  ↓
Play audio (Clock speaker, 1s)
  ↓
Total latency: ~3 seconds
```

### Complex Conversation

```
User: "Tell me about my day"
  ↓
STT: "tell me about my day" (Sonic, 1s)
  ↓
Intent: Briefing request (hardcoded pattern)
  ↓
Action: Generate briefing (APIs, no LLM, 2-3s)
  ↓
Response: Entire briefing text (~300 words)
  ↓
TTS: Stream audio (Sonic, starts immediately, ~20s to complete)
  ↓
Playback: Starts after 1s, completed ~20s
  ↓
Total latency: 25-30 seconds
```

### Email Triage (with LLM)

```
User: "What's in my email?"
  ↓
STT: "what's in my email" (1s)
  ↓
Intent: Email summary
  ↓
Action: Fetch email headers (2s)
  ↓
LLM triage: Classify emails ([[llm-integration]], 2-5s)
  ↓
Response: "3 urgent, 5 action items, rest is FYI"
  ↓
TTS: Generate speech (3s)
  ↓
Play audio (3s)
  ↓
Total latency: 10-15 seconds (mostly LLM)
```

## Error Handling

**STT fails**:
- Retry up to 2 times (network may be flaky)
- After 2 retries: "I didn't catch that. Please repeat."
- Log error to Discord #warnings

**TTS fails**:
- Fall back to Piper TTS (slower but works)
- If Piper also fails: Text only (show on Clock display)
- Log to Discord #warnings

**Audio glitch** (speaker crackle, mic noise):
- Re-normalize audio levels
- Skip frame if corrupted
- Subtle artifacts acceptable; complete failure not

## Cost Optimization

**High-volume day** (50+ voice interactions):
- After 40 interactions: Suggest switching to Piper TTS
- Reduces TTS cost from $0.50+ to $0 for remainder
- User choice; LLM doesn't auto-switch

**Fallback logic**:
```python
if total_tts_cost_today > $0.50:
    suggest_piper_fallback()  # User can agree/decline

if tts_provider == "sonic" and api_fails:
    switch_to_piper()  # Automatic

if total_stt_cost_today > $0.50:
    # Just log warning, continue (calls are important)
```

## Adaptive Volume (Planned, Phase 3+)

**Ambient noise detection**:
- Before responding, sample room noise for 0.5s
- Measure dB level
- Scale speaker volume accordingly

**Example**:
- Quiet room (45dB) → Volume 60%
- Normal room (60dB) → Volume 75%
- Noisy room (75dB+) → Volume 90%

**Talk-over ducking** (planned):
- During TTS output, listen for voice
- If detected: Lower/pause TTS, wait for user to finish
- Resume after 1-2 second silence

## Dependencies

- [[clock]] — Microphone and speaker hardware
- [[brain]] — STT/TTS API calls, buffering
- [[networking]] — API access
- [[priority-queue]] — Request queuing (microphone input high priority)
- Sonic API — Preferred provider
- Whisper API — Fallback STT
- Piper — Local TTS fallback

## Implementation Checklist (Phase 4)

- [ ] Sonic API integration (STT + TTS)
- [ ] Whisper API fallback
- [ ] Piper TTS fallback (download model)
- [ ] I2S audio streaming (Clock ↔ Brain)
- [ ] Audio buffering + playback
- [ ] Error handling + retries
- [ ] Cost tracking
- [ ] Volume control
- [ ] Latency optimization
- [ ] Test with [[clock]] hardware
- [ ] Ambient noise measurement (prep for adaptive volume)
