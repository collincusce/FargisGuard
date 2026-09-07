---
id: ext.openai-api
type: external-service
status: retired
last_verified: 2026-09-07
provider: OpenAI
purpose: Chat-completions classifier (gpt-4o-mini) that emits a VIOLATION|severity|reason verdict per message
risk: high
documented_in: docs/ARCHITECTURE.md#external-services
---

# OpenAI API (retired)

Was the chat-completions classifier (`gpt-4o-mini`, D-001). Replaced by
`ext.anthropic-api` in the token-architecture gameplan (D-011). The `openai`
package stays pinned for one release so `git checkout <previous-tag>` remains
a working rollback; drop the pin and this entity's last reference in the
release after that.
