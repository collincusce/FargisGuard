---
id: subsys.verdict
type: subsystem
version: 0.2.0
status: active
last_verified: 2026-09-07
documented_in: docs/ARCHITECTURE.md#verdict
key_files:
  - verdict.py
  - tests/test_verdict.py
  - tests/test_batch_verdict.py
---

# Verdict

Pure parsing of the classifier's reply; nothing here does I/O. Rejection
always means "a human should look", never "no violation" (INVARIANT-02).

- `parse_verdict(text) -> Verdict | None` — the single line
  `VIOLATION|<1-4>|<reason>` (D-001, kept for the single-message form).
- `VERDICT_SCHEMA` — the JSON schema for `output_config.format`:
  `{"verdicts": [{"id", "result": OK|VIOLATION, "severity", "reason"}]}`;
  every object `additionalProperties: false`, no numeric/length constraints.
- `parse_batch_verdicts(text, expected_ids) -> ParsedBatch` — one `Outcome`
  (`Verdict`, `CLEAN`, or `Unparseable(problem)`) per expected id (D-013).
  Missing, duplicated, or malformed ids fail closed individually; ids the model
  invented land in `unexpected_ids` and are never applied; a reply that is not
  JSON at all makes every id `Unparseable`.

Batch ids are 1-based positions within the request (see
`ai_engine.build_batch_user_turn`), not Discord snowflakes — short ids are
echoed reliably and the batcher maps them back to snapshots.
