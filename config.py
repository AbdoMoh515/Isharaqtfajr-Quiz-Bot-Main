
import os
import logging

# Bot configuration
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
DEFAULT_GROUP_ID = int(os.environ.get("GROUP_ID", 0))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", 0))

# Available groups for sending quizzes
AVAILABLE_GROUPS = {
    "إشراقة فجر اولى بشري": int(os.environ.get("GROUP_ID_1", "0")),
    "المجموعة الثانية": int(os.environ.get("GROUP_ID_2", "0")),
    "المجموعة الثالثة": int(os.environ.get("GROUP_ID_3", "0")),
}

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
