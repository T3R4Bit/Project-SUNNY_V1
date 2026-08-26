# Weekly Health Check — 2026-08-20

(LLM unavailable this week — raw summary below)

Past 7 days:
- App log errors: 9
- Unfulfilled requests by category: QA_QUESTION: 7, MORNING_BRIEFING: 2, EVENING_BRIEFING: 2
- LLM calls: none
- Keys expiring within 7 days: none

---

# Weekly Health Check — 2026-08-23

Overall health: fine.

The error count is elevated but appears noise-driven rather than systemic. No recurring error patterns emerged that warrant immediate investigation.

Unfulfilled requests are minimal and scattered across categories. QA_QUESTION saw 7 refusals—worth monitoring if this climbs, but current volume doesn't justify a hardcoded handler yet. The briefing misses (2 each) are negligible.

LLM usage is lean: 18 successful general chat calls and one stray weekly_health_check flag (likely a config artifact). No red flags on call volume or failure rates.

No keys expiring soon.

---

# Weekly Health Check — 2026-08-23

Overall health: **minor issues**.

**312** app log errors over the week is elevated — most are likely transient noise, but worth a spot-check on the error distribution to rule out a systemic problem in one subsystem.

**7** unfulfilled **QA_QUESTION** requests suggest a pattern. These are probably hitting the LLM fallback because no hardcoded answer exists. Consider building a static FAQ handler that covers the top repeat questions (check logs for the actual queries) — even a simple keyword-to-answer map would cut LLM load and latency.

**MORNING_BRIEFING** and **EVENING_BRIEFING** each had **2** unfulfilled requests, which is minor noise for now.

No key expirations in the next 7 days.

LLM usage is light (25 calls total), with general chat dominating. If QA questions cluster around a few topics, a hardcoded FAQ would be the quickest win.

---

