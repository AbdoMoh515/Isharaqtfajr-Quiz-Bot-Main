import logging
import os
import tempfile
from io import BytesIO
from datetime import datetime, timedelta
from typing import List, Dict, Any
from aiogram import Bot, types
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import Poll

from config import MIN_INTERVAL_BETWEEN_FILES
from utils import extract_text_from_pdf, extract_questions_from_text, send_telegram_quizzes, format_quiz_as_text

logger = logging.getLogger(__name__)

# Storage for temporary quiz batches
user_quiz_batches = {}
# Rate limiting
user_last_file_time = {}

async def start_command(message: types.Message):
    """Handle /start command"""
    await message.answer(
        "👋 مرحبًا بك في بوت تحويل الاختبارات!\n\n"
        "1. أرسل ملف PDF - احصل على اختبارات تفاعلية\n"
        "2. أعد توجيه الاختبارات - احصل على ملخص نصي\n\n"
        "استخدم /help للتعليمات"
    )

async def help_command(message: types.Message):
    """Handle /help command"""
    await message.answer(
        "📚 التعليمات:\n\n"
        "للملفات PDF:\n"
        "- أرسل ملف PDF يحتوي على أسئلة\n"
        "- التنسيق المطلوب:\n"
        "  السؤال\n"
        "  أ) الخيار الأول\n"
        "  ب) الخيار الثاني\n"
        "  الإجابة: أ\n\n"
        "لاختبارات التليجرام:\n"
        "- أعد توجيه الاختبارات إليّ\n"
        "- اكتب /finish عند الانتهاء\n"
        "- سيتم إرسال جميع الاختبارات في رسالة واحدة"
    )

async def handle_pdf_file(message: types.Message):
    """Process PDF file with improved error handling"""
    try:
        user_id = message.from_user.id
        
        # Rate limiting
        current_time = datetime.now().timestamp()
        if user_id in user_last_file_time:
            if (diff := current_time - user_last_file_time[user_id]) < MIN_INTERVAL_BETWEEN_FILES:
                await message.reply(f"⏳ يرجى الانتظار {int(MIN_INTERVAL_BETWEEN_FILES - diff)} ثانية")
                return
        
        user_last_file_time[user_id] = current_time

        # Validate PDF
        if not message.document.file_name.lower().endswith('.pdf'):
            await message.reply("❌ يرجى إرسال ملف PDF فقط")
            return

        processing_msg = await message.reply("🔄 جاري معالجة الملف...")

        # Download file
        file_stream = BytesIO()
        await message.bot.download(message.document, destination=file_stream)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_file:
            temp_file.write(file_stream.getvalue())
            temp_path = temp_file.name

        # Extract text
        text = await extract_text_from_pdf(temp_path)
        if not text.strip():
            await message.reply("❌ لم يتم العثور على نص في الملف")
            return

        logger.info(f"Extracted text:\n{text[:500]}...")

        # Extract questions
        questions = extract_questions_from_text(text)
        if not questions:
            await message.reply(
                "❌ لم يتم العثور على أسئلة\n\n"
                "تأكد من التنسيق:\n"
                "السؤال\n"
                "أ) الخيار الأول\n"
                "ب) الخيار الثاني\n"
                "الإجابة: أ"
            )
            return

        # Send as quizzes
        sent, failed = await send_telegram_quizzes(message.bot, questions, message.chat.id)
        await message.reply(
            f"✅ تم معالجة {len(questions)} سؤال\n"
            f"- تم إرسال: {sent}\n"
            f"- فشل في إرسال: {failed}"
        )

    except Exception as e:
        logger.error(f"PDF processing error: {e}", exc_info=True)
        await message.reply("❌ حدث خطأ أثناء معالجة الملف")
    finally:
        if 'temp_path' in locals() and os.path.exists(temp_path):
            os.remove(temp_path)
        if 'processing_msg' in locals():
            try:
                await processing_msg.delete()
            except:
                pass

async def handle_forwarded_quiz(message: types.Message):
    """Store forwarded quizzes temporarily"""
    try:
        if not (message.forward_origin and message.poll and message.poll.type == 'quiz'):
            return

        user_id = message.from_user.id
        if user_id not in user_quiz_batches:
            user_quiz_batches[user_id] = {
                'quizzes': [],
                'expires_at': datetime.now() + timedelta(hours=1)
            }

        quiz = message.poll
        user_quiz_batches[user_id]['quizzes'].append(quiz)

        count = len(user_quiz_batches[user_id]['quizzes'])
        await message.reply(
            f"📥 تم حفظ الاختبار ({count})\n"
            "اكتب /finish عندما تنتهي"
        )

    except Exception as e:
        logger.error(f"Quiz storage error: {e}", exc_info=True)
        await message.reply("❌ حدث خطأ أثناء حفظ الاختبار")

async def finish_quiz_batch(message: types.Message):
    """Send all stored quizzes as a single message"""
    try:
        user_id = message.from_user.id
        if user_id not in user_quiz_batches or not user_quiz_batches[user_id]['quizzes']:
            await message.reply("❌ لا توجد اختبارات محفوظة")
            return

        quizzes = user_quiz_batches.pop(user_id)['quizzes']
        message_text = "📝 الاختبارات المحفوظة:\n\n"
        
        for i, quiz in enumerate(quizzes, 1):
            quiz_text = await format_quiz_as_text(quiz)
            message_text += f"{i}. {quiz_text}\n\n"

        # Split if too long
        if len(message_text) > 4096:
            parts = [message_text[i:i+4000] for i in range(0, len(message_text), 4000)]
            for part in parts:
                await message.reply(part)
        else:
            await message.reply(message_text)

    except Exception as e:
        logger.error(f"Quiz batch error: {e}", exc_info=True)
        await message.reply("❌ حدث خطأ أثناء إنشاء الملخص")