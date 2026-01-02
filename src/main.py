import asyncio
import logging
from aiogram import Bot, Dispatcher
from src.config import BOT_TOKEN
from src.handlers import router
from src.database import init_db, async_session, User
from src.scheduler import start_scheduler
from sqlalchemy import select

logging.basicConfig(level=logging.INFO)

# Список ТОЛЬКО для первоначальной инициализации. 
# Имена здесь не важны, они обновятся сами. Важны ID.
INIT_USERS = [
    {"tg_id": 432998089, "name": "Nikita_Init"}, # Замени на свои реальные ID
    {"tg_id": 818400806, "name": "Dania_Init"},
    {"tg_id": 510679050, "name": "Nyuta_Init"},
]

async def seed_users():
    """Добавляет пользователей в БД, если их там нет. НЕ перезаписывает имена."""
    async with async_session() as session:
        for user_data in INIT_USERS:
            result = await session.execute(select(User).where(User.tg_id == user_data["tg_id"]))
            user = result.scalar_one_or_none()

            if not user:
                print(f"➕ Добавляю нового пользователя ID {user_data['tg_id']}")
                new_user = User(
                    tg_id=user_data["tg_id"],
                    name=user_data["name"], # Временное имя, обновится при /stats
                    role="user"
                )
                session.add(new_user)
        await session.commit()

async def on_startup(bot: Bot):
    await init_db()
    await seed_users() # Запускаем только добавление новых
    start_scheduler(bot)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)
    await on_startup(bot)
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот остановлен")