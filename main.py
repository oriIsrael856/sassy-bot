import os
import sqlite3
import telebot
import requests
import random
from google import genai
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from io import BytesIO
from PIL import Image

# --- 1. אתחול והגדרות ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

if not TELEGRAM_TOKEN or not GEMINI_KEY:
    print("שגיאה: חסרים מפתחות ב- .env")
    exit()

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

# מנוע תזכורות (Scheduler) שרץ במקביל לבוט
scheduler = BackgroundScheduler()
scheduler.start()

SYSTEM_PROMPT = "אתה 'הנודניק', בוט חצוף ששונא לעזור. ענה בעברית צינית וקצרה."

# --- 2. ניהול בסיס נתונים (SQLite) ---
def init_db():
    with sqlite3.connect('tasks.db') as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, desc TEXT)')
    print("בסיס הנתונים מוכן.")

# --- 3. פונקציונליות מדבקות (איכות משופרת) ---
@bot.message_handler(commands=['sticker'])
def make_sticker(message):
    prompt = message.text.replace('/sticker', '').strip()
    if not prompt:
        bot.reply_to(message, "מה לצייר? אין לי כוח לנחש.")
        return
    
    msg = bot.reply_to(message, "מג'נרט מדבקה בסטייל נאנו-בננה... חכה רגע.")
    
    try:
        # Prompt הנדסי שנועד לחקות את האיכות של המודלים הגדולים
        enhanced_prompt = f"Professional sticker design of {prompt}, isolated on white background, thick white border, die-cut, flat vector illustration, high quality, 4k digital art"
        encoded_prompt = requests.utils.quote(enhanced_prompt)
        
        # שימוש ב-Seed אקראי כדי לקבל תוצאה שונה בכל פעם
        seed = random.randint(1, 99999)
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=512&height=512&nologo=true&seed={seed}"
        
        response = requests.get(image_url, timeout=30)
        
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            
            # וידוא גודל מדויק לטלגרם
            img = img.resize((512, 512), Image.Resampling.LANCZOS)
            
            sticker_io = BytesIO()
            img.save(sticker_io, format="WEBP", quality=95)
            sticker_io.seek(0)
            
            bot.send_sticker(message.chat.id, sticker_io)
            bot.delete_message(message.chat.id, msg.message_id)
        else:
            bot.reply_to(message, "השרת עמוס מדי. אפילו לנאנו בננה יש גבול.")
    except Exception as e:
        print(f"Error: {e}")
        bot.reply_to(message, "משהו השתבש בציור. נסה תיאור אחר.")

# --- 4. מערכת תזכורות ---
def send_reminder(chat_id, text):
    bot.send_message(chat_id, f"🔔 נודניק כאן: הגיע הזמן ל-{text}! תזיז את עצמך.")

@bot.message_handler(commands=['remind'])
def set_reminder(message):
    try:
        # פורמט: /remind 14:30 לקנות קפה
        parts = message.text.split(' ', 2)
        time_str, task_text = parts[1], parts[2]
        
        now = datetime.now()
        remind_time = datetime.strptime(time_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )
        
        if remind_time < now:
            bot.reply_to(message, "הזמן הזה כבר עבר. אני בוט, לא מכונת זמן.")
            return

        scheduler.add_job(send_reminder, 'date', run_date=remind_time, args=[message.chat.id, task_text])
        bot.reply_to(message, f"סגור. ב-{time_str} אני אציק לך על '{task_text}'.")
    except:
        bot.reply_to(message, "פורמט: /remind HH:MM משימה")

# --- 5. ניהול משימות ---
@bot.message_handler(commands=['add'])
def add_task(message):
    task = message.text.replace('/add', '').strip()
    if task:
        with sqlite3.connect('tasks.db') as conn:
            conn.execute('INSERT INTO tasks (user_id, desc) VALUES (?, ?)', (message.chat.id, task))
        bot.reply_to(message, f"רשמתי: {task}. עכשיו תעלם.")

@bot.message_handler(commands=['tasks'])
def list_tasks(message):
    with sqlite3.connect('tasks.db') as conn:
        rows = conn.execute('SELECT id, desc FROM tasks WHERE user_id = ?', (message.chat.id, )).fetchall()
    if not rows:
        bot.reply_to(message, "אין משימות. הראש שלך ריק.")
    else:
        response = "משימות שאתה בטח תתעלם מהן:\n" + "\n".join([f"{r[0]}. {r[1]}" for r in rows])
        bot.reply_to(message, response)

@bot.message_handler(commands=['done'])
def delete_task(message):
    try:
        task_id = message.text.replace('/done', '').strip()
        with sqlite3.connect('tasks.db') as conn:
            conn.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, message.chat.id))
        bot.reply_to(message, f"מחקתי את {task_id}. אל תתרגל לזה.")
    except:
        bot.reply_to(message, "תכתוב מספר משימה למחיקה.")

# --- 6. צ'אט AI חופשי (Gemini 2.5 Flash) ---
@bot.message_handler(func=lambda message: True)
def chat(message):
    try:
        # שימוש במודל 2.5 פלאש המהיר והחכם
        response = client.models.generate_content(
            model="gemini-2.5-flash", 
            contents=f"{SYSTEM_PROMPT}\nהתלמיד: {message.text}"
        )
        bot.reply_to(message, response.text)
    except Exception as e:
        print(f"AI Error: {e}")
        bot.reply_to(message, "אין לי כוח לענות לך עכשיו.")

# --- הרצה ---
if __name__ == "__main__":
    init_db()
    print("--- הבוט של אורי באוויר! (עם שדרוג מדבקות) ---")
    bot.infinity_polling()