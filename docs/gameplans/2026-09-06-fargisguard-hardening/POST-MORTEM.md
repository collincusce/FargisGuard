# FargisGuard Hardening — Post-Mortem

> Gameplan: 2026-09-06-fargisguard-hardening · Closed: 2026-09-06 · Kind: driven
> Result: all 8 phases complete; 13 of 14 hardening findings resolved in code;
> the rest are owner/deploy actions tracked as open items.

## Executive summary

FargisGuard was a working prototype whose README promised human-supervised AI
moderation, warning escalation, and appeals — while the code auto-banned on raw,
prompt-injectable model output, exposed its rules prompt and its dashboard to
everyone, crashed on timeouts, and shipped an EC2 private key in git. In eight
session-sized phases the bot was rebuilt around one principle — **the model
advises, a human decides** — with an offline test suite growing from 0 to 148
and every fix tied to a numbered finding. The product's shape is unchanged: same
subsystems, same SQLite file, same single process.

## What the gameplan got right

1. **Dependency order over narrative order.** Phasing by what-blocks-what
   (tooling → pure core → gateway → async pipeline → human gate → storage →
   appeals → docs) meant every phase had a green pre-flight to build on. Twice
   the work pulled a later task forward (per-call SQLite in Phase 4, echo removal
   in Phase 1) rather than build throwaway scaffolding on the old seam — each
   recorded as a correction (C-02, C-04).
2. **Pure functions at every boundary.** `parse_verdict`, `effective_severity`,
   `is_immune`, `is_exempt`, `build_messages` — each is a pure function with an
   exhaustive test table, so the security-critical logic is verified without a
   gateway or an API key (INVARIANT-04). The dependency-injected `Deps` made the
   whole message pipeline testable offline.
3. **Findings as the spine.** Every commit named the H-finding it closed; the
   HARDENING tracker moved open → partial → resolved with dated evidence, so the
   audit trail is the changelog.

## What the gameplan got wrong (and root causes)

1. **The requirements pins were quietly broken before we started.** `openai
   1.10.0` and `fastapi 0.110.0` could not import against current `httpx` — the
   old `bot.run()`-at-import hid it until Phase 2 made the module importable
   (H-13). *Root cause:* pinning direct deps only. *Fix:* bumped both, verified
   in a fresh venv; the standing lesson is to lock transitives for deployables.
2. **A bootstrap phase can't pass a test gate that requires tests.** `pytest`
   exits 5 with zero tests, failing pre-flight on exactly the repo state Phase 0
   exists to fix (C-01). *Fix:* downgraded the `tests` check to advisory for
   Phase 0 only, restored at its close. Surfaced as a Clauderizer friction dream.
3. **Rotation was assumed, not verified.** The owner rotated the leaked key
   mid-gameplan; issuing a new key does not prove the old one is dead (L-7).
   Captured as O-05 with the exact rejection command.

## Procedure improvements (feed forward)

- A bootstrap phase on a test-less repo should ship with the `tests` pre-flight
  pre-downgraded, not discovered on first run.
- "Verify in a fresh venv" belongs in the exit criteria of any phase that
  touches dependencies, not just the final one.
- Clauderizer itself: `clauderize init` writes `docs/GLOSSARY.md` as
  engine-owned vocabulary at the same path a project glossary would live, so
  `cz_onboard` reports it as permanently unseeded (two friction dreams filed).

## Open threads (not code — owner/deploy actions)

- **O-01 / O-05 (H-01):** rotate the EC2 key *and prove the old one is rejected*
  (`ssh -i FargisGuard.pem … echo` must return Permission denied). Owner reports
  rotation done; verification still outstanding — cannot be run from CI/sandbox.
- **O-02 (H-01):** scrub `FargisGuard.pem` from git history and force-push
  (rewrites `main`; owner decision). The key is removed from HEAD but remains in
  commit `55ceedd`.
- **O-03:** enable the Message Content + Server Members privileged intents.
- **O-04:** post-deploy smoke test on the live host (systemd restart, command
  sync, loopback-only dashboard).

## By the numbers

- Findings: 14 total (H-01..H-14 less numbering) — 13 resolved in code, H-01
  partially (tree cleaned; rotation/scrub are owner actions).
- Tests: 0 → 148, all offline. ruff clean. Verified in a fresh venv.
- Decisions: D-001..D-006 (project) + D1..D8 (gameplan). Corrections: C-01..C-04.
  Amendment: A-001. Lessons: 7 (4 promoted project-wide).
