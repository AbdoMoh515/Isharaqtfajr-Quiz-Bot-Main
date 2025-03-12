
import asyncio
import logging
import signal
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

from config import TELEGRAM_TOKEN, LOG_CHANNEL_ID
from handlers import start_command, help_command, handle_document

# Initialize logging
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
from aiogram.client.default import DefaultBotProperties
bot = Bot(token=TELEGRAM_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Register command handlers
dp.message(Command("start"))(start_command)
dp.message(Command("help"))(help_command)

# Register document handler
@dp.message(lambda message: message.document)
async def document_handler(message: types.Message):
    await handle_document(bot, message)

# Register error handler
@dp.error()
async def error_handler(exception):
    error_message = f"❌ Exception raised: {exception}"
    logger.error(error_message)
    # Send error to the logging channel
    try:
        await bot.send_message(LOG_CHANNEL_ID, error_message)
    except Exception as e:
        logger.error(f"Failed to send error to log channel: {e}")

async def main():
    """Start the bot"""
    logger.info("✅ Bot is now running...")
    
    # Send startup notification
    try:
        await bot.send_message(LOG_CHANNEL_ID, "🚀 Bot has started successfully!")
    except Exception as e:
        logger.error(f"Failed to send startup notification: {e}")
        
    # Start polling
    await dp.start_polling(bot)

async def shutdown(signal, loop):
    """Safely shutdown the bot when receiving termination signal"""
    logger.warning(f"Received {signal.name} signal...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    if tasks:
        logger.info(f"Waiting for {len(tasks)} tasks to complete...")
        await asyncio.gather(*tasks, return_exceptions=True)
        
    logger.info("Bot shutdown successful!")
    loop.stop()

if __name__ == "__main__":
    # Setup signal handlers for safe shutdown
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
            # Signal handling not supported on Windows
            pass
    
    try:
        loop.run_until_complete(main())
    finally:
        logger.info("Closing event loop")
        loop.close()
