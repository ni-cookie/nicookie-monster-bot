from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from src.config import TIMEZONE

scheduler = AsyncIOScheduler(timezone=TIMEZONE)

async def delete_msg_job(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass # Сообщение уже удалено или нет прав

def start_scheduler(bot: Bot):
    scheduler.start()