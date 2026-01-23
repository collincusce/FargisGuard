import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MOD_LOG_CHANNEL = "mod-logs"
NSFW_CHANNEL_NAME = "nsfw"
DASHBOARD_PORT = 8000

IMMUNE_ROLES = ["Admin", "Moderator"]
