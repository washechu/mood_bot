import os
import logging
import random
from datetime import datetime

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
import analytics

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


def score_color(score: int) -> str:
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
        ["📝 Заполнить дневник"],
        ["📊 Итоги недели", "📅 Итоги месяца"],
        ["📈 Динамика", "🧠 Анализ ИИ"],
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


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_or_update_user(user.id, user.username or '', user.first_name or '')
    await update.message.reply_text(
        f"Привет, {user.first_name} 👋\n\n"
        "Я помогу тебе лучше понимать себя.\n\n"
        "Каждый день мы будем отмечать пять сфер жизни — коротко и честно:\n\n"
        "💊 Здоровье — как чувствует себя тело\n"
        "😊 Настроение — что происходит внутри\n"
        "🏃 Активность — движение и энергия\n"
        "🍎 Еда — как ты питаешься\n"
        "😴 Сон — качество отдыха\n\n"
        "Эта практика помогает замечать паттерны, понимать что влияет на твоё состояние "
        "и постепенно делать жизнь лучше — без давления и осуждения.\n\n"
        "Всего пара минут в день — и ты начнёшь лучше слышать себя 🌱\n\n"
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
        f"Отлично, буду напоминать каждый день в *{text}* 🌙\n\nЯ здесь, когда понадоблюсь:",
        reply_markup=main_menu_kb(),
        parse_mode='Markdown'
    )
    return ConversationHandler.END


async def begin_fill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_or_update_user(user.id, user.username or '', user.first_name or '')
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data['cat_idx'] = 0
    context.user_data['fill_date'] = datetime.now().strftime('%Y-%m-%d')
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


async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = db.get_reminder_time(update.effective_user.id)
    await update.message.reply_text(
        f"Сейчас напоминание приходит в *{current}*\nВ какое время изменить? (ЧЧ:ММ)",
        parse_mode='Markdown'
    )
    return SET_TIME


async def get_ai_summary(user_id: int, days: int, mode: str) -> str | None:
    entries = db.get_entries(user_id, days)
    if not entries:
        return None

    by_date = {}
    for date, category, score, comment in entries:
        by_date.setdefault(date, []).append((category, score, comment))

    lines = []
    for date in sorted(by_date.keys()):
        lines.append(f"\n📅 {date}")
        for category, score, comment in by_date[date]:
            comment_str = f" — {comment}" if comment else ""
            lines.append(f"  {category}: {score}/10{comment_str}")
    diary_text = "\n".join(lines)

    if mode == 'week':
        structure = (
            "**Как прошла неделя** — 2-3 предложения общего впечатления\n"
            "**Что радует** — что шло хорошо, на что стоит опираться\n"
            "**На что обратить внимание** — что просит заботы, без осуждения\n"
            "**Связи** — есть ли заметные паттерны между категориями\n"
            "**Совет на следующую неделю** — один конкретный и добрый"
        )
        header = "🧠 *Взгляд на неделю*"
    elif mode == 'month':
        structure = (
            "**Месяц в целом** — общая картина и динамика\n"
            "**Сильные стороны** — что стабильно хорошо\n"
            "**Зоны роста** — где есть потенциал для улучшений\n"
            "**Главный паттерн** — самая интересная связь в данных\n"
            "**Намерение на следующий месяц** — одна мягкая рекомендация"
        )
        header = "🧠 *Взгляд на месяц*"
    else:
        structure = (
            "**Общая картина** — кратко о периоде\n"
            "**Что бросается в глаза** — паттерны и корреляции\n"
            "**Тревожные сигналы** — только если реально есть, иначе пропусти блок\n"
            "**Маленький совет** — один конкретный и добрый"
        )
        header = f"🧠 *Анализ за {days} дней*"

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
        analysis = response.choices[0].message.content
        return f"{header}\n\n{analysis}"
    except Exception as e:
        logger.error(f"AI summary error: {e}")
        return None


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("Собираю итоги недели… 🌿")
    text = analytics.get_text_week_stats(user_id)
    if not text:
        await msg.edit_text("Пока нет данных. Начни с дневника 📝")
        return
    ai_text = await get_ai_summary(user_id, 7, 'week')
    full = text + (f"\n\n{ai_text}" if ai_text else "")
    await msg.edit_text(full, parse_mode='Markdown')


async def cmd_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("Собираю итоги месяца… 🌿")
    text = analytics.get_text_month_stats(user_id)
    if not text:
        await msg.edit_text("Пока нет данных. Начни с дневника 📝")
        return
    ai_text = await get_ai_summary(user_id, 30, 'month')
    full = text + (f"\n\n{ai_text}" if ai_text else "")
    await msg.edit_text(full, parse_mode='Markdown')


async def cmd_trends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("Смотрю динамику… 📈")
    text = analytics.get_text_trends(user_id)
    if not text:
        await msg.edit_text("Пока нет данных. Начни с дневника 📝")
        return
    await msg.edit_text(text, parse_mode='Markdown')


async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("Анализирую твой дневник… 🧠")
    args = context.args or []
    try:
        days = int(args[0]) if args else 7
        days = max(3, min(days, 90))
    except (ValueError, IndexError):
        days = 7
    ai_text = await get_ai_summary(user_id, days, 'detailed')
    if not ai_text:
        await msg.edit_text("Пока нет данных для анализа 📝")
        return
    await msg.edit_text(ai_text, parse_mode='Markdown')


async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📊 Итоги недели":
        await cmd_stats(update, context)
    elif text == "📅 Итоги месяца":
        await cmd_monthly(update, context)
    elif text == "📈 Динамика":
        await cmd_trends(update, context)
    elif text == "🧠 Анализ ИИ":
        await cmd_summary(update, context)


async def send_reminders(app: Application):
    current_time = datetime.now().strftime('%H:%M')
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
    )

    fill_conv = ConversationHandler(
        entry_points=[
            CommandHandler('fill', begin_fill),
            CallbackQueryHandler(begin_fill, pattern='^fill_now$'),
            MessageHandler(filters.Regex("^📝 Заполнить дневник$"), begin_fill),
        ],
        states={
            SCORE:   [CallbackQueryHandler(handle_score, pattern=r'^s\d+$')],
            COMMENT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)],
        },
        fallbacks=[CommandHandler('fill', begin_fill)],
    )

    app.add_handler(time_conv)
    app.add_handler(fill_conv)
    app.add_handler(CommandHandler('stats',   cmd_stats))
    app.add_handler(CommandHandler('monthly', cmd_monthly))
    app.add_handler(CommandHandler('trends',  cmd_trends))
    app.add_handler(CommandHandler('summary', cmd_summary))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))

    scheduler = AsyncIOScheduler(timezone='UTC')
    scheduler.add_job(send_reminders, 'cron', minute='*', args=[app])
    scheduler.start()

    logger.info("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
