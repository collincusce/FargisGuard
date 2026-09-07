# token-architecture — Phase Status Tracker

> Living document. Updated after each phase completes.
> Last updated: 2026-09-07

## Phase Status

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Batch verdict protocol | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-1-HANDOFF.md |
| 2 | Anthropic engine | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-2-HANDOFF.md |
| 3 | Batch queue | ⬜ NOT STARTED | — | — | handoffs/PHASE-3-HANDOFF.md |
| 4 | Batch settings and commands | ⬜ NOT STARTED | — | — | handoffs/PHASE-4-HANDOFF.md |
| 5 | Escalation re-check tier | ⬜ NOT STARTED | — | — | handoffs/PHASE-5-HANDOFF.md |
| 6 | Release readiness | ⬜ NOT STARTED | — | — | handoffs/PHASE-6-HANDOFF.md |

## Outputs Registry

### Phase 0 Outputs

```
baseline_tests: 217 passed (pytest -q, 2026-09-07); Python 3.11.15, discord.py 2.3.2, openai 2.54.0, fastapi 0.141.1
fresh_venv_anthropic: anthropic 1.4.0 + openai 2.54.0 + fastapi 0.141.1 install clean in a fresh venv (httpx 0.28.1 and httpx2 2.12.0 coexist); pip check clean; 217 passed. Pin change itself lands in Phase 2.
```

### Phase 1 Outputs

```
batch_protocol_api: verdict.py: VERDICT_SCHEMA (output_config.format json_schema), CLEAN / Clean / Unparseable(problem) / Outcome, ParsedBatch(outcomes: dict[id, Outcome], unexpected_ids), parse_batch_verdicts(text, expected_ids). ai_engine.build_batch_user_turn(rules, contents) -> '<rules>…</rules>\n<messages>\n<message id="1">…' with batch-local 1-based ids. snapshots.py: MessageSnapshot(message_id, channel_id, guild_id, author_id, content, jump_url, created_at) + snapshot_of(message, now=).
test_count_after_phase_1: 251 passed (217 + 34 in tests/test_batch_verdict.py); ruff check clean
```

### Phase 2 Outputs

```
engine_api: ai_engine: MODEL=claude-haiku-4-5, REQUEST_TIMEOUT=30s, build_request(rules, contents, model=) -> kwargs {model, max_tokens=64+40*n, system, messages, output_config.format json_schema}; classify_batch(rules, contents, *, client, model, ruleset_key, tier) -> ParsedBatch (stop_reason != end_turn => all Unparseable; RateLimitError/APIStatusError/APIConnectionError logged + re-raised); analyze_message(...) -> Outcome (batch of one); get_client() raises ConfigError without ANTHROPIC_API_KEY. Pipeline Analyzer contract now returns verdict.Outcome. FakeAnthropic(reply, error, stop_reason, usage) + batch_reply/ok_entry/violation_entry helpers in tests/fakes.py. NO temperature anywhere (C-01: SDK 1.4.0 create() has no such parameter).
test_count_after_phase_2: 262 passed; ruff check clean; ruff format clean except the pre-existing tests/test_bot_wiring.py nit
```

## Corrections Log

### C-01 — Phase 2

**Phase**: 2
**What gameplan said**: D-011: Haiku 4.5 requests carry temperature 0 (Sonnet 5 omits it).
**What was actually correct**: No request carries temperature. anthropic 1.4.0's typed messages.create signature has no temperature/top_p/top_k parameters (verified by introspection); the only route would be extra_body, which bypasses the SDK's typing for a knob the newer models reject anyway.
**Why**: Determinism for the classifier was a nice-to-have, not a requirement: structured output fixes the shape, and the verdict parser fails closed on anything malformed regardless of sampling. Omitting the parameter on both tiers keeps one request builder and avoids a per-model branch.
**Lesson**: Verify a planned request parameter against the installed SDK's signature (inspect.signature) before writing the decision, not after — the reference docs describe the API surface, the SDK pin decides what is expressible.
