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
**Superseded by**: D-013 (2026-09-07)
**Status**: superseded (2026-09-07)

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

### D-011 — The classifier runs on Anthropic Claude: Haiku 4.5 for every batch, Sonnet 5 as a re-check tier before any held action

**Context**: The prototype classifies with OpenAI gpt-4o-mini one message at a time. The operator asked for Claude with a smaller model for moderation. Per the bundled claude-api reference (cached 2026-06-24): Haiku 4.5 is $1/$5 per MTok and accepts temperature; Sonnet 5 is $2/$10 and rejects any non-default temperature/top_p/top_k (400), runs adaptive thinking unless disabled, and supports thinking disabled. Structured outputs (output_config.format json_schema) are supported on both. INVARIANT-02 already requires a human for kick/ban; a stronger second opinion before the hold is cheap insurance at ~5% of traffic.
**Decision**: ai_engine talks to the Anthropic Messages API through AsyncAnthropic. Every batch is classified by claude-haiku-4-5 (temperature 0, no thinking parameter, structured JSON output). Any verdict of severity >= 3 is re-checked one message at a time by claude-sonnet-5 (temperature omitted, thinking disabled, effort default) before the pending action is created; if the re-check disagrees downward the lower severity applies, if it fails the original verdict stands and the failure is logged (fail closed, INVARIANT-03). Model ids are constants, never date-suffixed. The OpenAI dependency stays pinned one release for rollback and is removed after.
**Consequences**: ANTHROPIC_API_KEY replaces OPENAI_API_KEY (one-release fallback with a warning). Tests use a FakeAnthropic whose response carries content blocks, stop_reason, and usage.input/output/cache_read/cache_creation tokens. INVARIANT-04's wording ("Discord or OpenAI") is generalised by INVARIANT-06. ext.openai-api is retired in favour of ext.anthropic-api. Haiku 4.5's support for the thinking parameter is undocumented in the reference; it is simply not sent.
**Evidence**: claude-api skill: python/claude-api/README.md (client, pricing example), shared/error-codes.md (model-specific 400s), shared/model-migration.md §Sonnet 5 sampling parameters, shared/tool-use-concepts.md line 482 (structured outputs models)
**Status**: active (2026-09-07)

### D-012 — Messages are classified in batches per (guild, ruleset key) on a moderator-set interval; strict batching, no content-based fast path

**Context**: Roughly 92% of each per-message request is the fixed prefix (instructions, floor, rules). The composed ruleset key (D-009) lets messages that share rules share a request. The operator chose strict batching: Discord AutoMod already handles keyword filtering, and the model's job is the ambiguous content a keyword list cannot classify, so a local fast path would add nothing. Batching opens an exposure window: a severe message stays visible until its bucket flushes.
**Decision**: on_message enqueues a snapshot (message id, channel, author, content, jump_url) into an in-process bucket keyed by (guild_id, ResolvedRules.key); the bucket freezes the ResolvedRules.text it was created with. A bucket flushes when its guild's interval elapses since the first enqueue or when it reaches the size cap, whichever first; the timer is per bucket. The interval is a per-guild setting (0 = classify per message, the pre-batching behaviour) clamped to a system ceiling BATCH_MAX_SECONDS; the size cap is a system constant. Verdicts are applied in original message order. There is no content-based fast path.
**Consequences**: Moderator-facing copy must state the trade-off ("reviewed in batches of up to N seconds; a severe message may stay visible until then"). Escalation ladders within a batch exactly as it would across sequential messages. A hard cap bounds the worst case; the operator accepted this for floor-tier content too. The queue is in-memory: graceful shutdown flushes it, a hard crash loses it — durable queueing is an open item, not a silent assumption.
**Evidence**: batching lens findings F3, F6, F8, F9; operator answer 2026-09-06 ("strict batching, no fast path — Discord already offers word filtering")
**Status**: active (2026-09-07)

### D-013 — Batch verdicts are structured JSON keyed by message id; an id that is missing, duplicated, or malformed fails closed for that message only

**Context**: D-001's single pipe-delimited line cannot carry N verdicts, and a batch multiplies the blast radius of one malformed reply to N messages (INVARIANT-02). Structured outputs (output_config.format with a json_schema; additionalProperties:false on every object; no numeric/length constraints) are supported on Haiku 4.5 and Sonnet 5 and guarantee the first text block is schema-valid JSON.
**Decision**: The classifier receives each message as <message id="N"> inside the user turn and must return {"verdicts":[{"id":N,"result":"OK"|"VIOLATION","severity":1-4|null,"reason":string}]} via output_config.format. The parser builds an id→verdict map with the same field validation as parse_verdict (integer severity 1..4, non-empty reason). Any expected id that is absent, appears more than once, or fails validation is routed to the existing unparseable_notice path for that message alone; unexpected ids are ignored and logged. stop_reason other than end_turn (max_tokens, refusal, anything else) marks every id in the batch unparseable — never clean.
**Consequences**: Supersedes D-001. A garbled or empty reply degrades every message to "needs a human", never to "OK". The single-message path is a batch of one, so one code path serves both the per-message mode and the escalation re-check.
**Supersedes**: D-001
**Evidence**: batching lens F2; claude-api shared/tool-use-concepts.md §Structured outputs (lines 482-511); python/claude-api/README.md stop reasons table
**Status**: active (2026-09-07)

### D-014 — Prompt caching is deferred: the prefix is below Haiku 4.5's minimum cacheable size, so no cache_control is sent

**Context**: The gameplan brief asked to place the static prefix under prompt caching. The bundled reference (shared/prompt-caching.md, minimum-prefix table) puts the minimum cacheable prefix at 4096 tokens for Haiku 4.5 and 1024 for Sonnet 5. Our static system turn is ~300 tokens and a composed rules block 50-800, so the largest bucket reaches ~1100. Below the minimum a breakpoint silently writes nothing (cache_creation_input_tokens 0) and padding to reach it would cost more than it saves. The reference states outright that adding cache_control to a prefix under the minimum pays the write premium for zero reads.
**Decision**: No cache_control anywhere in this gameplan. The usage line logs cache_read_input_tokens and cache_creation_input_tokens anyway so the numbers are visible. Revisit only when a measured prefix (system turn plus rules) exceeds the minimum for the model that will read it — for example if the batch pass moves to Sonnet 5 and rules grow past ~700 tokens.
**Consequences**: The token win in this gameplan comes from batching alone (lens estimate: ~$0.275 → ~$0.095 per 1,000 messages on Haiku 4.5, plus ~$0.03 for a 5% Sonnet re-check; estimates from the reference's pricing example, unconfirmed against the live pricing page). The system-prompt layout stays static-first anyway so a future breakpoint needs no restructuring.
**Evidence**: claude-api shared/prompt-caching.md lines 87, 131, 133-140, 144; cost lens §2 and §6
**Status**: active (2026-09-07)
