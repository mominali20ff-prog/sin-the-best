import os
from dotenv import load_dotenv

# Load a local .env file if present (useful for local testing).
# On Railway, you set BOT_TOKEN as a Variable instead of using a .env file.
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
PREFIX = os.getenv("PREFIX", ".")

# Default embed color (Discord "blurple"). Override with EMBED_COLOR env var, e.g. "FF0000"
EMBED_COLOR = int(os.getenv("EMBED_COLOR", "5865F2"), 16)

# Comma separated list of Discord user IDs that should always be treated as
# bot owners (bypass anti-nuke, can use owner-only commands), e.g. "123,456"
EXTRA_OWNER_IDS = [
    int(x) for x in os.getenv("EXTRA_OWNER_IDS", "").split(",") if x.strip().isdigit()
]

# How many "dangerous" actions (channel deletes, role deletes, mass bans, mass
# kicks) within ANTINUKE_WINDOW_SECONDS triggers the anti-nuke system.
ANTINUKE_THRESHOLD = int(os.getenv("ANTINUKE_THRESHOLD", "3"))
ANTINUKE_WINDOW_SECONDS = int(os.getenv("ANTINUKE_WINDOW_SECONDS", "10"))

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is not set. On Railway, add it under "
        "your service's Variables tab. Locally, put it in a .env file."
    )
