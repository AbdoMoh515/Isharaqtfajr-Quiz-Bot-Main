import logging
import fitz
import re
import asyncio
from typing import List, Dict, Set, Any, Tuple
from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.types import Poll

logger = logging.getLogger(__name__)

async def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extract text from PDF file with optimized formatting preservation.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Extracted text with preserved formatting
    """
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            page_count = len(doc)
            if page_count == 0:
                logger.warning("PDF is empty: no pages found")
                return ""
                
            logger.info(f"Processing PDF with {page_count} pages")
            
            for page_num, page in enumerate(doc):
                try:
                    # Get text with better formatting
                    page_text = page.get_text("text")
                    # Clean up excessive whitespace while preserving format
                    page_text = re.sub(r' +', ' ', page_text)
                    page_text = re.sub(r'\n\s*\n', '\n\n', page_text)
                    
                    text += page_text + "\n\n"
                except Exception as e:
                    logger.error(f"Error extracting text from page {page_num+1}: {str(e)}")
    except Exception as e:
        logger.error(f"Error opening PDF file: {str(e)}")
    
    return text
    """Extract text from PDF file with layout preservation"""
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            blocks = page.get_text("blocks")
            blocks.sort(key=lambda b: (b[1], b[0]))  # Sort by vertical then horizontal
            for block in blocks:
                if block[4].strip():  # Skip empty blocks
                    text += block[4] + "\n"
        return text.strip()
    except Exception as e:
        logger.error(f"PDF extraction error: {e}", exc_info=True)
        return ""

def extract_questions_from_text(text: str) -> List[Dict[str, Any]]:
    """
    Extract questions and answers from text with support for multiple formats.
    
    Args:
        text: Text extracted from PDF
        
    Returns:
        List of questions with options and correct answers
    """
    # Clean up text
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    # Log diagnostic info
    logger.info(f"Text extracted from PDF (first 500 chars): {text[:500]}...")
    logger.info(f"Total length of extracted text: {len(text)} characters")
    
    questions = []
    extracted_questions: Set[str] = set()
    
    # Patterns for different question formats
    patterns = [
        # Pattern 1: Question with options a) b) c) d) and answer with letter b)
        r"(\d+[-\.]?\s*)(.*?)\n+([a-d]\).*?(?:\n[a-d]\).*?){1,5})\n+(?:Answer|Answers?):\s*([a-d])\)?",
        
        # Pattern 2: Question with options a) b) c) d) and answer with letter and parenthesis like b)
        r"(\d+[-\.]?\s*)(.*?)\n+([a-d]\).*?(?:\n[a-d]\).*?){1,5})\n+(?:Answer|Answers?):\s*([a-d])\)",
        
        # More flexible pattern
        r"(\d+[-\.]?\s*)(.*?)\n+([a-d]\)\s*.*?(?:\n[a-d]\)\s*.*?){1,5})\n+(?:Answer|Answers?):\s*([a-d])\)?",
        
        # Pattern 3: Question with options A) B) C) D) (uppercase)
        r"(\d+[-\.]?\s*)(.*?)\n+([A-D]\).*?(?:\n[A-D]\).*?){1,5})\n+(?:Answer|Answers?):\s*([A-D])",
        
        # Pattern 4: Question with options أ) ب) ج) د) (Arabic)
        r"(\d+[-\.]?\s*)(.*?)\n+([\u0623-\u064A]\).*?(?:\n[\u0623-\u064A]\).*?){1,5})\n+(?:الإجابة|الاجابة):\s*([\u0623-\u064A])",
        
        # Pattern 5: Question with options 1) 2) 3) 4)
        r"(\d+[-\.]?\s*)(.*?)\n+([1-9]\).*?(?:\n[1-9]\).*?){1,5})\n+(?:Answer|Answers?):\s*([1-9])",
        
        # Pattern 6-9: Various formats with different separators and languages
        r"(\d+[-\.]?\s*)(.*?)\n+([a-d]\.\s*.*?(?:\n[a-d]\.\s*.*?){1,5})\n+(?:Answer|Answers?):\s*([a-d])",
        r"(\d+[-\.]?\s*)(.*?)\n+([A-D]\.\s*.*?(?:\n[A-D]\.\s*.*?){1,5})\n+(?:Answer|Answers?):\s*([A-D])",
        r"(\d+[-\.]?\s*)(.*?)\n+([\u0623-\u064A]\.\s*.*?(?:\n[\u0623-\u064A]\.\s*.*?){1,5})\n+(?:الإجابة|الاجابة):\s*([\u0623-\u064A])",
        r"(\d+[-\.]?\s*)(.*?)\n+([1-9]\.\s*.*?(?:\n[1-9]\.\s*.*?){1,5})\n+(?:Answer|Answers?):\s*([1-9])",
        
        # Pattern 10: More flexible pattern for irregular formatting
        r"(\d+[-\.]?\s*)(.*?)\n+(?:[^\n]*?choice.*?|[^\n]*?option.*?|[^\n]*?الخيار.*?)(?:\n[^\n]*?choice.*?|\n[^\n]*?option.*?|\n[^\n]*?الخيار.*?){1,5}\n+(?:answer|answers?|الإجابة|الاجابة):\s*([a-dA-D1-9\u0623-\u064A])",
        
        # Pattern 11: More flexible format for options (a - option, b - option)
        r"(\d+[-\.]?\s*)(.*?)\n+([a-dA-D])\s*[-–—]\s*(.*?)(?:\n([a-dA-D])\s*[-–—]\s*(.*?)){1,5}\n+(?:Answer|Answers?):\s*([a-dA-D])"
    ]
    
    # Process each pattern
    for i, pattern in enumerate(patterns):
        matches = re.findall(pattern, text, re.DOTALL)
        logger.info(f"Pattern {i+1}: Found {len(matches)} matches")
        
        for match in matches:
            try:
                question_num = match[0].strip()
                question_text = match[1].strip()
                
                # Add question number to text if present
                if question_num:
                    question_text = f"{question_num} {question_text}"
                
                # Extract all options
                options_text = match[2].strip()
                
                # Determine numbering type (a, A, أ, 1)
                if options_text.startswith(('a', 'b', 'c', 'd')):
                    options_raw = re.findall(r'([a-d]\))\s*(.*?)(?=\n[a-d]\)|$)', options_text, re.DOTALL)
                    correct_answer = match[3].strip().lower()
                    if correct_answer.endswith(')'):
                        correct_answer = correct_answer[:-1]
                    correct_index = ord(correct_answer) - ord('a')
                elif options_text.startswith(('A', 'B', 'C', 'D')):
                    options_raw = re.findall(r'([A-D]\))\s*(.*?)(?=\n[A-D]\)|$)', options_text, re.DOTALL)
                    correct_answer = match[3].strip().upper()
                    correct_index = ord(correct_answer) - ord('A')
                elif options_text[0] in 'أبجدهوزحطي':  # Arabic letters
                    options_raw = re.findall(r'([\u0623-\u064A]\))\s*(.*?)(?=\n[\u0623-\u064A]\)|$)', options_text, re.DOTALL)
                    correct_answer = match[3].strip()
                    arabic_options = 'أبجدهوزحطي'
                    correct_index = arabic_options.find(correct_answer)
                else:  # Numbers
                    options_raw = re.findall(r'([1-9]\))\s*(.*?)(?=\n[1-9]\)|$)', options_text, re.DOTALL)
                    correct_answer = match[3].strip()
                    correct_index = int(correct_answer) - 1
                
                options = []
                for opt in options_raw:
                    option_text = opt[1].strip()
                    options.append(option_text)
                
                # Ensure correct answer is within range
                if 0 <= correct_index < len(options):
                    # Create unique ID for question
                    question_id = question_text[:50]
                    if question_id not in extracted_questions:
                        questions.append({
                            "question": question_text,
                            "options": options,
                            "correct_option_id": correct_index
                        })
                        extracted_questions.add(question_id)
                        logger.info(f"Added new question: {question_id}")
                    else:
                        logger.info(f"Skipped duplicate question: {question_id}")
            except Exception as e:
                logger.warning(f"Error extracting question: {str(e)}")
                continue
    
    return questions
    """
    Extract questions from text with support for multiple formats
    
    Args:
        text: Extracted text from PDF
        
    Returns:
        List of question dictionaries with 'question', 'options', and 'correct_option_id'
    """
    questions = []
    
    # Pattern that matches your exact format
    pattern = r"""
        (?:^|\n)                      # Start of line
        (\d+-)?                       # Optional question number
        (.*?)                         # Question text
        \s*\n+                        # Whitespace
        ((?:                          # Options block:
           [a-d]\)\s*.+?              # Option line
           (?:\n|$)                   # End of line
        ){2,})                        # At least 2 options
        \s*                           # Whitespace
        Answer:\s*([a-d])             # Correct answer
        """
    
    try:
        matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE | re.VERBOSE)
        
        for match in matches:
            question_text = match.group(2).strip()
            options_block = match.group(3).strip()
            correct_answer = match.group(4).strip().lower()
            
            # Extract clean options
            options = []
            option_lines = re.finditer(r'^([a-d])\)\s*(.+?)(?=\n[a-d]\)|\n*$)', 
                                     options_block, re.MULTILINE)
            for opt in option_lines:
                options.append(opt.group(2).strip())
            
            if len(options) >= 2:
                try:
                    correct_index = ord(correct_answer) - ord('a')
                    if 0 <= correct_index < len(options):
                        questions.append({
                            'question': question_text,
                            'options': options,
                            'correct_option_id': correct_index
                        })
                except Exception as e:
                    logger.warning(f"Question format error: {e}")
    except Exception as e:
        logger.error(f"Regex error: {e}")
    
    return questions

async def send_telegram_quizzes(bot: Bot, questions: List[Dict[str, Any]], chat_id: int) -> Tuple[int, int]:
    """Send questions as Telegram quizzes"""
    sent_count = 0
    error_count = 0
    
    for q in questions:
        try:
            await bot.send_poll(
                chat_id=chat_id,
                question=q['question'],
                options=q['options'],
                type='quiz',
                correct_option_id=q['correct_option_id'],
                is_anonymous=False
            )
            sent_count += 1
            await asyncio.sleep(0.5)  # Avoid flood limits
        except Exception as e:
            logger.error(f"Error sending quiz: {e}")
            error_count += 1
    
    return sent_count, error_count

async def format_quiz_as_text(quiz: Poll) -> str:
    """Convert a single Telegram quiz to text format"""
    try:
        text = f"📝 السؤال:\n{quiz.question}\n\nالخيارات:\n"
        for i, option in enumerate(quiz.options):
            text += f"{chr(1633 + i)}) {option.text}\n"  # Arabic numbering
        text += f"\n✅ الإجابة الصحيحة: {chr(1633 + quiz.correct_option_id)}"
        return text
    except Exception as e:
        logger.error(f"Error formatting quiz: {e}")
        return "❌ خطأ في تحويل الاختبار إلى نص"