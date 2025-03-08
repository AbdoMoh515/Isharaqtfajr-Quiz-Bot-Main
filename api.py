import asyncio
import logging
import csv
import os
import tempfile
import fitz  # PyMuPDF
import re
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.enums import ParseMode

TOKEN = "7659827096:AAF48ZWCBPmkyk3XIySYV8Y7U1kfWHL_qD0"
GROUP_ID = -1002330884907

# تهيئة البوت والـ Dispatcher
from aiogram.client.default import DefaultBotProperties
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("مرحبًا! أرسل لي ملف الأسئلة بصيغة CSV أو PDF.")


@dp.message(lambda message: message.document)
async def handle_document(message: types.Message):
    """ استقبال الملفات من المستخدم (CSV أو PDF) """
    document = message.document
    file_extension = document.file_name.split(".")[-1].lower()

    # تحميل الملف من تيليجرام
    from io import BytesIO
    file_stream = BytesIO()
    await bot.download(document, destination=file_stream)
    file_stream.seek(0)  # تحريك المؤشر إلى بداية الملف

    # إنشاء ملف مؤقت على القرص
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
            print("📄 **النص المستخرج من PDF:**")
            print(extracted_text)  # ✅ طباعة النص لمعرفة شكله

            questions = extract_questions_from_text(extracted_text)

            if not questions:
                await message.reply("❌ لم يتم العثور على أسئلة في الملف، يرجى التأكد من التنسيق الصحيح.")
            else:
                await message.reply(f"✅ تم استخراج {len(questions)} سؤال، سيتم إرسالها إلى المجموعة...")
                await send_quizzes_from_pdf(questions, GROUP_ID)

        else:
            await message.reply("❌ لم يتم العثور على أي نص داخل ملف PDF، تأكد من أن الملف يحتوي على أسئلة مكتوبة كنصوص وليس صور.")

    # حذف الملف بعد المعالجة
    os.remove(temp_path)



async def send_quizzes(file_path, chat_id):
    """ قراءة الأسئلة من ملف CSV وإرسالها كـ Quiz """
    try:
        with open(file_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) < 2:
                    continue  # تخطي أي صف غير مكتمل
                
                question = row[0]
                options = row[1:-1]  # جميع الخيارات باستثناء الإجابة الصحيحة
                correct_option = row[-1]  # الإجابة الصحيحة

                if correct_option not in options:
                    options.append(correct_option)  # التأكد من وجود الإجابة الصحيحة في الخيارات
                
                await bot.send_poll(
                    chat_id=GROUP_ID,
                    question=question,
                    options=options,
                    type="quiz",
                    correct_option_id=options.index(correct_option),
                    is_anonymous=True
                )
                await asyncio.sleep(2)  # تأخير بين كل سؤال وآخر

    except Exception as e:
        await bot.send_message(chat_id, f"❌ حدث خطأ أثناء معالجة الملف:\n{e}")


def extract_text_from_pdf(pdf_path):
    """ استخراج النصوص من ملف PDF """
    text = ""
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text += page.get_text("text") + "\n"
    return text


import re

def extract_questions_from_text(text):
    """ استخراج الأسئلة والإجابات مع دعم أي عدد من الخيارات بين 2 و6 """
    pattern = r"(\d+\.\s*(.*?)\n+)\n*((?:[A-Fa-f]\)\s*.*?\n?){2,6})\n+Answer:\s*([A-Fa-f])"
    matches = re.findall(pattern, text, re.DOTALL)

    questions = []
    for match in matches:
        question_text = match[1].strip()
        
        # استخراج جميع الاختيارات
        options_raw = match[2].strip().split("\n")
        options = []
        for opt in options_raw:
            opt_match = re.match(r"([A-Fa-f])\)\s*(.*)", opt.strip())
            if opt_match:
                options.append(opt_match.group(2).strip())

        # استخراج الإجابة الصحيحة وتحويلها إلى حرف كبير (A, B, C, ...)
        correct_answer = match[3].strip().upper()

        if correct_answer in ["A", "B", "C", "D", "E", "F"] and correct_answer in [chr(65 + i) for i in range(len(options))]:
            correct_index = ["A", "B", "C", "D", "E", "F"].index(correct_answer)
        else:
            continue  # تخطي السؤال إذا لم تكن الإجابة الصحيحة موجودة في الخيارات

        questions.append({
            "question": question_text,
            "options": options,
            "correct_option_id": correct_index
        })

    return questions



async def send_quizzes_from_pdf(questions, chat_id):
    """ إرسال الأسئلة من PDF كاختبارات (Quiz) """
    for q in questions:
        await bot.send_poll(
            chat_id=chat_id,
            question=q["question"],
            options=q["options"],
            type="quiz",
            correct_option_id=q["correct_option_id"],
            is_anonymous=True
        )
        await asyncio.sleep(2)  # تأخير بين كل سؤال وآخر


async def main():
    """ تشغيل البوت """
    logging.basicConfig(level=logging.INFO)
    print("✅ البوت يعمل الآن...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
