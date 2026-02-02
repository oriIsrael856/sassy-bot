import os
import sqlite3
import telebot
import requests
from google import genai
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

# טעינת המפתחות
load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')
HF_TOKEN = os.getenv('HF_TOKEN')

# בדיקת מפתחות
if not all([TELEGRAM_TOKEN, GEMINI_KEY]):
    print("שגיאה: חסרים מפתחות ב- .env")
    exit()

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = genai.Client(api_key=GEMINI_KEY)

# --- הגדרת המתזמן (Scheduler) ---
scheduler = BackgroundScheduler()
scheduler.start()

# הגדרות Hugging Face למדבקות
IMAGE_MODEL_URL = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
headers = {"Authorization": f"Bearer {HF_TOKEN}"}

SYSTEM_PROMPT = "אתה 'הנודניק', בוט חצוף שעוזר לתלמידים. ענה בעברית קצרה, צינית ומצחיקה."

# --- בסיס נתונים ---
def init_db():
    with sqlite3.connect('tasks.db') as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, desc TEXT)')
    print("בסיס הנתונים מוכן.")

# --- פונקציית עזר לשליחת תזכורת ---
def send_reminder(chat_id, task_text):
    bot.send_message(chat_id, f"🔔 נודניק מזכיר לך: {task_text}\nתפסיק להתבטל ותתחיל לעבוד!")

# --- מוח ה-AI (הגרסה שעובדת לך) ---
def get_ai_response(user_text):
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{SYSTEM_PROMPT}\nהתלמיד אמר: {user_text}"
        )
        return response.text
    except Exception as e:
        print(f"❌ שגיאת API: {str(e)}")
        if "429" in str(e):
            return "חפרת לי! המכסה של גוגל נגמרה. חכה דקה ונסה שוב."
        return f"אפילו ה-AI שלי קרס מהשטויות שכתבת. שגיאה: {str(e)}"

# --- פקודת התזכורת (Remind) ---
@bot.message_handler(commands=['remind'])
def set_reminder(message):
    try:
        # פורמט מצופה: /remind 14:30 לקנות חלב
        parts = message.text.split(' ', 2)
        if len(parts) < 3:
            bot.reply_to(message, "שכחת משהו! תכתוב ככה: /remind HH:MM מה להזכיר")
            return

        time_str = parts[1]
        task_text = parts[2]
        
        now = datetime.now()
        # המרת הזמן לאובייקט datetime (לפי היום הנוכחי)
        target_time = datetime.strptime(time_str, "%H:%M").replace(
            year=now.year, month=now.month, day=now.day
        )

        # הוספה לתור המשימות
        scheduler.add_job(
            send_reminder, 
            'date', 
            run_date=target_time, 
            args=[message.chat.id, task_text]
        )
        
        bot.reply_to(message, f"סבבה, אני אציק לך ב-{time_str} לגבי '{task_text}'.")
        
    except ValueError:
        bot.reply_to(message, "הזמן לא תקין! תשתמש בפורמט HH:MM (למשל 14:05).")
    except Exception as e:
        print(f"⚠️ שגיאה בהוספת תזכורת: {e}")
        bot.reply_to(message, "משהו נדפק לי בלוח זמנים.")

# --- פקודת המדבקות (Hugging Face) ---
@bot.message_handler(commands=['sticker'])
def make_sticker(message):
    prompt = message.text.replace('/sticker', '').strip()
    if not prompt:
        bot.reply_to(message, "מה לצייר? אין לי כוח לנחש.")
        return
    
    msg = bot.reply_to(message, "מג'נרט מדבקה באיכות 'נאנו בננה'... חכה רגע.")
    
    try:
        new_url = "https://router.huggingface.co/hf-inference/models/black-forest-labs/FLUX.1-schnell"
        enhanced_prompt = f"Professional sticker of {prompt}, isolated on white background, thick white border, die-cut style"
        
        response = requests.post(new_url, headers=headers, json={"inputs": enhanced_prompt}, timeout=60)
        
        if response.status_code == 200:
            img = Image.open(BytesIO(response.content))
            img = img.resize((512, 512), Image.Resampling.LANCZOS)
            
            sticker_io = BytesIO()
            img.save(sticker_io, format="WEBP")
            sticker_io.seek(0)
            
            bot.send_sticker(message.chat.id, sticker_io)
            bot.delete_message(message.chat.id, msg.message_id)
        else:
            print(f"❌ שגיאת HF (קוד {response.status_code}): {response.text}")
            bot.reply_to(message, f"השרת של המדבקות החזיר שגיאה {response.status_code}.")
            
    except Exception as e:
        print(f"⚠️ שגיאה במדבקות: {e}")
        bot.reply_to(message, "משהו נדפק בציור.")

# --- שאר הפקודות ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "נו, מה עכשיו? שלח /add [משימה], /remind [HH:MM] [מה להזכיר] או /sticker [מה לצייר].")

@bot.message_handler(commands=['add'])
def add(message):
    task = message.text.replace('/add', '').strip()
    if task:
        with sqlite3.connect('tasks.db') as conn:
            conn.execute('INSERT INTO tasks (user_id, desc) VALUES (?, ?)', (message.chat.id, task))
        bot.reply_to(message, f"רשמתי: '{task}'. עכשיו תעוף לעבוד.")

@bot.message_handler(commands=['tasks'])
def list_tasks(message):
    with sqlite3.connect('tasks.db') as conn:
        rows = conn.execute('SELECT id, desc FROM tasks WHERE user_id = ?', (message.chat.id, )).fetchall()
    text = "משימות שאתה בטח תתעלם מהן:\n" + "\n".join([f"{r[0]}. {r[1]}" for r in rows]) if rows else "אין משימות."
    bot.reply_to(message, text)

@bot.message_handler(commands=['done'])
def done(message):
    task_id = message.text.replace('/done', '').strip()
    if task_id:
        with sqlite3.connect('tasks.db') as conn:
            conn.execute('DELETE FROM tasks WHERE id = ? AND user_id = ?', (task_id, message.chat.id))
        bot.reply_to(message, f"מחקתי את {task_id}.")

@bot.message_handler(func=lambda message: True)
def chat(message):
    bot.reply_to(message, get_ai_response(message.text))

if __name__ == "__main__":
    init_db()
    print("--- הבוט של אורי באוויר! (Gemini 2.5 + Stickers + Reminders) ---")
    bot.infinity_polling()