import asyncio
import logging
import csv
import os
import tempfile
import fitz  # PyMuPDF
import re
import signal
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

import os
TOKEN = os.environ.get("TELEGRAM_TOKEN", "7659827096:AAF48ZWCBPmkyk3XIySYV8Y7U1kfWHL_qD0")
GROUP_ID = int(os.environ.get("GROUP_ID", "-1002330884907"))
LOG_CHANNEL_ID = int(os.environ.get("LOG_CHANNEL_ID", "-1002300659776"))

# تهيئة البوت والـ Dispatcher
from aiogram.client.default import DefaultBotProperties
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer(
        "👋 مرحبًا بك في بوت الاختبارات!\n\n"
        "يمكنك إرسال ملفات الأسئلة بصيغة CSV أو PDF لإنشاء اختبارات في المجموعة.\n"
        "استخدم الأمر /help للحصول على مزيد من المعلومات."
    )

@dp.message(Command("help"))
async def help_command(message: types.Message):
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


# قاموس لتخزين آخر وقت تم فيه معالجة ملف لكل مستخدم
user_last_file_time = {}

@dp.error()
async def error_handler(exception):
    error_message = f"❌ Exception raised: {exception}"
    logging.error(error_message)
    # Send error to the logging channel
    try:
        await bot.send_message(LOG_CHANNEL_ID, error_message)
    except Exception as e:
        logging.error(f"Failed to send error to log channel: {e}")

@dp.message(lambda message: message.document)
async def handle_document(message: types.Message):
    # التحقق من معدل الطلبات (مرة واحدة كل دقيقة لكل مستخدم)
    user_id = message.from_user.id
    current_time = asyncio.get_event_loop().time()

    if user_id in user_last_file_time:
        time_diff = current_time - user_last_file_time[user_id]
        if time_diff < 60:  # 60 ثانية
            await message.reply(f"⏳ يرجى الانتظار {60 - int(time_diff)} ثانية قبل إرسال ملف آخر.")
            return

    user_last_file_time[user_id] = current_time
    logging.info(f"معالجة ملف من المستخدم {message.from_user.first_name} ({user_id})")
    """ استقبال الملفات من المستخدم (CSV أو PDF) """
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

        # تحميل الملف من تيليجرام
        from io import BytesIO
        file_stream = BytesIO()
        await bot.download(document, destination=file_stream)
        file_stream.seek(0)  # تحريك المؤشر إلى بداية الملف

        # إنشاء ملف مؤقت على القرص
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}", mode="wb") as temp_file:
                temp_file.write(file_stream.getvalue())
                temp_path = temp_file.name  # حفظ مسار الملف

            await message.answer("✅ تم استلام الملف، جاري المعالجة...")

            if file_extension == "csv":
                await send_quizzes(temp_path, message.chat.id)

            elif file_extension == "pdf":
                # استخراج النص من PDF
                extracted_text = extract_text_from_pdf(temp_path)

                if extracted_text.strip():  # تأكد من أن النص غير فارغ
                    logging.info("📄 النص المستخرج من PDF")

                    # إرسال رسالة مؤقتة قبل معالجة الأسئلة
                    processing_msg = await message.reply("🔍 جاري تحليل النص واستخراج الأسئلة...")

                    questions = extract_questions_from_text(extracted_text)

                    if not questions:
                        # إرسال أول 500 حرف من النص للمستخدم كمساعدة في تحديد المشكلة
                        preview = extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text
                        logging.warning("لم يتم العثور على أسئلة في النص المستخرج من PDF")
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
                        logging.info(f"تم العثور على {len(questions)} سؤال فريد")
                        await message.reply(f"✅ تم استخراج {len(questions)} سؤال فريد، سيتم إرسالها إلى المجموعة...")
                        await send_quizzes_from_pdf(questions, GROUP_ID)

                else:
                    await message.reply("❌ لم يتم العثور على أي نص داخل ملف PDF، تأكد من أن الملف يحتوي على أسئلة مكتوبة كنصوص وليس صور.")
        finally:
            # حذف الملف بعد المعالجة إذا تم إنشاؤه
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    except Exception as e:
        error_message = f"خطأ في معالجة الملف: {str(e)}"
        logging.error(error_message)

        # Send detailed error to log channel
        try:
            await bot.send_message(LOG_CHANNEL_ID, f"❌ Error processing file from user {message.from_user.first_name} ({message.from_user.id}):\n{str(e)}")
        except Exception as log_err:
            logging.error(f"Failed to send error to log channel: {log_err}")

        # Send user-friendly message to the user
        await message.reply("❌ حدث خطأ أثناء معالجة الملف. تم إبلاغ المسؤول بالمشكلة.")



async def send_quizzes(file_path, chat_id):
    """ قراءة الأسئلة من ملف CSV وإرسالها كـ Quiz """
    sent_count = 0
    error_count = 0

    try:
        with open(file_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)  # قراءة جميع الصفوف مرة واحدة

            if not rows:
                await bot.send_message(chat_id, "❌ الملف CSV فارغ!")
                return

            total_rows = len(rows)
            await bot.send_message(chat_id, f"🔄 جاري معالجة {total_rows} سؤال من ملف CSV...")

            for i, row in enumerate(rows):
                try:
                    if len(row) < 2:
                        logging.warning(f"تم تخطي السطر {i+1}: غير مكتمل")
                        error_count += 1
                        continue

                    question = row[0].strip()
                    if not question:
                        logging.warning(f"تم تخطي السطر {i+1}: لا يوجد سؤال")
                        error_count += 1
                        continue

                    options = [opt.strip() for opt in row[1:-1] if opt.strip()]  # استبعاد الخيارات الفارغة
                    correct_option = row[-1].strip()

                    if not correct_option:
                        logging.warning(f"تم تخطي السطر {i+1}: لا توجد إجابة صحيحة")
                        error_count += 1
                        continue

                    if len(options) < 1:
                        logging.warning(f"تم تخطي السطر {i+1}: لا توجد خيارات كافية")
                        error_count += 1
                        continue

                    # التأكد من وجود الإجابة الصحيحة في الخيارات
                    if correct_option not in options:
                        options.append(correct_option)

                    # التأكد من أن عدد الخيارات لا يتجاوز الحد المسموح به في تيليجرام
                    if len(options) > 10:
                        options = options[:10]
                        logging.warning(f"تم اقتصاص الخيارات للسؤال {i+1} إلى 10 خيارات")

                    if len(options) < 2:
                        options.append("لا أعرف الإجابة")  # إضافة خيار افتراضي إذا كان هناك خيار واحد فقط

                    await bot.send_poll(
                        chat_id=GROUP_ID,
                        question=question,
                        options=options,
                        type="quiz",
                        correct_option_id=options.index(correct_option),
                        is_anonymous=True
                    )

                    sent_count += 1
                    await asyncio.sleep(2)  # تأخير بين كل سؤال وآخر

                    # إرسال تحديث كل 10 أسئلة
                    if sent_count % 10 == 0:
                        await bot.send_message(chat_id, f"✅ تم إرسال {sent_count}/{total_rows} سؤال...")

                except Exception as e:
                    error_count += 1
                    logging.error(f"خطأ في السؤال {i+1}: {str(e)}")

            # إرسال تقرير نهائي
            await bot.send_message(
                chat_id, 
                f"✅ اكتملت العملية!\n"
                f"- تم إرسال: {sent_count} سؤال\n"
                f"- تم تخطي: {error_count} سؤال"
            )

    except Exception as e:
        error_message = f"خطأ في معالجة ملف CSV: {str(e)}"
        logging.error(error_message)

        # Send detailed error to log channel
        try:
            await bot.send_message(LOG_CHANNEL_ID, f"❌ CSV processing error:\n{str(e)}")
        except Exception as log_err:
            logging.error(f"Failed to send error to log channel: {log_err}")

        # Send user-friendly message to the user
        await bot.send_message(chat_id, "❌ حدث خطأ أثناء معالجة الملف. تم إبلاغ المسؤول بالمشكلة.")


def extract_text_from_pdf(pdf_path):
    """ استخراج النصوص من ملف PDF مع تحسينات """
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            # التحقق من عدد الصفحات
            page_count = len(doc)
            if page_count == 0:
                logging.warning("PDF فارغ: لا توجد صفحات")
                return ""

            logging.info(f"يتم معالجة PDF مكون من {page_count} صفحة")

            for page_num, page in enumerate(doc):
                try:
                    # استخراج النص مع معالجة أفضل للتنسيق
                    page_text = page.get_text("text")
                    # حفظ التنسيق الأصلي للأسطر مع تنظيف المساحات الزائدة
                    page_text = re.sub(r' +', ' ', page_text)  # دمج المسافات المتعددة
                    page_text = re.sub(r'\n\s*\n', '\n\n', page_text)  # دمج الأسطر الفارغة
                    # لا نقوم بإزالة جميع الأسطر الجديدة لأنها مهمة لتنسيق الأسئلة

                    text += page_text + "\n\n"

                except Exception as e:
                    logging.error(f"خطأ في استخراج النص من الصفحة {page_num+1}: {str(e)}")
    except Exception as e:
        logging.error(f"خطأ في فتح ملف PDF: {str(e)}")

    return text


import re

def extract_questions_from_text(text):
    """ استخراج الأسئلة والإجابات مع دعم أشكال متعددة من الأسئلة """
    # تنظيف النص من أي مساحات زائدة
    text = re.sub(r'\n{3,}', '\n\n', text)

    # طباعة النص المستخرج للتشخيص
    logging.info(f"النص المستخرج من PDF (أول 500 حرف): {text[:500]}...")
    # تسجيل طول النص المستخرج
    logging.info(f"إجمالي طول النص المستخرج: {len(text)} حرف")

    questions = []
    # قاموس لتخزين الأسئلة التي تم استخراجها مسبقًا لتجنب التكرار
    extracted_questions = set()

    # مجموعة من الأنماط المختلفة لاستخراج الأسئلة بشكل أكثر مرونة
    patterns = [
        # النمط 1: السؤال مع خيارات a) b) c) d) وجواب مع حرف b)
        r"(\d+[-\.]?\s*)(.*?)\n+([a-d]\).*?(?:\n[a-d]\).*?){1,5})\n+(?:Answer|Answers?):\s*([a-d])\)?",

        # النمط 2: السؤال مع خيارات a) b) c) d) والجواب مع حرف وأقواس مثل b)
        r"(\d+[-\.]?\s*)(.*?)\n+([a-d]\).*?(?:\n[a-d]\).*?){1,5})\n+(?:Answer|Answers?):\s*([a-d])\)",

        # نمط إضافي: يتعامل مع نوع السؤال الذي يظهر في اللوغات الخاصة بك
        r"(\d+[-\.]?\s*)(.*?)\n+([a-d]\)\s*.*?(?:\n[a-d]\)\s*.*?){1,5})\n+(?:Answer|Answers?):\s*([a-d])\)?",

        # النمط 3: السؤال مع خيارات A) B) C) D) (حروف كبيرة)
        r"(\d+[-\.]?\s*)(.*?)\n+([A-D]\).*?(?:\n[A-D]\).*?){1,5})\n+(?:Answer|Answers?):\s*([A-D])",

        # النمط 4: السؤال مع خيارات أ) ب) ج) د) (عربي)
        r"(\d+[-\.]?\s*)(.*?)\n+([\u0623-\u064A]\).*?(?:\n[\u0623-\u064A]\).*?){1,5})\n+(?:الإجابة|الاجابة):\s*([\u0623-\u064A])",

        # النمط 5: السؤال مع خيارات 1) 2) 3) 4)
        r"(\d+[-\.]?\s*)(.*?)\n+([1-9]\).*?(?:\n[1-9]\).*?){1,5})\n+(?:Answer|Answers?):\s*([1-9])",

        # النمط 6: السؤال مع خيارات a. b. c. d.
        r"(\d+[-\.]?\s*)(.*?)\n+([a-d]\.\s*.*?(?:\n[a-d]\.\s*.*?){1,5})\n+(?:Answer|Answers?):\s*([a-d])",

        # النمط 7: السؤال مع خيارات A. B. C. D. (حروف كبيرة)
        r"(\d+[-\.]?\s*)(.*?)\n+([A-D]\.\s*.*?(?:\n[A-D]\.\s*.*?){1,5})\n+(?:Answer|Answers?):\s*([A-D])",

        # النمط 8: السؤال مع خيارات أ. ب. ج. د. (عربي مع نقطة)
        r"(\d+[-\.]?\s*)(.*?)\n+([\u0623-\u064A]\.\s*.*?(?:\n[\u0623-\u064A]\.\s*.*?){1,5})\n+(?:الإجابة|الاجابة):\s*([\u0623-\u064A])",

        # النمط 9: السؤال مع خيارات 1. 2. 3. 4. (أرقام مع نقطة)
        r"(\d+[-\.]?\s*)(.*?)\n+([1-9]\.\s*.*?(?:\n[1-9]\.\s*.*?){1,5})\n+(?:Answer|Answers?):\s*([1-9])",

        # النمط 10: السؤال مع خيارات مع تنسيق غير منتظم
        r"(\d+[-\.]?\s*)(.*?)\n+(?:[^\n]*?choice.*?|[^\n]*?option.*?|[^\n]*?الخيار.*?)(?:\n[^\n]*?choice.*?|\n[^\n]*?option.*?|\n[^\n]*?الخيار.*?){1,5}\n+(?:answer|answers?|الإجابة|الاجابة):\s*([a-dA-D1-9\u0623-\u064A])",

        # النمط 11: تنسيق أكثر مرونة للخيارات (a - option, b - option)
        r"(\d+[-\.]?\s*)(.*?)\n+([a-dA-D])\s*[-–—]\s*(.*?)(?:\n([a-dA-D])\s*[-–—]\s*(.*?)){1,5}\n+(?:Answer|Answers?):\s*([a-dA-D])"
    ]

    # تجربة كل نمط
    for i, pattern in enumerate(patterns):
        matches = re.findall(pattern, text, re.DOTALL)
        logging.info(f"النمط {i+1}: تم العثور على {len(matches)} تطابق")

        for match in matches:
            try:
                question_num = match[0].strip()
                question_text = match[1].strip()

                # إذا كان هناك رقم سؤال، أضفه إلى نص السؤال
                if question_num:
                    question_text = f"{question_num} {question_text}"

                # استخراج جميع الاختيارات
                options_text = match[2].strip()

                # تحديد نوع الترقيم المستخدم (a, A, أ, 1)
                if options_text.startswith(('a', 'b', 'c', 'd')):
                    # استخدام نمط أكثر مرونة لاستخراج الخيارات
                    options_raw = re.findall(r'([a-d]\))\s*(.*?)(?=\n[a-d]\)|$)', options_text, re.DOTALL)
                    correct_answer = match[3].strip().lower()
                    # تنظيف الإجابة من الأقواس إن وجدت
                    if correct_answer.endswith(')'):
                        correct_answer = correct_answer[:-1]
                    correct_index = ord(correct_answer) - ord('a')
                    logging.info(f"تم استخراج سؤال. الإجابة الصحيحة: {correct_answer}, مؤشر: {correct_index}")
                elif options_text.startswith(('A', 'B', 'C', 'D')):
                    options_raw = re.findall(r'([A-D]\))\s*(.*?)(?=\n[A-D]\)|$)', options_text, re.DOTALL)
                    correct_answer = match[3].strip().upper()
                    correct_index = ord(correct_answer) - ord('A')
                elif options_text[0] in 'أبجدهوزحطي':  # حروف عربية
                    options_raw = re.findall(r'([\u0623-\u064A]\))\s*(.*?)(?=\n[\u0623-\u064A]\)|$)', options_text, re.DOTALL)
                    correct_answer = match[3].strip()
                    # تحويل الإجابة العربية إلى رقم (أ=0, ب=1, إلخ)
                    arabic_options = 'أبجدهوزحطي'
                    correct_index = arabic_options.find(correct_answer)
                else:  # أرقام
                    options_raw = re.findall(r'([1-9]\))\s*(.*?)(?=\n[1-9]\)|$)', options_text, re.DOTALL)
                    correct_answer = match[3].strip()
                    correct_index = int(correct_answer) - 1  # تحويل الرقم إلى فهرس (1=>0, 2=>1, إلخ)

                options = []
                for opt in options_raw:
                    option_text = opt[1].strip()
                    options.append(option_text)

                # تأكد من أن الإجابة الصحيحة في نطاق الخيارات
                if 0 <= correct_index < len(options):
                    # إنشاء معرف فريد للسؤال باستخدام نص السؤال والخيارات
                    question_id = question_text[:50]  # استخدم بداية السؤال كمعرف
                    if question_id not in extracted_questions:
                        questions.append({
                            "question": question_text,
                            "options": options,
                            "correct_option_id": correct_index
                        })
                        extracted_questions.add(question_id)
                        logging.info(f"تمت إضافة سؤال جديد: {question_id}")
                    else:
                        logging.info(f"تم تخطي سؤال مكرر: {question_id}")
            except Exception as e:
                logging.warning(f"خطأ في استخراج السؤال: {str(e)}")
                continue

    return questions



async def send_quizzes_from_pdf(questions, chat_id):
    """ إرسال الأسئلة من PDF كاختبارات (Quiz) مع إدارة أفضل لحدود التيليجرام """
    sent_count = 0
    error_count = 0

    # إرسال رسالة للمستخدم قبل البدء
    await bot.send_message(chat_id, f"🔄 جاري إرسال {len(questions)} سؤال...")

    for i, q in enumerate(questions):
        try:
            await bot.send_poll(
                chat_id=chat_id,
                question=q["question"],
                options=q["options"],
                type="quiz",
                correct_option_id=q["correct_option_id"],
                is_anonymous=True
            )
            sent_count += 1

            # تأخير أكبر بين الرسائل لتجنب حدود التيليجرام
            await asyncio.sleep(3)  # 3 ثوان بين كل سؤال

            # إرسال تحديث كل 5 أسئلة
            if sent_count % 5 == 0:
                await bot.send_message(chat_id, f"✅ تم إرسال {sent_count}/{len(questions)} سؤال...")
                await asyncio.sleep(2)  # انتظار إضافي بعد رسائل التحديث

            # زيادة التأخير كل 20 سؤال لتجنب حدود التيليجرام
            if sent_count % 20 == 0:
                logging.info(f"انتظار 30 ثانية بعد إرسال {sent_count} سؤال لتجنب حدود التيليجرام")
                await bot.send_message(chat_id, "⏳ انتظار قليل لتجنب حدود التيليجرام...")
                await asyncio.sleep(30)  # انتظار 30 ثانية كل 20 سؤال

        except Exception as e:
            error_count += 1
            error_message = f"خطأ في إرسال السؤال {i+1}: {str(e)}"
            logging.error(error_message)

            # Send error to log channel
            try:
                await bot.send_message(LOG_CHANNEL_ID, f"❌ Error sending poll {i+1}/{len(questions)}:\n{str(e)}")
            except Exception as log_err:
                logging.error(f"Failed to send error to log channel: {log_err}")

            # التعامل مع أخطاء حدود التيليجرام
            if "Flood control exceeded" in str(e) or "Too Many Requests" in str(e):
                # استخراج وقت الانتظار من رسالة الخطأ
                retry_time = 20  # وقت افتراضي للانتظار

                try:
                    # محاولة استخراج وقت الانتظار من رسالة الخطأ
                    retry_match = re.search(r'retry after (\d+)', str(e))
                    if retry_match:
                        retry_time = int(retry_match.group(1)) + 5  # إضافة 5 ثوان إضافية
                except:
                    pass

                await bot.send_message(chat_id, f"⚠️ تم تجاوز حدود التيليجرام! سننتظر {retry_time} ثانية قبل المتابعة...")
                logging.warning(f"انتظار {retry_time} ثانية بسبب حدود التيليجرام")
                await asyncio.sleep(retry_time)

                # محاولة إعادة إرسال السؤال الحالي
                try:
                    await bot.send_poll(
                        chat_id=chat_id,
                        question=q["question"],
                        options=q["options"],
                        type="quiz",
                        correct_option_id=q["correct_option_id"],
                        is_anonymous=True
                    )
                    sent_count += 1
                    error_count -= 1  # تصحيح العداد لأن المحاولة الثانية نجحت
                    await asyncio.sleep(5)  # انتظار أطول بعد إعادة المحاولة
                except Exception as retry_error:
                    logging.error(f"فشلت إعادة المحاولة للسؤال {i+1}: {str(retry_error)}")

    # إرسال تقرير نهائي
    await bot.send_message(
        chat_id, 
        f"✅ اكتملت العملية!\n"
        f"- تم إرسال: {sent_count} سؤال\n"
        f"- تم تخطي أو فشل: {error_count} سؤال"
    )


async def main():
    """ تشغيل البوت """
    # تحسين إعدادات التسجيل لتضمين الوقت والتاريخ
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    logging.info("✅ البوت يعمل الآن...")
    await dp.start_polling(bot)


async def shutdown(signal, loop):
    """إيقاف البوت بشكل آمن عند استلام إشارة إنهاء"""
    logging.warning(f"تم استلام إشارة {signal.name}...")
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]

    if tasks:
        logging.info(f"انتظار انتهاء {len(tasks)} مهمة...")
        await asyncio.gather(*tasks, return_exceptions=True)

    logging.info("إيقاف البوت بنجاح!")
    loop.stop()

if __name__ == "__main__":
    # إعداد معالجة الإشارات للإيقاف الآمن
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
            # لا يتم دعم معالجة الإشارات في Windows
            pass

    try:
        loop.run_until_complete(main())
    finally:
        logging.info("إغلاق الحلقة")
        loop.close()
