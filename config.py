
import os
import logging

# Bot configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GROUP_ID = int(os.environ.get("GROUP_ID"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID"))

# Rate limiting
MAX_FILE_SIZE_MB = 10
MIN_INTERVAL_BETWEEN_FILES = 60  # seconds
FLOOD_WAIT_BASE = 30  # seconds

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)
