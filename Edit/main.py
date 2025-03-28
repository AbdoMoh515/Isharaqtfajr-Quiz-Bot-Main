import asyncio
import logging
import signal
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

from config import TELEGRAM_TOKEN, LOG_CHANNEL_ID
from handlers import (start_command,help_command,handle_pdf_file,handle_forwarded_quiz,finish_quiz_batch)

# Initialize logging
logger = logging.getLogger(__name__)

# Initialize bot with default properties
bot = Bot(
    token=TELEGRAM_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# Register handlers - FIXED: Properly await the handler
dp.message(Command("start"))(start_command)
dp.message(Command("help"))(help_command)
dp.message(Command("finish"))(finish_quiz_batch)
dp.message(lambda m: m.document)(handle_pdf_file)
dp.message(lambda m: m.forward_origin and m.poll and m.poll.type == 'quiz')(handle_forwarded_quiz)

# Enhanced error handler
@dp.error()
async def error_handler(event, exception):
    error_message = (
        f"❌ Exception in handler {event.handler.__name__ if hasattr(event, 'handler') else 'unknown'}:\n"
        f"Type: {type(exception).__name__}\n"
        f"Message: {str(exception)}"
    )
    logger.error(error_message, exc_info=True)
    
    # Send error to the logging channel
    try:
        await bot.send_message(LOG_CHANNEL_ID, error_message)
    except Exception as e:
        logger.error(f"Failed to send error to log channel: {e}")

async def main():
    logger.info("✅ Bot is starting...")
    
    # Send startup notification
    try:
        await bot.send_message(LOG_CHANNEL_ID, "🚀 Bot has started successfully!")
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")

    await dp.start_polling(bot)

async def shutdown(signal, loop):
    """Safely shutdown the bot when receiving termination signal"""
    logger.warning(f"Received {signal.name} signal...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    if tasks:
        logger.info(f"Cancelling {len(tasks)} pending tasks...")
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        
    logger.info("Bot shutdown successful!")
    loop.stop()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.get_event_loop()
    
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: asyncio.create_task(shutdown(s, loop))
            )
        except NotImplementedError:
            pass
    
    try:
        loop.run_until_complete(main())
    except Exception as e:
        logger.critical(f"Fatal error in main loop: {e}")
    finally:
        logger.info("Closing event loop")
        loop.close()