from datetime import datetime, timedelta
import database as db

CATEGORIES = ['Здоровье', 'Настроение', 'Активность', 'Еда', 'Сон']
EMOJI = {
    'Здоровье':   '💊',
    'Настроение': '😊',
    'Активность': '🏃',
    'Еда':        '🍎',
    'Сон':        '😴',
}


def score_square(score) -> str:
    if score is None:
        return "⬛"
    score = float(score)
    if score <= 5:
        return "⬜"
    elif score <= 7:
        return "🟨"
    else:
        return "🟩"


def _entries_by_date(entries):
    by_date = {}
    for date, category, score, comment in entries:
        by_date.setdefault(str(date)[:10], {})[category] = score
    return by_date


def get_text_week_stats(user_id: int) -> str | None:
    entries = db.get_entries(user_id, 7)
    if not entries:
        return None

    today = datetime.now().date()
    days = [(today - timedelta(days=i)) for i in range(6, -1, -1)]
    by_date = _entries_by_date(entries)

    week_start = days[0].strftime('%d.%m')
    week_end = days[-1].strftime('%d.%m')
    lines = [f"📊 *Итоги недели* ({week_start} — {week_end})\n"]

    day_labels = "".join([d.strftime('%d')[1] if d.strftime('%d')[0] == '0' else d.strftime('%d') + " " for d in days])

    for cat in CATEGORIES:
        emoji = EMOJI.get(cat, '')
        squares = []
        scores = []
        for day in days:
            day_str = day.strftime('%Y-%m-%d')
            score = by_date.get(day_str, {}).get(cat)
            squares.append(score_square(score))
            if score is not None:
                scores.append(score)

        avg = sum(scores) / len(scores) if scores else None
        bar = "".join(squares)
        avg_str = f"  _{avg:.1f}_" if avg is not None else ""
        lines.append(f"{emoji} *{cat}*\n{bar}{avg_str}")

    lines.append(f"\n⬜ 1–5  🟨 6–7  🟩 8–10  ⬛ нет данных")
    return "\n".join(lines)


def get_text_month_stats(user_id: int) -> str | None:
    entries = db.get_entries(user_id, 30)
    if not entries:
        return None

    today = datetime.now().date()
    days = [(today - timedelta(days=i)) for i in range(29, -1, -1)]
    by_date = _entries_by_date(entries)

    lines = [f"📅 *Итоги месяца* (последние 30 дней)\n"]

    for cat in CATEGORIES:
        emoji = EMOJI.get(cat, '')
        squares = []
        scores = []
        for day in days:
            day_str = day.strftime('%Y-%m-%d')
            score = by_date.get(day_str, {}).get(cat)
            squares.append(score_square(score))
            if score is not None:
                scores.append(score)

        avg = sum(scores) / len(scores) if scores else None
        bar = "".join(squares)
        avg_str = f"  _{avg:.1f}_" if avg is not None else ""
        lines.append(f"{emoji} *{cat}*\n{bar}{avg_str}")

    lines.append(f"\n⬜ 1–5  🟨 6–7  🟩 8–10  ⬛ нет данных")
    return "\n".join(lines)


def get_text_trends(user_id: int) -> str | None:
    entries = db.get_entries(user_id, 14)
    if not entries:
        return None

    today = datetime.now().date()
    days = [(today - timedelta(days=i)) for i in range(13, -1, -1)]
    by_date = _entries_by_date(entries)

    lines = [f"📈 *Динамика за 14 дней*\n"]

    for cat in CATEGORIES:
        emoji = EMOJI.get(cat, '')
        scores_with_days = []
        squares = []
        for day in days:
            day_str = day.strftime('%Y-%m-%d')
            score = by_date.get(day_str, {}).get(cat)
            squares.append(score_square(score))
            if score is not None:
                scores_with_days.append((day, score))

        bar = "".join(squares)

        # Simple trend arrow
        trend = ""
        if len(scores_with_days) >= 4:
            first_half = [s for _, s in scores_with_days[:len(scores_with_days)//2]]
            second_half = [s for _, s in scores_with_days[len(scores_with_days)//2:]]
            avg_first = sum(first_half) / len(first_half)
            avg_second = sum(second_half) / len(second_half)
            diff = avg_second - avg_first
            if diff > 0.5:
                trend = " 📈"
            elif diff < -0.5:
                trend = " 📉"
            else:
                trend = " ➡️"

        lines.append(f"{emoji} *{cat}*{trend}\n{bar}")

    lines.append(f"\n⬜ 1–5  🟨 6–7  🟩 8–10  ⬛ нет данных")
    lines.append("_Первый день слева, сегодня справа_")
    return "\n".join(lines)
