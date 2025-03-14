
import asyncio
import logging
import signal
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import CallbackQuery

from config import TELEGRAM_TOKEN, LOG_CHANNEL_ID
from handlers import start_command, help_command, handle_document, user_file_data, user_states, AVAILABLE_GROUPS, process_file

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

# Register callback query handler for group selection
@dp.callback_query(lambda c: c.data and c.data.startswith("group_"))
async def group_selection_callback(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    
    # Extract group ID from callback data
    group_id = int(callback_query.data.split("_")[1])
    
    # Check if user has file data
    if user_id in user_file_data:
        file_data = user_file_data[user_id]
        
        # Acknowledge the callback query
        await callback_query.answer("✅ تم اختيار المجموعة")
        
        # Update the message to show selection
        group_name = next((name for name, gid in AVAILABLE_GROUPS.items() if gid == group_id), "المجموعة المحددة")
        await callback_query.message.edit_text(
            f"🔄 جاري معالجة الملف وإرسال الأسئلة إلى {group_name}..."
        )
        
        # Process the file with selected group
        try:
            await process_file(
                bot, 
                callback_query.message, 
                file_data['file_stream'], 
                file_data['file_extension'],
                group_id
            )
            
            # Clean up
            del user_file_data[user_id]
            if user_id in user_states:
                del user_states[user_id]
                
        except Exception as e:
            logger.error(f"Error processing file after group selection: {e}")
            await callback_query.message.reply(f"❌ حدث خطأ أثناء معالجة الملف: {str(e)}")
    else:
        await callback_query.answer("❌ انتهت صلاحية الملف، يرجى إعادة الإرسال", show_alert=True)

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
