import os
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
CENTML_API_KEY = os.environ.get("CENTML_API_KEY")

if not SLACK_SIGNING_SECRET or not SLACK_BOT_TOKEN or not CENTML_API_KEY:
    logger.error("One or more required environment variables are missing.")
    raise ValueError(
        "Missing environment variables: SLACK_SIGNING_SECRET, SLACK_BOT_TOKEN, CENTML_API_KEY"
    )
