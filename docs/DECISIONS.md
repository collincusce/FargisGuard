# Decisions

Project-wide architectural decision records (ADRs). Append-only. Numbered `D-NNN`.
Each entry carries a `**Status**` (`active` | `superseded` | `deprecated`). When a
decision supersedes another, the predecessor stays in the record — annotated in place
with a `**Superseded by**: D-NNN` back-ref and `**Status**: superseded` — so the
lifecycle is navigable and the current decision is the one that surfaces.

## Decisions

_(Add entries with `cz_add_decision`.)_

### D-001 — LLM classifier emits a pipe-delimited verdict per message

**Context**: Every non-bot guild message is sent to OpenAI chat completions with the guild's rules in the system prompt (ai_engine.py). The model is instructed to answer exactly VIOLATION|<severity 1-4>|<reason> on a violation.
**Decision**: Use gpt-4o-mini as the per-message moderation classifier with a text verdict protocol parsed by bot.py.
**Consequences**: Moderation quality and safety are bounded by prompt adherence; the verdict must be parsed defensively and must not be treated as sole authority for irreversible actions (see H-NN findings).
**Evidence**: ai_engine.py, bot.py
**Status**: active (2026-09-06)

### D-002 — SQLite single-file store for warnings, rules, and appeals

**Context**: The bot runs as one process on one EC2 host (README). database.py opens moderation.db with check_same_thread=False and creates three tables.
**Decision**: Persist all moderation state in a local SQLite file; *.db is gitignored.
**Consequences**: No external DB dependency; concurrency must be handled by the app (one process, but two threads: bot loop + dashboard).
**Evidence**: database.py, .gitignore, README.md
**Status**: active (2026-09-06)

### D-003 — Severity ladder maps 1..4 to warn, timeout, kick, ban

**Context**: moderation.py maps the model's severity integer to a Discord action and increments the user's warning count.
**Decision**: Severity 1=DM warning, 2=15-minute timeout, 3=kick, 4=ban; Admin/Moderator roles are immune.
**Consequences**: Severity 3 and 4 are irreversible from the user's side; who may trigger them and how they are reviewed is a security-critical question.
**Evidence**: moderation.py, config.py
**Status**: active (2026-09-06)

### D-004 — NSFW content is isolated to a dedicated channel that bypasses AI moderation

**Context**: README lists human-supervised NSFW isolation; bot.py skips AI analysis entirely for the channel named in NSFW_CHANNEL_NAME.
**Decision**: One designated NSFW channel is exempt from the AI pipeline and relies on human moderation.
**Consequences**: The exemption test must be robust (Discord's channel NSFW flag, not a name string) or it becomes a moderation bypass.
**Evidence**: bot.py, config.py, README.md
**Superseded by**: D-007 (2026-09-06)
**Status**: superseded (2026-09-06)

### D-005 — Runtime secrets come from .env via python-dotenv

**Context**: config.py loads DISCORD_TOKEN and OPENAI_API_KEY from the environment; .env is gitignored; README says environment-based secrets.
**Decision**: All credentials are read from the environment at startup, never from source.
**Consequences**: config must fail fast when a required variable is absent; any credential found in the tree is a policy violation.
**Evidence**: config.py, .gitignore, README.md
**Status**: active (2026-09-06)

### D-006 — FastAPI moderation dashboard runs in-process beside the bot

**Context**: dashboard.py defines /infractions and /appeals; bot.py starts uvicorn in a thread from on_ready.
**Decision**: Serve the read-only dashboard from the same process on DASHBOARD_PORT.
**Consequences**: Shares the SQLite connection with the bot loop; must be started exactly once and must not be reachable unauthenticated from the internet.
**Evidence**: dashboard.py, bot.py, config.py
**Status**: active (2026-09-06)

### D-007 — NSFW channels receive a permissive scoped ruleset, not an AI bypass

**Context**: D-004 exempts NSFW-flagged channels from classification entirely (pipeline.py:94 returns "exempt" before analyze runs). Scoped rules require the classifier to run in NSFW channels so that nudity can be allowed while CSAM and animal harm remain forbidden. This also means prompt injection becomes possible in the highest-stakes channel for the first time; the safety floor decision addresses that.
**Decision**: Remove the pre-analysis NSFW short-circuit. An NSFW-flagged channel is resolved like any other scope; a guild that wants the old behaviour writes a permissive channel-scope rule. The NSFW flag (INVARIANT-05) remains the only signal used to identify such channels — never the name.
**Consequences**: docs/SECURITY.md threat model changes: injection via message content in NSFW channels is now in scope. channels.is_exempt is retired from the pipeline. Existing guilds see NSFW channels classified for the first time; the runbook must say so. Gated by the safety-floor decision landing in the same release.
**Supersedes**: D-004
**Evidence**: pipeline.py:94-95, channels.py:4-11, security lens finding #1
**Status**: active (2026-09-06)

### D-008 — A hard safety floor lives outside mod-writable rules text and cannot be relaxed by any scope

**Context**: Composed scope text is concatenated from up to four authored fragments. neutralize_tags (ai_engine.py:32) only prevents tag-closing; it establishes no precedence between fragments, so a narrower-scope rule could semantically override a guild safety rule. Categories such as CSAM and animal harm must be unremovable regardless of what any moderator types at any scope.
**Decision**: The floor is operator-controlled (code/config, never a database row any authoring command can write). It is rendered in its own tagged prompt region, structurally separate from the composed <rules> block, always present, appended never substituted. Composition precedence: the floor is absolute; among mod-authored fragments the most specific scope wins for allowances only. Tests must prove that no combination of scope text removes the floor from the built payload.
**Consequences**: A new invariant candidate for INVARIANTS.md once implemented. Whether the floor additionally needs an independent classification pass that ignores scoped rules (a stronger-than-prompt guarantee) is an open item for the token-architecture gameplan, since it doubles calls.
**Evidence**: ai_engine.py:19-46, security lens findings #2 #4 #7
**Status**: active (2026-09-06)

### D-009 — Rules are scoped guild → category → channel → thread, keyed by Discord IDs, composed deterministically, and identified by content hash

**Context**: Discord (discord.py 2.3.2, verified from installed source) has no nested threads: a Thread's parent is always a TextChannel or ForumChannel. "Thread depth" is therefore binary — in a channel, or in a thread of that channel. Batching and prompt caching (later gameplan) need a stable identity for "these messages share the same rules"; two channels that inherit identical text should share one batch and one cache prefix.
**Decision**: Scopes are exactly: guild default, category (category_id), channel (channel_id), thread (the channel's threads collectively). Rows are keyed by Discord snowflake IDs, never names (INVARIANT-05). Composition renders fragments in the fixed order guild → category → channel → thread with byte-stable whitespace and joins. The resolved-ruleset key is sha256 of the composed text, not the scope tuple; the scope tuple → (text, hash) mapping is memoized in-process and invalidated by a per-guild version counter bumped on every rules write, including the default-seeding insert.
**Consequences**: Cardinality of distinct rulesets is bounded by channel count (×2 for thread scope), realistically ~categories+1. Per-channel customisation fragments the future batch pool; that gameplan must time-box flushes per bucket. rules.get_rules(guild_id) survives as a guild-only compatibility wrapper. analyze receives scope IDs as additive optional kwargs to keep the test blast radius mechanical (~15-20 of 148).
**Evidence**: discord/threads.py in installed discord.py 2.3.2; cost lens findings #1-#4; migration lens finding #4
**Status**: active (2026-09-06)

### D-010 — Scope resolution fails closed: an unresolvable scope link is a mod-log error, never a silent fallback

**Context**: Thread.category raises discord.ClientException when the parent channel is not cached; category_id can be None; channels can be deleted between receipt and resolution. Today is_exempt runs outside the try/except at pipeline.py:94, so a raising channel probe already escapes INVARIANT-03. Silently resolving a failed lookup to "guild default only" would produce a plausible verdict with no signal anything went wrong — a quieter fail-open than an exception.
**Decision**: The resolver runs inside the pipeline's fail-closed boundary. Absence is not failure: a channel with no category resolves to guild+channel; a scope with no authored row contributes nothing. But an exception or a dangling reference (thread whose parent_id resolves to None) is an error posted to mod-log via error_notice, and the message is left for a human. DMs never reach the resolver (pipeline.py:92 already returns before it).
**Consequences**: Moving the channel probe inside the try fixes the pre-existing INVARIANT-03 gap. Forum-channel posts (thread whose parent is a ForumChannel) need an explicit resolver case — tracked as an open item.
**Evidence**: pipeline.py:92-103, discord.py 2.3.2 threads.py category property, security lens finding #5
**Status**: active (2026-09-06)
