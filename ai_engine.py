from openai import OpenAI
from config import OPENAI_API_KEY
from rules import get_rules

client = OpenAI(api_key=OPENAI_API_KEY)

async def analyze_message(content: str, guild_id: int) -> str:
    rules = get_rules(guild_id)

    system_prompt = f"""
You are a Discord moderation AI.

Server Rules:
{rules}

IMPORTANT:
- NSFW content is ONLY allowed in #nsfw
- NSFW outside #nsfw is a violation

If content violates rules, respond exactly:
VIOLATION|<severity 1-4>|<short reason>

Otherwise, respond helpfully.
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content}
        ]
    )

    return response.choices[0].message.content.strip()
