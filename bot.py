import os
import logging
from datetime import datetime

import groq
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

CATEGORIES = ['Здоровье', 'Настроение', 'Физактивность', 'Еда', 'Сон']
EMOJI = {
    'Здоровье':     '❤️',
    'Настроение':   '😊',
    'Физактивность':'💪',
    'Еда':          '🍎',
    'Сон':          '😴',
}

# Conversation states
SET_TIME, SCORE, COMMENT = range(3)


# ──────────────────────────────────────────────
# Keyboards
# ──────────────────────────────────────────────

def score_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(str(i), callback_data=f's{i}') for i in range(1, 6)],
        [InlineKeyboardButton(str(i), callback_data=f's{i}') for i in range(6, 11)],
    ])

def skip_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("Пропустить ➡️", callback_data='skip')]])


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

async def reply(update: Update, text: str, **kwargs):
    """Send a reply regardless of whether update has message or callback_query."""
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
        f"{EMOJI[cat]} *{cat}* {progress}\nОцени от 1 до 10:",
        reply_markup=score_kb(),
        parse_mode='Markdown'
    )


# ──────────────────────────────────────────────
# Onboarding
# ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_or_update_user(user.id, user.username or '', user.first_name or '')

    await update.message.reply_text(
        f"Привет, {user.first_name}! 👋\n\n"
        "Я помогу каждый день отслеживать самочувствие по 5 категориям:\n\n"
        "❤️ Здоровье\n"
        "😊 Настроение\n"
        "💪 Физактивность\n"
        "🍎 Еда\n"
        "😴 Сон\n\n"
        "Каждый день в выбранное время буду присылать напоминание. "
        "Ты ставишь оценку 1–10 и пишешь короткий комментарий.\n\n"
        "В какое время присылать напоминание?\n"
        "Напиши в формате ЧЧ:ММ, например `21:00`",
        parse_mode='Markdown'
    )
    return SET_TIME


async def save_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, '%H:%M')
    except ValueError:
        await update.message.reply_text(
            "Не понял формат 🤔 Напиши ЧЧ:ММ, например `21:00`",
            parse_mode='Markdown'
        )
        return SET_TIME

    db.set_reminder_time(update.effective_user.id, text)
    await update.message.reply_text(
        f"✅ Буду напоминать каждый день в *{text}*\n\n"
        "Команды:\n"
        "/fill — заполнить дневник прямо сейчас\n"
        "/stats — итоги недели\n"
        "/heatmap — тепловая карта за 30 дней\n"
        "/trends — динамика по категориям\n"
        "/time — изменить время напоминания",
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
    context.user_data['fill_date'] = datetime.now().strftime('%Y-%m-%d')

    await ask_category(update, context)
    return SCORE


async def handle_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    score = int(query.data[1:])  # strip leading 's'
    context.user_data['cur_score'] = score
    context.user_data['cur_cat'] = CATEGORIES[context.user_data['cat_idx']]

    await query.message.reply_text(
        f"*{score}/10* ✓\n\nДобавь комментарий или пропусти:",
        reply_markup=skip_kb(),
        parse_mode='Markdown'
    )
    return COMMENT


async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _save_and_next(update, context, update.message.text.strip())


async def handle_skip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await _save_and_next(update, context, None)


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
        await reply(update, "✅ *Готово! Всё записано.*\n\nХорошего вечера 🌙", parse_mode='Markdown')
        return ConversationHandler.END

    await ask_category(update, context)
    return SCORE


# ──────────────────────────────────────────────
# Change time
# ──────────────────────────────────────────────

async def cmd_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current = db.get_reminder_time(update.effective_user.id)
    await update.message.reply_text(
        f"Текущее время напоминания: *{current}*\n\nНапиши новое время (ЧЧ:ММ):",
        parse_mode='Markdown'
    )
    return SET_TIME


# ──────────────────────────────────────────────
# Analytics commands
# ──────────────────────────────────────────────

async def cmd_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    first_name = update.effective_user.first_name or 'пользователь'

    # Determine period from args: /summary 7 or /summary 30, default 7
    args = context.args
    try:
        days = int(args[0]) if args else 7
        days = max(3, min(days, 90))
    except (ValueError, IndexError):
        days = 7

    entries = db.get_entries(user_id, days)
    if not entries:
        await update.message.reply_text("Пока нет данных для анализа. Начни с /fill 📝")
        return

    # Format entries for the prompt
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

    prompt = f"""Ты заботливый и внимательный помощник, который анализирует дневник самочувствия.

Вот записи пользователя {first_name} за последние {days} дней:
{diary_text}

Напиши персональный анализ на русском языке. Структура:

1. **Общая картина** — кратко как прошёл период в целом, средние оценки по категориям
2. **Что бросается в глаза** — интересные паттерны, корреляции, динамика (например: "в дни с низкой физактивностью настроение тоже падало")
3. **Тревожные сигналы** — если что-то стабильно низкое или резко упало (если таких нет — не выдумывай)
4. **Маленький совет** — одна конкретная, практичная рекомендация на следующую неделю

Пиши тепло и по-человечески, без канцелярита. Не больше 300 слов."""

    msg = await update.message.reply_text("🤔 Анализирую твой дневник…")

    try:
        client = groq.Groq(api_key=os.environ['GROQ_API_KEY'])
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )
        analysis = response.choices[0].message.content
        await msg.delete()
        await update.message.reply_text(
            f"🧠 *Анализ за {days} дней*\n\n{analysis}",
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"AI summary error: {e}")
        await msg.edit_text("Что-то пошло не так при анализе. Попробуй позже 🙏")


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = analytics.get_weekly_summary(update.effective_user.id)
    if not text:
        await update.message.reply_text("Пока нет данных. Начни с /fill 📝")
        return
    await update.message.reply_text(text, parse_mode='Markdown')


async def cmd_heatmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Генерирую тепловую карту… 🔥")
    buf = analytics.generate_heatmap(update.effective_user.id)
    await msg.delete()
    if not buf:
        await update.message.reply_text("Пока нет данных. Начни с /fill 📝")
        return
    await update.message.reply_photo(buf, caption="🔥 Тепловая карта за 30 дней")


async def cmd_trends(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("Строю графики… 📈")
    buf = analytics.generate_trends(update.effective_user.id)
    await msg.delete()
    if not buf:
        await update.message.reply_text("Пока нет данных. Начни с /fill 📝")
        return
    await update.message.reply_photo(buf, caption="📈 Динамика за 14 дней")


# ──────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────

async def send_reminders(app: Application):
    current_time = datetime.now().strftime('%H:%M')
    for user_id, reminder_time in db.get_all_users():
        if reminder_time == current_time:
            try:
                await app.bot.send_message(
                    chat_id=user_id,
                    text="🌙 Привет! Как прошёл день?\nВремя заполнить дневник.",
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

    # Onboarding & change time — share the SET_TIME state handler
    time_conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', cmd_start),
            CommandHandler('time', cmd_time),
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
        ],
        states={
            SCORE:   [CallbackQueryHandler(handle_score, pattern=r'^s\d+$')],
            COMMENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment),
                CallbackQueryHandler(handle_skip, pattern='^skip$'),
            ],
        },
        fallbacks=[CommandHandler('fill', begin_fill)],
    )

    app.add_handler(time_conv)
    app.add_handler(fill_conv)
    app.add_handler(CommandHandler('stats',   cmd_stats))
    app.add_handler(CommandHandler('heatmap', cmd_heatmap))
    app.add_handler(CommandHandler('trends',  cmd_trends))
    app.add_handler(CommandHandler('summary', cmd_summary))

    # Scheduler runs every minute, checks who needs a reminder
    scheduler = AsyncIOScheduler(timezone='UTC')
    scheduler.add_job(send_reminders, 'cron', minute='*', args=[app])
    scheduler.start()

    logger.info("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
