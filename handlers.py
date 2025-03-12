
import asyncio
import logging
import csv
import os
import tempfile
from typing import Dict, Any, BinaryIO
from datetime import datetime
from io import BytesIO

from aiogram import Bot, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

from config import GROUP_ID, LOG_CHANNEL_ID, MIN_INTERVAL_BETWEEN_FILES
from utils import extract_text_from_pdf, extract_questions_from_text, send_paginated_quizzes

logger = logging.getLogger(__name__)

# Dictionary to store user rate limits
user_last_file_time: Dict[int, float] = {}

async def start_command(message: types.Message):
    """Handle /start command"""
    await message.answer(
        "👋 مرحبًا بك في بوت الاختبارات!\n\n"
        "يمكنك إرسال ملفات الأسئلة بصيغة CSV أو PDF لإنشاء اختبارات في المجموعة.\n"
        "استخدم الأمر /help للحصول على مزيد من المعلومات."
    )

async def help_command(message: types.Message):
    """Handle /help command"""
    help_text = (
        "📚 <b>دليل استخدام البوت</b>\n\n"
        "<b>الأوامر المتاحة:</b>\n"
        "/start - بدء استخدام البوت\n"
        "/help - عرض هذه المساعدة\n\n"
        "<b>أنواع الملفات المدعومة:</b>\n"
        "1. <b>CSV</b>: يجب أن يحتوي على عمود للسؤال، وأعمدة للخيارات، والعمود الأخير للإجابة الصحيحة.\n"
        "2. <b>PDF</b>: يجب أن يحتوي على أسئلة بتنسيق النص التالي:\n"
        "   السؤال\n"
        "   a) الخيار الأول\n"
        "   b) الخيار الثاني\n"
        "   ... إلخ\n"
        "   Answer: X\n\n"
        "<b>ملاحظات:</b>\n"
        "- يتم إرسال الأسئلة إلى المجموعة المحددة.\n"
        "- يجب أن يكون هناك فاصل زمني بين إرسال الملفات."
    )
    await message.answer(help_text, parse_mode=ParseMode.HTML)

async def process_file(bot: Bot, message: types.Message, file_stream: BinaryIO, file_extension: str) -> None:
    """
    Process uploaded file and send quizzes based on file type
    
    Args:
        bot: Telegram bot instance
        message: Original message with the file
        file_stream: File content as binary stream
        file_extension: File extension (csv or pdf)
    """
    temp_path = None
    try:
        # Create temporary file on disk
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}", mode="wb") as temp_file:
            temp_file.write(file_stream.getvalue())
            temp_path = temp_file.name

        await message.answer("✅ تم استلام الملف، جاري المعالجة...")

        if file_extension == "csv":
            await process_csv_file(bot, message, temp_path)
        elif file_extension == "pdf":
            await process_pdf_file(bot, message, temp_path)

    except Exception as e:
        error_message = f"خطأ في معالجة الملف: {str(e)}"
        logger.error(error_message)
        
        # Send detailed error to log channel
        try:
            await bot.send_message(
                LOG_CHANNEL_ID, 
                f"❌ Error processing file from user {message.from_user.first_name} ({message.from_user.id}):\n{str(e)}"
            )
        except Exception as log_err:
            logger.error(f"Failed to send error to log channel: {log_err}")
            
        # Send user-friendly message
        await message.reply("❌ حدث خطأ أثناء معالجة الملف. تم إبلاغ المسؤول بالمشكلة.")
    finally:
        # Delete temporary file
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

async def process_csv_file(bot: Bot, message: types.Message, file_path: str) -> None:
    """
    Process CSV file and send quizzes
    
    Args:
        bot: Telegram bot instance
        message: Original message with the file
        file_path: Path to CSV file
    """
    try:
        with open(file_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)
            
            if not rows:
                await message.reply("❌ الملف CSV فارغ!")
                return
                
            total_rows = len(rows)
            await message.reply(f"🔄 جاري معالجة {total_rows} سؤال من ملف CSV...")
            
            # Prepare questions in proper format
            questions = []
            for i, row in enumerate(rows):
                try:
                    if len(row) < 2:
                        logger.warning(f"Skipped row {i+1}: incomplete")
                        continue
                    
                    question = row[0].strip()
                    if not question:
                        logger.warning(f"Skipped row {i+1}: no question")
                        continue
                        
                    options = [opt.strip() for opt in row[1:-1] if opt.strip()]
                    correct_option = row[-1].strip()
                    
                    if not correct_option:
                        logger.warning(f"Skipped row {i+1}: no correct answer")
                        continue
                        
                    if len(options) < 1:
                        logger.warning(f"Skipped row {i+1}: not enough options")
                        continue
                    
                    # Make sure correct option is in options
                    if correct_option not in options:
                        options.append(correct_option)
                    
                    # Limit options to 10 (Telegram limit)
                    if len(options) > 10:
                        options = options[:10]
                        logger.warning(f"Trimmed options for question {i+1} to 10")
                    
                    if len(options) < 2:
                        options.append("لا أعرف الإجابة")
                    
                    questions.append({
                        "question": question,
                        "options": options,
                        "correct_option_id": options.index(correct_option)
                    })
                    
                except Exception as e:
                    logger.error(f"Error processing row {i+1}: {str(e)}")
            
            # Send questions with pagination
            if questions:
                sent_count, error_count = await send_paginated_quizzes(bot, questions, GROUP_ID)
                
                # Send final report
                await message.reply(
                    f"✅ اكتملت العملية!\n"
                    f"- تم إرسال: {sent_count} سؤال\n"
                    f"- تم تخطي: {error_count} سؤال"
                )
            else:
                await message.reply("❌ لم يتم العثور على أسئلة صالحة في الملف CSV.")

    except Exception as e:
        logger.error(f"Error processing CSV file: {str(e)}")
        raise

async def process_pdf_file(bot: Bot, message: types.Message, file_path: str) -> None:
    """
    Process PDF file and send quizzes
    
    Args:
        bot: Telegram bot instance
        message: Original message with the file
        file_path: Path to PDF file
    """
    try:
        # Extract text from PDF
        extracted_text = await extract_text_from_pdf(file_path)

        if not extracted_text.strip():
            await message.reply("❌ لم يتم العثور على أي نص داخل ملف PDF، تأكد من أن الملف يحتوي على أسئلة مكتوبة كنصوص وليس صور.")
            return
        
        # Send processing message
        processing_msg = await message.reply("🔍 جاري تحليل النص واستخراج الأسئلة...")
        
        # Extract questions
        questions = extract_questions_from_text(extracted_text)

        if not questions:
            # Send preview of extracted text to help diagnose the issue
            preview = extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
            logger.warning("No questions found in extracted PDF text")
            await processing_msg.delete()
            await message.reply(
                "❌ لم يتم العثور على أسئلة في الملف، يرجى التأكد من التنسيق الصحيح.\n\n"
                "أنماط الأسئلة المعتمدة هي:\n"
                "1. السؤال\n"
                "   a) الخيار الأول\n"
                "   b) الخيار الثاني\n"
                "   ...\n"
                "   Answer: a\n\n"
                "النص المستخرج من الملف (مقتطف):\n"
                f"<pre>{preview}</pre>",
                parse_mode=ParseMode.HTML
            )
        else:
            await processing_msg.delete()
            logger.info(f"Found {len(questions)} unique questions")
            await message.reply(f"✅ تم استخراج {len(questions)} سؤال فريد، سيتم إرسالها إلى المجموعة...")
            
            # Send questions with pagination
            sent_count, error_count = await send_paginated_quizzes(bot, questions, GROUP_ID)
            
            # Send final report
            await message.reply(
                f"✅ اكتملت العملية!\n"
                f"- تم إرسال: {sent_count} سؤال\n"
                f"- تم تخطي أو فشل: {error_count} سؤال"
            )

    except Exception as e:
        logger.error(f"Error processing PDF file: {str(e)}")
        raise

async def handle_document(bot: Bot, message: types.Message):
    """Handle document upload (PDF or CSV files)"""
    user_id = message.from_user.id
    current_time = asyncio.get_event_loop().time()
    
    # Check rate limits
    if user_id in user_last_file_time:
        time_diff = current_time - user_last_file_time[user_id]
        if time_diff < MIN_INTERVAL_BETWEEN_FILES:
            await message.reply(
                f"⏳ يرجى الانتظار {MIN_INTERVAL_BETWEEN_FILES - int(time_diff)} ثانية قبل إرسال ملف آخر."
            )
            return
    
    user_last_file_time[user_id] = current_time
    logger.info(f"Processing file from user {message.from_user.first_name} ({user_id})")
    
    try:
        document = message.document
        file_name = document.file_name
        
        if not file_name:
            await message.reply("❌ الملف غير صالح. يرجى التأكد من وجود اسم ملف.")
            return
            
        file_extension = file_name.split(".")[-1].lower()
        
        if file_extension not in ["csv", "pdf"]:
            await message.reply("❌ يرجى إرسال ملف بصيغة CSV أو PDF فقط.")
            return

        # Download file from Telegram
        file_stream = BytesIO()
        await bot.download(document, destination=file_stream)
        file_stream.seek(0)
        
        # Process file
        await process_file(bot, message, file_stream, file_extension)
        
    except Exception as e:
        error_message = f"خطأ في معالجة الملف: {str(e)}"
        logger.error(error_message)
        
        # Send detailed error to log channel
        try:
            await bot.send_message(
                LOG_CHANNEL_ID, 
                f"❌ Error processing file from user {message.from_user.first_name} ({message.from_user.id}):\n{str(e)}"
            )
        except Exception as log_err:
            logger.error(f"Failed to send error to log channel: {log_err}")
            
        # Send user-friendly message
        await message.reply("❌ حدث خطأ أثناء معالجة الملف. تم إبلاغ المسؤول بالمشكلة.")
