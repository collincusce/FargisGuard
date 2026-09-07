---
id: ext.anthropic-api
type: external-service
status: active
last_verified: 2026-09-07
provider: Anthropic
purpose: "Moderation classifier: claude-haiku-4-5 for batches, claude-sonnet-5 re-check tier (D-011); Messages API via anthropic 1.4.0 (httpx2)"
auth: ANTHROPIC_API_KEY from the environment (INVARIANT-01)
---

# Anthropic API

Messages API through `anthropic` 1.4.0 (`httpx2`). `ai_engine.classify_batch`
sends one request per bucket with `output_config.format` = the verdict schema;
`claude-haiku-4-5` for batches, `claude-sonnet-5` (thinking disabled, no
sampling parameters) for the severity-3/4 re-check. Auth from
`ANTHROPIC_API_KEY` only. Every request logs the four usage counters at DEBUG.
