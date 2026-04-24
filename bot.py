import os
import logging
import random
from datetime import datetime, timedelta, timezone

import groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db

logging.basicConfig(
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ['BOT_TOKEN']

CATEGORIES = ['Здоровье', 'Настроение', 'Активность', 'Еда', 'Сон']
EMOJI = {
    'Здоровье':   '💊',
    'Настроение': '😊',
    'Активность': '🏃',
    'Еда':        '🍎',
    'Сон':        '😴',
}

QUOTES = [
    "Каждый день — это маленький шаг к лучшей версии себя 🌱",
    "Ты уже сделал что-то важное — остановился и прислушался к себе 💙",
    "Забота о себе — это не эгоизм, это необходимость 🤍",
    "Хорошие дни складываются из маленьких осознанных моментов ✨",
    "Даже если сегодня было непросто — ты справился. Это уже победа 🙌",
    "Внимание к себе — первый шаг к изменениям 🪴",
    "Ты молодец, что не забываешь о себе 💫",
    "Каждая запись в дневнике — это акт самолюбви 🌸",
    "Маленькие ритуалы создают большие перемены 🌊",
    "Слышать себя — это навык. Ты его тренируешь 🎯",
]

REMINDER_MESSAGES = [
    "Привет 🌙 Как прошёл твой день?\nДавай немного побудем с собой — заполни дневник.",
    "Время для себя ✨ Как ты сегодня?\nПара минут честного разговора с собой — и день завершён.",
    "Добрый вечер 🌿 Поймай этот момент — как ты себя чувствуешь?\nЗаполни дневник, пока день ещё свеж.",
    "Тихий момент для тебя 🕯️ Как было сегодня?\nПрислушайся к себе — и расскажи.",
    "Один вопрос на вечер 🌛 Как ты?\nЗапиши — даже если день был обычным. Особенно если был обычным.",
]

COMMENT_PROMPTS = {
    'Здоровье':   "Что с самочувствием? Есть что-то, на что стоит обратить внимание? 🩺",
    'Настроение': "Что повлияло на настроение сегодня? Что стоит за этой оценкой? 💭",
    'Активность': "Как двигалось тело сегодня? Что давало энергию — или забирало её? ⚡",
    'Еда':        "Как питался сегодня? Было что-то особенное — или наоборот? 🍽️",
    'Сон':        "Как спалось? Что могло повлиять на качество сна? 🌙",
}

SET_TIME, SCORE, COMMENT = range(3)

MOSCOW_TZ = timezone(timedelta(hours=3))


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def moscow_now():
    return datetime.now(MOSCOW_TZ)


def score_color(score) -> str:
    if score is None:
        return "⬛"
    score = float(score)
    if score <= 5:
        return "⬜"
    elif score <= 7:
        return "🟨"
    else:
        return "🟩"


def score_kb() -> InlineKeyboardMarkup:
    def btn(i):
        return InlineKeyboardButton(f"{score_color(i)} {i}", callback_data=f's{i}')
    return InlineKeyboardMarkup([
        [btn(i) for i in range(1, 6)],
        [btn(i) for i in range(6, 11)],
    ])


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup([
        ["📝 Заполнить"],
        ["📅 Календарь", "📈 Динамика"],
        ["⏰ Изменить время"],
    ], resize_keyboard=True)


async def reply(update: Update, text: str, **kwargs):
    if update.callback_query:
        await update.callback_query.message.reply_text(text, **kwargs)
    else:
        await update.message.reply_text(text, **kwargs)


async def ask_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['cat_idx']
    cat = CATEGORIES[idx]
    progress = f"({idx + 1}/{len(CATEGORIES)})"
    await reply(
        update,
        f"{EMOJI[cat]} *{cat}* {progress}\nКак оцениваешь от 1 до 10?",
        reply_markup=score_kb(),
        parse_mode='Markdown'
    )


def entries_by_date(entries):
    by_date = {}
    for date, category, score, comment in entries:
        day = str(date)[:10]
        by_date.setdefault(day, {})[category] = (score, comment)
    return by_date


# ──────────────────────────────────────────────
# AI summary
# ──────────────────────────────────────────────

async def get_ai_summary(user_id: int, days: int, mode: str) -> str:
    entries = db.get_entries(user_id, days)
    if not entries:
        return ""

    by_date = {}
    for date, category, score, comment in entries:
        by_date.setdefault(str(date)[:10], []).append((category, score, comment))

    lines = []
    for date in sorted(by_date.keys()):
        lines.append(f"\n📅 {date}")
        for category, score, comment in by_date[date]:
            comment_str = f" — {comment}" if comment else ""
            lines.append(f"  {category}: {score}/10{comment_str}")
    diary_text = "\n".join(lines)

    if mode == 'calendar':
        structure = (
            "**Как прошла неделя** — 2-3 предложения общего впечатления\n"
            "**Что радует** — что шло хорошо, на что стоит опираться\n"
            "**На что обратить внимание** — что просит заботы, без осуждения\n"
            "**Связи** — есть ли заметные паттерны между категориями\n"
            "**Совет на следующую неделю** — один конкретный и добрый"
        )
        header = "🧠 *Взгляд на неделю*"
    else:
        structure = (
            "**Месяц в целом** — общая картина и динамика\n"
            "**Сильные стороны** — что стабильно хорошо\n"
            "**Зоны роста** — где есть потенциал для улучшений\n"
            "**Главный паттерн** — самая интересная связь в данных\n"
            "**Намерение на следующий месяц** — одна мягкая рекомендация"
        )
        header = "🧠 *Взгляд на месяц*"

    prompt = (
        f"Ты тёплый и внимательный помощник по самонаблюдению. "
        f"Твоя задача — помочь человеку лучше понять себя через данные дневника. "
        f"Пиши мягко, поддерживающе, без осуждения и без излишнего пафоса.\n\n"
        f"Данные дневника за {days} дней:\n{diary_text}\n\n"
        f"Структура ответа (строго следуй ей):\n{structure}\n\n"
        f"Важно: пиши на русском, тепло и по-человечески. "
        f"Не больше 250 слов. Используй *жирный* markdown для заголовков блоков."
    )

    try:
        client = groq.Groq(api_key=os.environ['GROQ_API_KEY'])
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        return f"{header}\n\n{response.choices[0].message.content}"
    except Exception as e:
        logger.error(f"AI summary error: {e}")
        return ""


# ──────────────────────────────────────────────
# Onboarding
# ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_or_update_user(user.id, user.username or '', user.first_name or '')
    await update.message.reply_text(
        f"Привет, {user.first_name} 👋\n\n"
        "Я помогу тебе лучше понимать себя.\n\n"
        "Каждый день мы будем отмечать пять сфер жизни — коротко и честно:\n\n"
        "💊 Здоровье — как чувствует себя тело\n"
        "😊 Настроение — что происходит внутри\n"
        "🏃 Активность — движение и спорт\n"
        "🍎 Еда — как ты питаешься\n"
        "😴 Сон — качество отдыха\n\n"
        "Эта практика помогает замечать паттерны и понимать, что влияет на твоё состояние. "
        "Лучше всего заполнять вечером, перед сном — когда день уже прожит 🌙\n\n"
        "В какое время мне напоминать тебе каждый день?\nНапиши в формате ЧЧ:ММ, например `21:00`",
        parse_mode='Markdown'
    )
    return SET_TIME


async def save_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, '%H:%M')
    except ValueError:
        await update.message.reply_text(
            "Не совсем понял формат 🙏 Напиши время вот так: `21:00`",
            parse_mode='Markdown'
        )
        return SET_TIME
    db.set_reminder_time(update.effective_user.id, text)
    await update.message.reply_text(
        f"Отлично, буду напоминать каждый день в *{text}* 🌙",
        reply_markup=main_menu_kb(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


# ──────────────────────────────────────────────
# Fill diary
# ──────────────────────────────────────────────

async def begin_fill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_or_update_user(user.id, user.username or '', user.first_name or '')
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data['cat_idx'] = 0
    context.user_data['fill_date'] = moscow_now().strftime('%Y-%m-%d')
    await reply(update, "Хорошо, давай пройдёмся по дню 🌿\nОтвечай честно — здесь нет правильных ответов.")
    await ask_category(update, context)
    return SCORE


async def handle_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    score = int(query.data[1:])
    context.user_data['cur_score'] = score
    cat = CATEGORIES[context.user_data['cat_idx']]
    context.user_data['cur_cat'] = cat
    prompt = COMMENT_PROMPTS.get(cat, "Хочешь добавить что-нибудь?")
    await query.message.reply_text(
        f"*{score_color(score)} {score}/10*\n\n{prompt}",
        parse_mode='Markdown'
    )
    return COMMENT


async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _save_and_next(update, context, update.message.text.strip())


async def _save_and_next(update: Update, context: ContextTypes.DEFAULT_TYPE, comment):
    user_id = update.effective_user.id
    db.save_entry(
        user_id,
        context.user_data['fill_date'],
        context.user_data['cur_cat'],
        context.user_data['cur_score'],
        comment
    )
    context.user_data['cat_idx'] += 1
    if context.user_data['cat_idx'] >= len(CATEGORIES):
        quote = random.choice(QUOTES)
        await reply(
            update,
            f"✅ *Записано. Спасибо, что нашёл время для себя.*\n\n_{quote}_",
            parse_mode='Markdown',
            reply_markup=main_menu_kb()
        )
        return ConversationHandler.END
    await ask_category(update, context)
    return SCORE


# ──────────────────────────────────────────────
# Change time
# ──────────────────────────────────────────────

async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = db.get_reminder_time(update.effective_user.id)
    await update.message.reply_text(
        f"Сейчас напоминание приходит в *{current}*\nВ какое время изменить? (ЧЧ:ММ)",
        parse_mode='Markdown'
    )
    return SET_TIME


# ──────────────────────────────────────────────
# Calendar — 7 days, rows = categories, cols = days, each cell tappable
# ──────────────────────────────────────────────

async def cmd_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("Собираю календарь… 📅")

    today = moscow_now().date()
    days = [(today - timedelta(days=i)) for i in range(29, -1, -1)]
    entries = db.get_entries(user_id, 30)
    by_date = entries_by_date(entries)

    start_str = days[0].strftime('%d.%m')
    end_str = days[-1].strftime('%d.%m')
    text = f"📅 *Календарь* ({start_str} — {end_str})\n\n"

    keyboard = []
    for cat in CATEGORIES:
        emoji = EMOJI[cat]
        text += f"{emoji} *{cat}*\n"
        row = []
        for day in days:
            day_str = day.strftime('%Y-%m-%d')
            score = by_date.get(day_str, {}).get(cat, (None, None))[0]
            color = score_color(score)
            cat_idx = CATEGORIES.index(cat)
            row.append(InlineKeyboardButton(
                color,
                callback_data=f"cal_{day_str}_{cat_idx}"
            ))
        keyboard.append(row)

    text += "\n⬜ 1–5  🟨 6–7  🟩 8–10  ⬛ нет данных"

    ai_text = await get_ai_summary(user_id, 30, 'calendar')
    if ai_text:
        text += f"\n\n{ai_text}"

    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def handle_calendar_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, date_str, cat_idx_str = query.data.split('_', 2)
    cat = CATEGORIES[int(cat_idx_str)]
    emoji = EMOJI[cat]

    entries = db.get_entries(query.from_user.id, 60)
    by_date = entries_by_date(entries)

    day_data = by_date.get(date_str, {}).get(cat)
    date_fmt = datetime.strptime(date_str, '%Y-%m-%d').strftime('%d %B')

    if day_data is None:
        await query.message.reply_text(
            f"{emoji} *{cat} · {date_fmt}*\n\n_Нет данных за этот день_",
            parse_mode='Markdown'
        )
    else:
        score, comment = day_data
        color = score_color(score)
        comment_text = f"\n\n_{comment}_" if comment else ""
        await query.message.reply_text(
            f"{emoji} *{cat} · {date_fmt}*\n\n{color} *{score}/10*{comment_text}",
            parse_mode='Markdown'
        )


# ──────────────────────────────────────────────
# Dynamics — progress bars per category, 30 days, each cell tappable
# ──────────────────────────────────────────────

async def cmd_dynamics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("Собираю динамику… 📈")

    today = moscow_now().date()
    days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    entries = db.get_entries(user_id, 7)
    by_date = entries_by_date(entries)

    start_str = days[0].strftime('%d.%m')
    end_str = days[-1].strftime('%d.%m')
    text = f"📈 *Динамика* ({start_str} — {end_str})\n\n"

    keyboard = []
    for cat in CATEGORIES:
        emoji = EMOJI[cat]
        scores = []
        row = []
        for day in days:
            day_str = day.strftime('%Y-%m-%d')
            score = by_date.get(day_str, {}).get(cat, (None, None))[0]
            scores.append(score)
            color = score_color(score)
            cat_idx = CATEGORIES.index(cat)
            row.append(InlineKeyboardButton(
                color,
                callback_data=f"dyn_{day.strftime('%Y-%m-%d')}_{cat_idx}"
            ))

        filled = [s for s in scores if s is not None]
        avg = sum(filled) / len(filled) if filled else None
        avg_str = f"  _{avg:.1f}_" if avg is not None else ""
        text += f"{emoji} *{cat}*{avg_str}\n"
        keyboard.append(row)

    text += "\n⬜ 1–5  🟨 6–7  🟩 8–10  ⬛ нет данных\n_← 7 дней назад · сегодня →_"

    ai_text = await get_ai_summary(user_id, 7, 'calendar')
    if ai_text:
        text += f"\n\n{ai_text}"

    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')


async def handle_dynamics_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, date_str, cat_idx_str = query.data.split('_', 2)
    cat = CATEGORIES[int(cat_idx_str)]
    emoji = EMOJI[cat]

    entries = db.get_entries(query.from_user.id, 60)
    by_date = entries_by_date(entries)

    day_data = by_date.get(date_str, {}).get(cat)
    date_fmt = datetime.strptime(date_str, '%Y-%m-%d').strftime('%d %B')

    if day_data is None:
        await query.message.reply_text(
            f"{emoji} *{cat} · {date_fmt}*\n\n_Нет данных за этот день_",
            parse_mode='Markdown'
        )
    else:
        score, comment = day_data
        color = score_color(score)
        comment_text = f"\n\n_{comment}_" if comment else ""
        await query.message.reply_text(
            f"{emoji} *{cat} · {date_fmt}*\n\n{color} *{score}/10*{comment_text}",
            parse_mode='Markdown'
        )


# ──────────────────────────────────────────────
# Menu button handler
# ──────────────────────────────────────────────

async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📅 Календарь":
        await cmd_calendar(update, context)
    elif text == "📈 Динамика":
        await cmd_dynamics(update, context)


# ──────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────

async def send_reminders(app: Application):
    current_time = moscow_now().strftime('%H:%M')
    for user_id, reminder_time in db.get_all_users():
        if reminder_time == current_time:
            try:
                msg = random.choice(REMINDER_MESSAGES)
                await app.bot.send_message(
                    chat_id=user_id,
                    text=msg,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("📝 Заполнить", callback_data='fill_now')
                    ]])
                )
            except Exception as e:
                logger.warning(f"Reminder failed for user {user_id}: {e}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    db.init_db()
    app = Application.builder().token(TOKEN).build()

    time_conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', cmd_start),
            CommandHandler('time', cmd_time),
            MessageHandler(filters.Regex("^⏰ Изменить время$"), cmd_time),
        ],
        states={
            SET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_time)]
        },
        fallbacks=[CommandHandler('start', cmd_start)],
        allow_reentry=True,
    )

    fill_conv = ConversationHandler(
        entry_points=[
            CommandHandler('fill', begin_fill),
            CallbackQueryHandler(begin_fill, pattern='^fill_now$'),
            MessageHandler(filters.Regex("^📝 Заполнить$"), begin_fill),
        ],
        states={
            SCORE:   [CallbackQueryHandler(handle_score, pattern=r'^s\d+$')],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)],
        },
        fallbacks=[CommandHandler('fill', begin_fill)],
        allow_reentry=True,
    )

    app.add_handler(time_conv)
    app.add_handler(fill_conv)
    app.add_handler(CallbackQueryHandler(handle_calendar_tap, pattern=r'^cal_'))
    app.add_handler(CallbackQueryHandler(handle_dynamics_tap, pattern=r'^dyn_'))
    app.add_handler(CommandHandler('calendar', cmd_calendar))
    app.add_handler(CommandHandler('dynamics', cmd_dynamics))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))

    scheduler = AsyncIOScheduler(timezone='UTC')
    scheduler.add_job(send_reminders, 'cron', minute='*', args=[app])
    scheduler.start()

    logger.info("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
