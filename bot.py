import os
import logging
import random
import threading
from datetime import datetime, timedelta, timezone

from openai import AsyncOpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ConversationHandler, ContextTypes, filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import database as db

logging.basicConfig(format='%(asctime)s [%(levelname)s] %(name)s: %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ['BOT_TOKEN']
MOSCOW_TZ = timezone(timedelta(hours=3))

CATEGORIES = ['Здоровье', 'Настроение', 'Активность', 'Еда', 'Сон', 'Саморазвитие']
EMOJI = {
    'Здоровье':     '💊',
    'Настроение':   '😊',
    'Активность':   '🏃',
    'Еда':          '🍎',
    'Сон':          '😴',
    'Саморазвитие': '📚',
}

IMAGES = [
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_bicycle.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_cooking.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_english.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_jumping.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_pancakes.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_reading.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_running.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_sleeping.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_train.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_training.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_walking.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_watching.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_working.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_camping.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_climbing.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_meditation.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_shopping_2.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_kosmos.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_mountin.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_paris.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_president.png",
    "https://raw.githubusercontent.com/washechu/mood_bot/main/images/g_surfing.png",
]

# url -> telegram file_id (persists for lifetime of process)
_image_file_ids: dict[str, str] = {}

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
    'Здоровье':     "Что с самочувствием? Есть что-то, на что стоит обратить внимание? 🩺",
    'Настроение':   "Что повлияло на настроение сегодня? Что стоит за этой оценкой? 💭",
    'Активность':   "Как двигалось тело сегодня? Что давало энергию — или забирало её? ⚡",
    'Еда':          "Как питался сегодня? Было что-то особенное — или наоборот? 🍽️",
    'Сон':          "Как спалось? Что могло повлиять на качество сна? 🌙",
    'Саморазвитие': "Что нового сегодня? Книга, урок, идея, открытие — даже маленькое считается 📖",
}

SYSTEM_PROMPT = """Ты заботливый помощник по практике самонаблюдения.
Помогаешь людям лучше понимать себя через ежедневный дневник самочувствия.
Человек каждый день оценивает 6 сфер жизни по шкале 1-10 и оставляет комментарии:
💊 Здоровье, 😊 Настроение, 🏃 Активность, 🍎 Еда, 😴 Сон, 📚 Саморазвитие.
Цель практики — замечать паттерны и лучше понимать что влияет на состояние.
Твой тон: тёплый, честный, поддерживающий — без пафоса, осуждения и излишнего оптимизма.
Пиши ТОЛЬКО на русском языке, включая все заголовки."""

SET_TIME, SCORE, COMMENT = range(3)


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
        ["📈 Динамика"],
        ["🔔 Напоминание"],
    ], resize_keyboard=True)


def entries_by_date(entries):
    by_date = {}
    for date, category, score, comment in entries:
        day = str(date)[:10]
        by_date.setdefault(day, {})[category] = (score, comment)
    return by_date


def get_streak(user_id: int) -> int:
    entries = db.get_entries(user_id, 90)
    if not entries:
        return 0
    days_with_data = set(str(e[0])[:10] for e in entries)
    today = moscow_now().date()
    check = today
    if today.strftime('%Y-%m-%d') not in days_with_data:
        check = today - timedelta(days=1)
    streak = 0
    while check.strftime('%Y-%m-%d') in days_with_data:
        streak += 1
        check -= timedelta(days=1)
    return streak


def ai_client():
    return AsyncOpenAI(
        api_key=os.environ['ROUTER_AI_KEY'],
        base_url="https://routerai.ru/api/v1"
    )


# ──────────────────────────────────────────────
# AI: daily summary
# ──────────────────────────────────────────────

async def get_daily_summary(entries_today: list) -> str:
    if not entries_today:
        return ""
    lines = []
    scores = []
    for category, score, comment in entries_today:
        comment_str = f" — {comment}" if comment else ""
        lines.append(f"{EMOJI.get(category, '')} {category}: {score}/10{comment_str}")
        scores.append(score)
    today_text = "\n".join(lines)

    avg = sum(scores) / len(scores) if scores else 5
    if avg >= 7.5:
        tone = (
            "Тон: тёплый и немного приподнятый — день был хорошим, отрази это. "
            "Можно отметить что-то конкретно позитивное. Заверши с лёгкостью."
        )
    elif avg >= 5:
        tone = (
            "Тон: спокойный и поддерживающий — день был средним, не преувеличивай ни хорошее ни плохое. "
            "Просто будь рядом. Заверши мягко."
        )
    else:
        tone = (
            "Тон: очень бережный и тихий — день был тяжёлым. Не давай советов, не ищи позитив. "
            "Просто признай что было непросто и пожелай отдыха."
        )

    prompt = (
        f"Вот записи за сегодня:\n{today_text}\n\n"
        f"Напиши отклик на день — ровно два коротких абзаца, разделённых пустой строкой.\n"
        f"Первый абзац: одно-два предложения — что заметил в этом дне. Опирайся на конкретные детали из записей, не обобщай.\n"
        f"Второй абзац: одно предложение — тёплое завершение или пожелание на вечер.\n"
        f"{tone} "
        f"Не восклицай, не заискивай, не используй слова 'противоречие', 'баланс', 'гармония'. "
        f"Только русский язык, без markdown."
    )
    for attempt in range(2):
        try:
            response = await ai_client().chat.completions.create(
                model="deepseek/deepseek-v4-pro",
                max_tokens=500,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            choice = response.choices[0]
            content = choice.message.content
            if content:
                return content.strip()
            logger.warning(f"Daily summary empty content, finish_reason={choice.finish_reason}")
        except Exception as e:
            logger.error(f"Daily summary error (attempt {attempt + 1}): {e}")
    return ""


# ──────────────────────────────────────────────
# AI: period summary
# ──────────────────────────────────────────────

async def get_ai_summary(user_id: int, days: int, mode: str) -> str:
    entries = db.get_entries(user_id, days)
    if not entries:
        return ""

    by_date = {}
    for date, category, score, comment in entries:
        by_date.setdefault(str(date)[:10], []).append((category, score, comment))

    min_days = 3 if days == 7 else 10
    if len(by_date) < min_days:
        if mode == 'week':
            return f"_Для анализа недели нужно минимум 3 дня — сейчас есть {len(by_date)}. Возвращайся через несколько дней 🌱_"
        else:
            return f"_Для анализа месяца нужно минимум 10 дней — сейчас есть {len(by_date)}. Продолжай заполнять дневник 🌱_"

    lines = []
    for date in sorted(by_date.keys()):
        lines.append(f"\n📅 {date}")
        for category, score, comment in by_date[date]:
            comment_str = f" — {comment}" if comment else ""
            lines.append(f"  {category}: {score}/10{comment_str}")
    diary_text = "\n".join(lines)

    if mode == 'week':
        structure = (
            "_Как прошла неделя_\n1-2 предложения\n\n"
            "_Что радует_\n1-2 предложения\n\n"
            "_На что обратить внимание_\n1-2 предложения\n\n"
            "_Совет_\nОдно предложение"
        )
        header = "🧠 *Взгляд на неделю*"
    else:
        structure = (
            "_Месяц в целом_\n1-2 предложения\n\n"
            "_Сильные стороны_\n1-2 предложения\n\n"
            "_Зоны роста_\n1-2 предложения\n\n"
            "_Намерение_\nОдно предложение"
        )
        header = "🧠 *Взгляд на месяц*"

    prompt = (
        f"Данные дневника за {days} дней:{diary_text}\n\n"
        f"Напиши анализ строго по этой структуре:\n{structure}\n\n"
        f"Требования:\n"
        f"- Строго не больше 120 слов суммарно\n"
        f"- Названия блоков как в структуре (курсивом через _)\n"
        f"- Текст внутри блоков — обычный, без markdown\n"
        f"- Пустая строка между блоками\n"
        f"- Только русский язык"
    )
    for attempt in range(2):
        try:
            response = await ai_client().chat.completions.create(
                model="deepseek/deepseek-v4-pro",
                max_tokens=2000,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            choice = response.choices[0]
            content = choice.message.content
            if content:
                return f"{header}\n\n{content.strip()}"
            logger.warning(f"AI summary empty content, finish_reason={choice.finish_reason}")
        except Exception as e:
            logger.error(f"AI summary error (attempt {attempt + 1}): {e}")
    return ""


# ──────────────────────────────────────────────
# Dynamics
# ──────────────────────────────────────────────

async def build_dynamics(user_id: int, days: int):
    today = moscow_now().date()
    day_list = [(today - timedelta(days=i)) for i in range(days - 1, -1, -1)]
    entries = db.get_entries(user_id, days)
    by_date = entries_by_date(entries)

    start_str = day_list[0].strftime('%d.%m')
    end_str = day_list[-1].strftime('%d.%m')
    period = "неделю" if days == 7 else "месяц"
    header = f"📈 *Динамика за {period}* ({start_str} — {end_str})"

    keyboard = []
    if days == 7:
        for cat in CATEGORIES:
            cat_idx = CATEGORIES.index(cat)
            scores, day_row = [], []
            for day in day_list:
                day_str = day.strftime('%Y-%m-%d')
                score = by_date.get(day_str, {}).get(cat, (None, None))[0]
                scores.append(score)
                day_row.append(InlineKeyboardButton(
                    score_color(score),
                    callback_data=f"dyn_{day.strftime('%Y-%m-%d')}_{cat_idx}"
                ))
            filled = [s for s in scores if s is not None]
            avg = f"  {sum(filled)/len(filled):.1f}" if filled else ""
            keyboard.append([InlineKeyboardButton(f"{EMOJI[cat]} {cat}{avg}", callback_data="noop")])
            keyboard.append(day_row)
    else:
        weeks = [day_list[i:i+7] for i in range(0, len(day_list), 7)]
        for cat in CATEGORIES:
            cat_idx = CATEGORIES.index(cat)
            week_row = []
            for week in weeks:
                week_scores = [by_date.get(d.strftime('%Y-%m-%d'), {}).get(cat, (None, None))[0] for d in week]
                filled = [s for s in week_scores if s is not None]
                avg = sum(filled) / len(filled) if filled else None
                label = f"{score_color(avg)} {week[0].day}"
                week_row.append(InlineKeyboardButton(
                    label, callback_data=f"week_{week[0].strftime('%Y-%m-%d')}_{cat_idx}"
                ))
            keyboard.append([InlineKeyboardButton(f"{EMOJI[cat]} {cat}", callback_data="noop")])
            keyboard.append(week_row)

    mode = 'week' if days == 7 else 'month'
    keyboard.append([
        InlineKeyboardButton("📅 Показать месяц", callback_data="dyn_toggle_30")
        if days == 7 else
        InlineKeyboardButton("📅 Показать неделю", callback_data="dyn_toggle_7"),
        InlineKeyboardButton("🧠 Анализ недели" if days == 7 else "🧠 Анализ месяца", callback_data=f"dyn_ai_{days}_{mode}"),
    ])

    return header, InlineKeyboardMarkup(keyboard)


# ──────────────────────────────────────────────
# Onboarding
# ──────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_or_update_user(user.id, user.username or '', user.first_name or '')
    await update.message.reply_text(
        f"Привет, {user.first_name} 👋\n\n"
        "Я помогу тебе лучше понимать себя.\n\n"
        "Каждый день мы будем отмечать шесть сфер жизни — коротко и честно:\n\n"
        "💊 Здоровье — как чувствует себя тело\n"
        "😊 Настроение — что происходит внутри\n"
        "🏃 Активность — движение и спорт\n"
        "🍎 Еда — как ты питаешься\n"
        "😴 Сон — качество отдыха\n"
        "📚 Саморазвитие — книга, урок, новая идея\n\n"
        "Эта практика помогает замечать паттерны и понимать, что влияет на твоё состояние. "
        "Лучше всего заполнять вечером, перед сном 🌙\n\n"
        "Давай прямо сейчас заполним первую запись!",
        parse_mode='Markdown'
    )
    context.user_data['cat_idx'] = 0
    context.user_data['fill_date'] = moscow_now().strftime('%Y-%m-%d')
    context.user_data['onboarding'] = True
    await ask_category(update, context)
    return SCORE


async def save_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    try:
        datetime.strptime(text, '%H:%M')
    except ValueError:
        await update.message.reply_text("Не совсем понял формат 🙏 Напиши время вот так: `21:00`", parse_mode='Markdown')
        return SET_TIME
    db.set_reminder_time(update.effective_user.id, text)
    await update.message.reply_text(
        f"Готово! Буду напоминать каждый день в *{text}* 🌙",
        reply_markup=main_menu_kb(), parse_mode='Markdown'
    )
    return ConversationHandler.END


# ──────────────────────────────────────────────
# Fill diary
# ──────────────────────────────────────────────

async def ask_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['cat_idx']
    cat = CATEGORIES[idx]
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"{EMOJI[cat]} *{cat}*\nКак оцениваешь от 1 до 10?",
        reply_markup=score_kb(),
        parse_mode='Markdown'
    )


async def begin_fill(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.add_or_update_user(user.id, user.username or '', user.first_name or '')
    if update.callback_query:
        await update.callback_query.answer()
    context.user_data['cat_idx'] = 0
    context.user_data['fill_date'] = moscow_now().strftime('%Y-%m-%d')
    context.user_data['onboarding'] = False
    intro = "Ты уже заполнял сегодня — но можешь обновить записи 🌿" if db.has_entry_today(user.id) else "Хорошо, давай пройдёмся по дню 🌿\nОтвечай честно — здесь нет правильных ответов."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=intro)
    await ask_category(update, context)
    return SCORE


async def handle_text_in_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Нажми на цифру выше 👆")
    return SCORE


async def handle_score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    score = int(query.data[1:])
    context.user_data['cur_score'] = score
    cat = CATEGORIES[context.user_data['cat_idx']]
    context.user_data['cur_cat'] = cat
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"*{score_color(score)} {score}/10*\n\n{COMMENT_PROMPTS.get(cat, 'Хочешь добавить что-нибудь?')}",
        parse_mode='Markdown'
    )
    return COMMENT


async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    return await _save_and_next(update, context, update.message.text.strip())


async def _save_and_next(update: Update, context: ContextTypes.DEFAULT_TYPE, comment):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    db.save_entry(user_id, context.user_data['fill_date'], context.user_data['cur_cat'], context.user_data['cur_score'], comment)
    context.user_data['cat_idx'] += 1

    if context.user_data['cat_idx'] >= len(CATEGORIES):
        last_image = context.user_data.get('last_image')
        pool = [i for i in IMAGES if i != last_image] or IMAGES
        image_url = random.choice(pool)
        context.user_data['last_image'] = image_url

        # Show intermediate message while AI generates
        await context.bot.send_chat_action(chat_id=chat_id, action="typing")
        thinking_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="_Обдумываю это… ⏰_",
            parse_mode='Markdown'
        )

        # Get today's entries for daily summary
        fill_date = context.user_data['fill_date']
        raw_entries = db.get_entries_by_date(user_id, fill_date)
        today_entries = [(cat, score, comm) for cat, score, comm in raw_entries]
        daily_text = await get_daily_summary(today_entries)
        if daily_text:
            db.save_summary(user_id, fill_date, 'day', daily_text)
        else:
            daily_text = random.choice(QUOTES)

        try:
            await thinking_msg.delete()
        except Exception:
            pass

        if context.user_data.get('onboarding'):
            try:
                photo = _image_file_ids.get(image_url, image_url)
                msg = await context.bot.send_photo(chat_id=chat_id, photo=photo,
                    caption=f"✅ Первая запись сделана!\n\n{daily_text}")
                if image_url not in _image_file_ids:
                    _image_file_ids[image_url] = msg.photo[-1].file_id
            except Exception as e:
                logger.warning(f"Photo send failed: {e}")
                await context.bot.send_message(chat_id=chat_id, text=f"✅ Первая запись сделана!\n\n{daily_text}")
            await context.bot.send_message(
                chat_id=chat_id,
                text="В какое время каждый день мне присылать напоминание?\nНапиши в формате ЧЧ:ММ, например `21:00`",
                parse_mode='Markdown'
            )
            return SET_TIME
        try:
            photo = _image_file_ids.get(image_url, image_url)
            msg = await context.bot.send_photo(chat_id=chat_id, photo=photo, caption=daily_text)
            if image_url not in _image_file_ids:
                _image_file_ids[image_url] = msg.photo[-1].file_id
        except Exception as e:
            logger.error(f"Photo send failed with URL {image_url}: {type(e).__name__}: {e}")
            await context.bot.send_message(chat_id=chat_id, text=daily_text)

        streak = get_streak(user_id)
        if streak >= 2:
            def day_form(n):
                if n % 10 == 1 and n % 100 != 11: return "день"
                if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14: return "дня"
                return "дней"
            if streak == 7:
                milestone = " — неделя! 🎉"
            elif streak == 14:
                milestone = " — две недели! 🏆"
            elif streak == 30:
                milestone = " — месяц! 🌟"
            elif streak % 10 == 0:
                milestone = " — круглая цифра! ✨"
            else:
                milestone = ""
            streak_text = f"🔥 {streak} {day_form(streak)} подряд{milestone}"
        else:
            streak_text = ""
        done_text = f"✅  {streak_text}" if streak_text else "✅"
        await context.bot.send_message(chat_id=chat_id, text=done_text, reply_markup=main_menu_kb())
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
# Dynamics commands
# ──────────────────────────────────────────────


async def cmd_dynamics(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    msg = await update.message.reply_text("_Собираю динамику… 📈_", parse_mode='Markdown')
    header, keyboard = await build_dynamics(user_id, 7)
    await msg.delete()
    await update.message.reply_text(header, reply_markup=keyboard, parse_mode='Markdown')


async def handle_dynamics_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    days = int(query.data.split('_')[2])
    period = "месяц" if days == 30 else "неделю"
    chat_id = query.message.chat_id

    await query.message.edit_text(f"_Собираю данные за {period}… 📈_", parse_mode='Markdown')

    header, keyboard = await build_dynamics(query.from_user.id, days)

    try:
        await query.message.delete()
    except Exception:
        pass

    await context.bot.send_message(chat_id=chat_id, text=header, reply_markup=keyboard, parse_mode='Markdown')


async def handle_ai_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    days, mode = int(parts[2]), parts[3]
    loading = await query.message.reply_text("_Загружаю анализ… ⏰_", parse_mode='Markdown')
    ai_text = await get_ai_summary(query.from_user.id, days, mode)
    try:
        await loading.delete()
    except Exception:
        pass
    if ai_text and not ai_text.startswith('_Данных пока') and not ai_text.startswith('_Для анализа'):
        today = moscow_now().strftime('%Y-%m-%d')
        db.save_summary(query.from_user.id, today, mode, ai_text)
    if ai_text:
        await query.message.reply_text(ai_text, parse_mode='Markdown')
    else:
        await query.message.reply_text("_Не удалось загрузить анализ — попробуй чуть позже_", parse_mode='Markdown')


async def handle_dynamics_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    date_str, cat_idx = parts[1], int(parts[2])
    cat = CATEGORIES[cat_idx]
    by_date = entries_by_date(db.get_entries(query.from_user.id, 60))
    day_data = by_date.get(date_str, {}).get(cat)
    date_fmt = datetime.strptime(date_str, '%Y-%m-%d').strftime('%d %B')
    if day_data is None:
        await query.message.reply_text(f"{EMOJI[cat]} *{cat} · {date_fmt}*\n\n_Нет данных за этот день_", parse_mode='Markdown')
    else:
        score, comment = day_data
        comment_text = f"\n\n_{comment}_" if comment else ""
        await query.message.reply_text(f"{EMOJI[cat]} *{cat} · {date_fmt}*\n\n{score_color(score)} *{score}/10*{comment_text}", parse_mode='Markdown')


async def handle_week_tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split('_')
    week_start = datetime.strptime(parts[1], '%Y-%m-%d').date()
    cat = CATEGORIES[int(parts[2])]
    week_days = [week_start + timedelta(days=i) for i in range(7)]
    by_date = entries_by_date(db.get_entries(query.from_user.id, 60))
    lines = [f"{EMOJI[cat]} *{cat} · {week_start.strftime('%d.%m')}–{(week_start + timedelta(days=6)).strftime('%d.%m')}*\n"]
    for day in week_days:
        day_str = day.strftime('%Y-%m-%d')
        day_data = by_date.get(day_str, {}).get(cat)
        if day_data:
            score, comment = day_data
            comment_text = f" — _{comment}_" if comment else ""
            lines.append(f"{score_color(score)} *{day.strftime('%d.%m')}* {score}/10{comment_text}")
        else:
            lines.append(f"⬛ {day.strftime('%d.%m')} — нет данных")
    await query.message.reply_text("\n".join(lines), parse_mode='Markdown')


# ──────────────────────────────────────────────
# Menu buttons
# ──────────────────────────────────────────────

async def handle_menu_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "📈 Динамика":
        await cmd_dynamics(update, context)
    elif text == "🔔 Напоминание":
        await cmd_time(update, context)


# ──────────────────────────────────────────────
# Scheduler
# ──────────────────────────────────────────────

async def send_reminders(app: Application):
    current_time = moscow_now().strftime('%H:%M')
    for user_id, reminder_time in db.get_all_users():
        if reminder_time == current_time:
            try:
                streak = get_streak(user_id)
                streak_text = f"\n\n🔥 Ты заполняешь дневник уже *{streak} дней подряд*. Keep going!" if streak >= 2 else ""
                msg = random.choice(REMINDER_MESSAGES)
                await app.bot.send_message(
                    chat_id=user_id,
                    text=msg + streak_text,
                    parse_mode='Markdown',
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📝 Заполнить", callback_data='fill_now')]])
                )
            except Exception as e:
                logger.warning(f"Reminder failed for user {user_id}: {e}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def start_viewer():
    from viewer import app as flask_app
    port = int(os.environ.get('PORT', 5000))
    flask_app.run(host='0.0.0.0', port=port, use_reloader=False)


def main():
    db.init_db()

    viewer_thread = threading.Thread(target=start_viewer, daemon=True)
    viewer_thread.start()
    logger.info("🌐 Viewer started")

    app = Application.builder().token(TOKEN).build()

    time_conv = ConversationHandler(
        entry_points=[
            CommandHandler('time', cmd_time),
            MessageHandler(filters.Regex("^🔔 Напоминание$"), cmd_time),
        ],
        states={SET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_time)]},
        fallbacks=[],
        allow_reentry=True,
    )

    fill_conv = ConversationHandler(
        entry_points=[
            CommandHandler('start', cmd_start),
            CommandHandler('fill', begin_fill),
            CallbackQueryHandler(begin_fill, pattern='^fill_now$'),
            MessageHandler(filters.Regex("^📝 Заполнить$"), begin_fill),
        ],
        states={
            SCORE: [
                CallbackQueryHandler(handle_score, pattern=r'^s\d+$'),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_in_score),
            ],
            COMMENT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment)],
            SET_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_time)],
        },
        fallbacks=[CommandHandler('start', cmd_start)],
        allow_reentry=True,
    )

    app.add_handler(time_conv)
    app.add_handler(fill_conv)
    app.add_handler(CallbackQueryHandler(lambda u, c: u.callback_query.answer(), pattern='^noop$'))
    app.add_handler(CallbackQueryHandler(handle_dynamics_toggle, pattern=r'^dyn_toggle_'))
    app.add_handler(CallbackQueryHandler(handle_ai_request, pattern=r'^dyn_ai_'))
    app.add_handler(CallbackQueryHandler(handle_week_tap, pattern=r'^week_'))
    app.add_handler(CallbackQueryHandler(handle_dynamics_tap, pattern=r'^dyn_'))
    app.add_handler(CommandHandler('dynamics', cmd_dynamics))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_buttons))

    scheduler = AsyncIOScheduler(timezone='UTC')
    scheduler.add_job(send_reminders, 'cron', minute='*', args=[app])
    scheduler.start()

    logger.info("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
