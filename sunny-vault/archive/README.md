---
id: sunny-archive
type: reference
status: active
created: 2026-08-18
tags: [archive, history]
---

# Archive

Items that have been synced to Notion and moved here for local backup. Read-only reference.

## Structure

When items are pushed to Notion from `staging/`:

1. `staging/task-abc123.md` (status: `pending`)
2. → Notion API call succeeds
3. → File updated: `staging/task-abc123.md` (status: `synced`, notion_id: `xyz789`)
4. → File moved: `archive/task-abc123.md`

**Never delete from archive.** This is your local backup in case Notion becomes unavailable.

## File Retention

Keep everything. Archive never gets pruned.

## Sync Idempotency

Each archived item has an `id` and optional `notion_id`. If you need to re-sync:

1. Copy item back to `staging/`
2. Set status to `pending`
3. Run sync again — same `id` prevents duplicate creation

This is how retries work safely.

---

## Examples

```yaml
---
id: task-abc123def
type: task
status: synced
source: discord
created: 2026-08-18T14:30:00Z
notion_id: 550e8400-e29b-41d4-a716-446655440000
tags: [school, homework]
---

# Finish Physics Homework

Complete problems 1-20 from chapter 5.

**Status:** Done
**Priority:** 4/5
**Due:** 2026-08-20
**Completed:** 2026-08-19T16:45:00Z
```
