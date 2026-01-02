import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy import select
from datetime import datetime, timedelta

from src.database import async_session, User, Submission
from src.services import calculate_stats_period, generate_period_chart
from src.config import GROUP_CHAT_ID
from src.scheduler import scheduler, delete_msg_job
from src.states import StatsState

router = Router()

pending_media = {} # {user_id: {"file_id": ..., "file_type": ...}}

WORKOUT_TAGS = ["#спортзал", "#gym", "#зал", "#workout", "#треня", "#спорт"]
MEAL_TAGS = ["#еда", "#meal", "#food", "#кушать", "#завтрак", "#обед", "#ужин"]
CHEAT_TAGS = ["#читы", "#cheat", "#чит", "#вредное"]

# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def get_stats_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="За сегодня", callback_data="stats_today"),
         InlineKeyboardButton(text="За неделю", callback_data="stats_week")],
        [InlineKeyboardButton(text="За месяц", callback_data="stats_month"),
         InlineKeyboardButton(text="Кастом (даты)", callback_data="stats_custom")]
    ])

def get_mod_keyboard(submission_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Принять", callback_data=f"approve_{submission_id}"),
         InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject_{submission_id}")]
    ])

async def schedule_autodelete(bot: Bot, chat_id: int, message_id: int, delay_sec: int = 300):
    run_date = datetime.now() + timedelta(seconds=delay_sec)
    scheduler.add_job(delete_msg_job, 'date', run_date=run_date, args=[bot, chat_id, message_id])

async def get_user_from_db(user_id):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.tg_id == user_id))
        return result.scalar_one_or_none()

async def process_submission(bot, user, file_id, file_type, content_type, chat_id, reply_id):
    async with async_session() as session:
        new_sub = Submission(
            user_id=user.id, 
            type=content_type, 
            file_id=file_id,
            file_type=file_type,
            verified=False, 
            timestamp=datetime.now()
        )
        session.add(new_sub)
        await session.commit()
        await session.refresh(new_sub)
        sub_id = new_sub.id

    emoji = "🍔" if content_type == "cheat" else ("🥗" if content_type == "meal" else "🏋️‍♂️")
    text_type = "ЧИТ-МИЛ (+1 штраф)" if content_type == "cheat" else content_type
    
    caption_text = f"<b>{emoji} @{user.name} | {text_type}</b>\n🕓 <i>{datetime.now().strftime('%H:%M')}</i>"
    
    sent_msg = None
    if file_type == "photo":
        sent_msg = await bot.send_photo(chat_id=chat_id, photo=file_id, caption=f"На проверку:\n{caption_text}", reply_to_message_id=reply_id, reply_markup=get_mod_keyboard(sub_id), parse_mode="HTML")
    elif file_type == "video":
        sent_msg = await bot.send_video(chat_id=chat_id, video=file_id, caption=f"На проверку:\n{caption_text}", reply_to_message_id=reply_id, reply_markup=get_mod_keyboard(sub_id), parse_mode="HTML")
    elif file_type == "video_note":
        msg_note = await bot.send_video_note(chat_id=chat_id, video_note=file_id, reply_to_message_id=reply_id)
        sent_msg = await bot.send_message(chat_id=chat_id, text=f"На проверку:\n{caption_text}", reply_to_message_id=msg_note.message_id, reply_markup=get_mod_keyboard(sub_id), parse_mode="HTML")
        await schedule_autodelete(bot, chat_id, msg_note.message_id)

    if sent_msg:
        await schedule_autodelete(bot, chat_id, sent_msg.message_id)

# --- КОМАНДЫ ---

@router.message(Command("start"))
async def cmd_start(message: Message, bot: Bot):
    try: await message.delete()
    except: pass

    txt = ("👋 <b>CookieHelper v2.3</b>\n\n"
           "📸 <b>Правила:</b>\n"
           "• Фото/Видео + <code>#еда</code> или <code>#зал</code>\n"
           "• <code>#читы</code> — +1 штраф.\n\n"
           "📊 <b>Статистика:</b> /stats")
    msg = await message.answer(txt, parse_mode="HTML")
    await schedule_autodelete(bot, message.chat.id, msg.message_id)

@router.message(Command("stats"))
async def cmd_stats(message: Message, bot: Bot):
    try: await message.delete()
    except: pass
    msg = await message.answer("📊 <b>Выберите период статистики:</b>", reply_markup=get_stats_keyboard(), parse_mode="HTML")
    await schedule_autodelete(bot, message.chat.id, msg.message_id)

# --- CALLBACKS ДЛЯ СТАТИСТИКИ (С ФИКСОМ ДЛИННОГО ТЕКСТА) ---

async def send_stats_report(bot, chat_id, start_date, end_date, title):
    loading_msg = await bot.send_message(chat_id, "🔄 Считаю статистику...")
    async with async_session() as session:
        stats = await calculate_stats_period(session, bot, GROUP_CHAT_ID, start_date, end_date)
        chart_buf = generate_period_chart(stats, title)
    await bot.delete_message(chat_id, loading_msg.message_id)

    if not stats:
        msg = await bot.send_message(chat_id, "Нет данных.")
        await schedule_autodelete(bot, chat_id, msg.message_id)
        return

    text_lines = [f"📅 <b>{title}</b>\n"]
    for name, data in stats.items():
        reasons_display = data['reasons']
        line = (f"👤 <b>{name}</b>:\n"
                f"   🥗 Еда: <b>{data['total_meals']}</b> | 🏋️‍♂️ Зал: <b>{data['total_workouts']}</b>\n"
                f"   ⚠️ Штрафы: <b>{data['total_penalty']}</b>{data['note']}\n"
                f"   📝 <i>Причины:</i> {reasons_display}")
        text_lines.append(line)
    
    full_text = "\n\n".join(text_lines)
    photo = BufferedInputFile(chart_buf.read(), filename="stats.png")

    # --- ФИКС ОШИБКИ "CAPTION TOO LONG" ---
    if len(full_text) > 1000:
        # Если текст длинный, отправляем график отдельно, текст отдельно
        msg_photo = await bot.send_photo(chat_id=chat_id, photo=photo, caption=f"📅 <b>{title}</b> (Подробности ниже)", parse_mode="HTML")
        await schedule_autodelete(bot, chat_id, msg_photo.message_id)
        
        # Текст (здесь лимит 4096 символов, точно влезет)
        msg_text = await bot.send_message(chat_id=chat_id, text=full_text, parse_mode="HTML")
        await schedule_autodelete(bot, chat_id, msg_text.message_id)
    else:
        # Если текст короткий, шлем как раньше (картинка + подпись)
        msg = await bot.send_photo(chat_id=chat_id, photo=photo, caption=full_text, parse_mode="HTML")
        await schedule_autodelete(bot, chat_id, msg.message_id)


@router.callback_query(F.data == "stats_today")
async def stats_today(call: CallbackQuery, bot: Bot):
    now = datetime.now()
    await call.message.delete()
    await send_stats_report(bot, call.message.chat.id, now, now, f"Отчет за {now.strftime('%d.%m')}")

@router.callback_query(F.data == "stats_week")
async def stats_week(call: CallbackQuery, bot: Bot):
    now = datetime.now()
    start = now - timedelta(days=now.weekday())
    await call.message.delete()
    await send_stats_report(bot, call.message.chat.id, start, now, "Отчет за неделю")

@router.callback_query(F.data == "stats_month")
async def stats_month(call: CallbackQuery, bot: Bot):
    now = datetime.now()
    start = now.replace(day=1)
    await call.message.delete()
    await send_stats_report(bot, call.message.chat.id, start, now, f"Отчет за {now.strftime('%B')}")

@router.callback_query(F.data == "stats_custom")
async def stats_custom(call: CallbackQuery, state: FSMContext):
    await call.message.edit_text("📅 Формат: <code>ДД.ММ.ГГГГ - ДД.ММ.ГГГГ</code>", parse_mode="HTML")
    await state.set_state(StatsState.waiting_for_dates)

@router.message(StateFilter(StatsState.waiting_for_dates))
async def process_custom_dates(message: Message, state: FSMContext, bot: Bot):
    try: await message.delete()
    except: pass

    try:
        raw = message.text.replace(" ", "")
        d1_str, d2_str = raw.split("-")
        d1 = datetime.strptime(d1_str, "%d.%m.%Y")
        d2 = datetime.strptime(d2_str, "%d.%m.%Y")
        
        await send_stats_report(bot, message.chat.id, d1, d2, f"Отчет: {d1_str} - {d2_str}")
        await state.clear()
        
    except ValueError:
        msg = await message.answer("⚠️ Ошибка формата.")
        await schedule_autodelete(bot, message.chat.id, msg.message_id)

# --- ОБРАБОТКА МЕДИА ---

@router.message(F.photo | F.video | F.video_note)
async def handle_media(message: Message, bot: Bot):
    user = await get_user_from_db(message.from_user.id)
    if not user: return

    caption = (message.caption or "").lower()
    content_type = None

    if any(tag in caption for tag in CHEAT_TAGS): content_type = "cheat"
    elif any(tag in caption for tag in WORKOUT_TAGS): content_type = "workout"
    elif any(tag in caption for tag in MEAL_TAGS): content_type = "meal"

    if message.photo:
        f_id = message.photo[-1].file_id
        f_type = "photo"
    elif message.video:
        f_id = message.video.file_id
        f_type = "video"
    elif message.video_note:
        f_id = message.video_note.file_id
        f_type = "video_note"

    if content_type:
        await process_submission(bot, user, f_id, f_type, content_type, message.chat.id, message.message_id)
    else:
        pending_media[message.from_user.id] = {
            "file_id": f_id, "file_type": f_type,
            "message_id": message.message_id, "timestamp": datetime.now()
        }

@router.message(F.text)
async def handle_tags(message: Message, bot: Bot):
    text = message.text.lower()
    is_cheat = any(tag in text for tag in CHEAT_TAGS)
    is_workout = any(tag in text for tag in WORKOUT_TAGS)
    is_meal = any(tag in text for tag in MEAL_TAGS)

    if not (is_workout or is_meal or is_cheat): return

    user_id = message.from_user.id
    last_media = pending_media.get(user_id)
    
    if last_media and (datetime.now() - last_media["timestamp"] < timedelta(minutes=5)):
        user = await get_user_from_db(user_id)
        c_type = "cheat" if is_cheat else ("workout" if is_workout else "meal")
        
        await process_submission(bot, user, last_media["file_id"], last_media["file_type"], c_type, message.chat.id, last_media["message_id"])
        del pending_media[user_id]
        
        try: await message.delete()
        except: pass

# --- МОДЕРАЦИЯ ---

@router.callback_query(F.data.startswith("approve_"))
async def approve(callback: CallbackQuery):
    sub_id = int(callback.data.split("_")[1])
    name = callback.from_user.first_name
    async with async_session() as session:
        sub = await session.get(Submission, sub_id)
        if sub:
            sub.verified = True
            await session.commit()
            
            original = callback.message.caption or callback.message.text
            if "\n" in original: original = original.split("\n")[1] 
            
            new_text = f"✅ <b>Принято</b>\n{original}\n(Подтвердил: {name})"
            
            if callback.message.caption:
                await callback.message.edit_caption(caption=new_text, reply_markup=None, parse_mode="HTML")
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data.startswith("reject_"))
async def reject(callback: CallbackQuery):
    sub_id = int(callback.data.split("_")[1])
    name = callback.from_user.first_name
    async with async_session() as session:
        sub = await session.get(Submission, sub_id)
        if sub:
            await session.delete(sub)
            await session.commit()
            
            original = callback.message.caption or callback.message.text
            if "\n" in original: original = original.split("\n")[1]
            
            new_text = f"❌ <b>Отклонено</b>\n{original}\n(Отклонил: {name})"
            
            if callback.message.caption:
                await callback.message.edit_caption(caption=new_text, reply_markup=None, parse_mode="HTML")
            else:
                await callback.message.edit_text(text=new_text, reply_markup=None, parse_mode="HTML")
    await callback.answer()