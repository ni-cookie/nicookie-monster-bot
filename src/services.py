import matplotlib.pyplot as plt
import io
import pandas as pd
from sqlalchemy import select, and_
from datetime import datetime
from src.database import User, Submission

# ID (Константы)
ID_NIKITA = 432998089
ID_DANIA = 818400806
ID_NYUTA = 510679050

# --- ГРАФИКИ ---
def generate_period_chart(stats_data: dict, title: str):
    if not stats_data:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "Нет данных", ha='center')
        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        buf.seek(0)
        plt.close()
        return buf

    names = list(stats_data.keys())
    penalties = [d['total_penalty'] for d in stats_data.values()]

    plt.style.use('bmh')
    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(names, penalties, color=['#4CAF50' if p==0 else '#F44336' for p in penalties], alpha=0.9)
    
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_ylabel("Штрафы", fontsize=12)
    plt.xticks(rotation=15 if len(names) > 3 else 0)

    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height, f'{int(height)}',
                ha='center', va='bottom', fontsize=12, fontweight='bold')

    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=100, bbox_inches='tight')
    buf.seek(0)
    plt.close()
    return buf

# --- МАТЕМАТИКА ---
async def calculate_stats_period(session, bot, chat_id, start_date: datetime, end_date: datetime):
    start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_date = end_date.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Обновление имен
    db_users = (await session.execute(select(User))).scalars().all()
    active_users = []
    
    for user in db_users:
        try:
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user.tg_id)
            if member.status in ['left', 'kicked']: continue
            if user.name != member.user.full_name:
                user.name = member.user.full_name
                session.add(user)
            active_users.append(user)
        except: continue
    await session.commit()

    final_stats = {}
    all_days = pd.date_range(start_date, end_date).to_pydatetime()
    
    for user in active_users:
        user_penalty_sum = 0
        user_meals_count = 0
        user_workouts_count = 0
        penalty_reasons = []
        
        subs = (await session.execute(select(Submission).where(
            and_(Submission.user_id == user.id, Submission.timestamp >= start_date, 
                 Submission.timestamp <= end_date, Submission.verified == True)
        ))).scalars().all()

        for day in all_days:
            d_start = day.replace(hour=0, minute=0, second=0, microsecond=0)
            d_end = day.replace(hour=23, minute=59, second=59, microsecond=999999)
            day_str = day.strftime("%d.%m")
            
            day_subs = [s for s in subs if d_start <= s.timestamp <= d_end]
            
            meals = [s for s in day_subs if s.type in ["meal", "cheat"]]
            cheats = [s for s in day_subs if s.type == "cheat"]
            workouts = [s for s in day_subs if s.type in ["workout", "video_note"]]
            
            user_meals_count += len(meals)
            user_workouts_count += len(workouts)
            
            daily_penalty = 0
            day_reasons = []

            # 1. НИКИТА
            if user.tg_id == ID_NIKITA:
                if len(meals) == 0:
                    daily_penalty += 1
                    day_reasons.append("Нет еды")
                if len(cheats) > 0:
                    daily_penalty += len(cheats)
                    day_reasons.append(f"Читы ({len(cheats)})")

            # 2. ДАНЯ
            elif user.tg_id == ID_DANIA:
                if len(meals) == 0:
                    daily_penalty += 1
                    day_reasons.append("Нет еды")
                if len(workouts) == 0:
                    daily_penalty += 1
                    day_reasons.append("Пропуск зала")
                if len(cheats) > 0:
                    daily_penalty += len(cheats)
                    day_reasons.append(f"Читы ({len(cheats)})")

            # 3. НЮТА
            elif user.tg_id == ID_NYUTA:
                # Еда: минимум 3
                if len(meals) < 3:
                    daily_penalty += 1
                    day_reasons.append(f"Мало еды ({len(meals)}/3)")
                # Зал: Тут НЕ считаем, считаем в конце периода
            
            # 4. ОСТАЛЬНЫЕ
            else:
                if len(meals) == 0: 
                    daily_penalty += 1
                    day_reasons.append("Нет еды")
                if len(workouts) == 0: 
                    daily_penalty += 1
                    day_reasons.append("Нет зала")
                if len(cheats) > 0:
                    daily_penalty += len(cheats)
                    day_reasons.append(f"Читы ({len(cheats)})")

            user_penalty_sum += daily_penalty
            if day_reasons:
                penalty_reasons.append(f"{day_str}: {', '.join(day_reasons)}")

        # --- ПОСТ-ОБРАБОТКА ДЛЯ НЮТЫ (ЗАЛ) ---
        note_text = ""
        if user.tg_id == ID_NYUTA:
            # Цель: 12 - 4 = 8 тренировок
            TARGET_GYM = 8
            
            # Сколько не хватает до цели?
            missing_gym = max(0, TARGET_GYM - user_workouts_count)
            
            if missing_gym > 0:
                user_penalty_sum += missing_gym
                penalty_reasons.append(f"Зал (Месяц): Осталось сходить {missing_gym} раз(а)")
            
            note_text = f" (План: 8/мес. Сделано: {user_workouts_count})"

        reason_str = "\n      └ " + "\n      └ ".join(penalty_reasons) if penalty_reasons else "Нет"

        final_stats[user.name] = {
            'total_penalty': user_penalty_sum,
            'total_meals': user_meals_count,
            'total_workouts': user_workouts_count,
            'reasons': reason_str,
            'note': note_text
        }

    return final_stats