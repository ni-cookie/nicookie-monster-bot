import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID"))
TIMEZONE = os.getenv("TIMEZONE", "Europe/Kyiv")

# Пути
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA_DIR = os.path.join(BASE_DIR, "media")
DB_PATH = os.path.join(BASE_DIR, "data", "bot.db")

# Создаем папки если нет
os.makedirs(MEDIA_DIR, exist_ok=True)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)