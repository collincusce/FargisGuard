# token-architecture — Phase Status Tracker

> Living document. Updated after each phase completes.
> Last updated: 2026-09-07

## Phase Status

| Phase | Name | Status | Started | Completed | Handoff |
|-------|------|--------|---------|-----------|---------|
| 0 | Bootstrap | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-0-HANDOFF.md |
| 1 | Batch verdict protocol | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-1-HANDOFF.md |
| 2 | Anthropic engine | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-2-HANDOFF.md |
| 3 | Batch queue | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-3-HANDOFF.md |
| 4 | Batch settings and commands | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-4-HANDOFF.md |
| 5 | Escalation re-check tier | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-5-HANDOFF.md |
| 6 | Release readiness | ✅ COMPLETE | 2026-09-07 | 2026-09-07 | handoffs/PHASE-6-HANDOFF.md |

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

### Phase 3 Outputs

```
batcher_api: batcher.Batcher(classify, apply, guild_for, log_to, max_messages=25, clock, sleep, spawn): enqueue(snapshot, rules: ResolvedRules, interval) -> 'queued'|'queued-flush' (sync); depth(guild_id=None); flush_now(guild_id=None); shutdown(deadline=20s) -> unreviewed count. Bucket(guild_id, rules, interval, generation, opened_at, snapshots, timer). pipeline.Deps gained batcher, interval_for (default no_batching -> 0), resolve_rules, clock; handle_message returns 'queued'/'queued-flush' on the batch path. pipeline.apply_outcome(snap, outcome, guild, deps, *, held) and delete_by_id. moderation.punish(existing_pending_id=) + record_history_only; database.append_pending_reason. FargisGuard(deps, classifier=classify_batch) builds its Batcher; close() awaits batcher.shutdown before super().close(). create_bot(interval_for=...) for Phase 4.
test_count_after_phase_3: 284 passed (262 + 22 in tests/test_batcher.py); ruff check clean
```

### Phase 4 Outputs

```
test_count_after_phase_4: 304 passed (284 + 20 in tests/test_batchsettings.py); ruff check and format clean
batch_settings_api: batchsettings.py: BATCH_MAX_SECONDS=300; clamp_interval(seconds) (0 stays 0, else 1..300, ValueError on non-int/bool); get_batch_interval(guild_id) -> 0 default; set_batch_interval(guild_id, seconds) -> stored; set_reply/show_reply(guild_id, depth) with EXPOSURE_NOTE. Table batch_settings(guild_id PK, interval_seconds). /batch set <seconds> and /batch show, Administrator-only, guild-only; create_bot wires interval_for=get_batch_interval (default). Default for every guild is 0 = per-message until a moderator opts in.
```

### Phase 5 Outputs

```
test_count_after_phase_5: 321 passed (304 + 17 in tests/test_recheck.py); ruff clean
recheck_api: ai_engine.RECHECK_MODEL=claude-sonnet-5, RECHECK_AT=3; recheck(rules, content, *, client, ruleset_key) -> Outcome via classify_batch(model=RECHECK_MODEL, tier="recheck", thinking={"type":"disabled"}); build_request(..., thinking=) only adds the key when given. pipeline: Deps.recheck (None disables), RECHECK_AT, reconcile(original, second) pure (lower wins; equal/higher no change; CLEAN -> DISPUTED reason; failure -> "re-check failed" reason), with_recheck never raises; apply_outcome(rules_text=, ruleset_key=) and the batcher passes the bucket's frozen rules; create_bot(rechecker=recheck).
```

### Phase 6 Outputs

```
postmortem_inputs: ESTIMATES ONLY (reference pricing example, unconfirmed live — O-02): per 1,000 messages on Haiku 4.5, per-message ≈ $0.275 (250 in / 5 out each) → batched 25/request ≈ $0.095 (300 static + 200 rules + 25×25 in, 10 out per message) = ~65% less from amortisation alone; caching contributes 0 (D-014); Sonnet 5 re-check on ~5% adds ≈ $0.03 → ≈ $0.12 total. Measured baseline: STILL NONE (O-04 carried from the previous gameplan: 0 API requests in 30 days on the live deployment). First real numbers arrive from `journalctl -u fargisguard | grep 'classify tier='` after deploy with LOG_LEVEL=DEBUG.
test_count_after_phase_6: 321 passed in the working install and in a fresh venv built from requirements.txt + requirements-dev.txt (anthropic 1.4.0 + openai 2.54.0 + fastapi 0.141.1; pip check clean); ruff check and format clean
```

## Corrections Log

### C-01 — Phase 2

**Phase**: 2
**What gameplan said**: D-011: Haiku 4.5 requests carry temperature 0 (Sonnet 5 omits it).
**What was actually correct**: No request carries temperature. anthropic 1.4.0's typed messages.create signature has no temperature/top_p/top_k parameters (verified by introspection); the only route would be extra_body, which bypasses the SDK's typing for a knob the newer models reject anyway.
**Why**: Determinism for the classifier was a nice-to-have, not a requirement: structured output fixes the shape, and the verdict parser fails closed on anything malformed regardless of sampling. Omitting the parameter on both tiers keeps one request builder and avoids a per-model branch.
**Lesson**: Verify a planned request parameter against the installed SDK's signature (inspect.signature) before writing the decision, not after — the reference docs describe the API surface, the SDK pin decides what is expressible.
