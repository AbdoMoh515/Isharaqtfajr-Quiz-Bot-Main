import os
import logging


# Bot configuration
TELEGRAM_TOKEN = ("7231699684:AAHYGk2j-CbpxTUkFUEMyqq5My5jwXKthQE")
LOG_CHANNEL_ID = int(os.getenv("LOG_CHANNEL_ID", "-1002300659776"))

# Rate limiting
MIN_INTERVAL_BETWEEN_FILES = 60  # seconds

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Validate configuration
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is not set in environment variables")