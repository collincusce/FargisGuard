"""Shared test setup.

The suite runs fully offline (INVARIANT-04). config.py validates required
secrets at import, so give it harmless placeholders before any module under
test imports it.
"""

import os

os.environ.setdefault("DISCORD_TOKEN", "test-discord-token")
os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")
