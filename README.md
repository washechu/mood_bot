# 🌙 Mood Tracker Bot

Телеграм-бот для ежедневного отслеживания самочувствия по 5 категориям:
❤️ Здоровье · 😊 Настроение · 💪 Физактивность · 🍎 Еда · 😴 Сон

---

## Быстрый старт

### Шаг 1 — Создать бота в Telegram

1. Открой [@BotFather](https://t.me/BotFather) в Telegram
2. Напиши `/newbot`
3. Придумай имя и username (например `GalyaMoodBot`)
4. Скопируй **токен** — он выглядит как `123456789:ABC-DEF...`

### Шаг 2 — Задеплоить на Railway (бесплатно)

1. Зарегистрируйся на [railway.app](https://railway.app) (можно через GitHub)
2. Нажми **New Project → Deploy from GitHub repo**
3. Загрузи эти файлы в GitHub-репозиторий (или используй Railway CLI)
4. В Railway зайди в **Variables** и добавь:
   ```
   BOT_TOKEN = <твой токен от BotFather>
   ```
5. Railway сам задеплоит бота — через ~1 минуту он будет живой

> **Альтернатива без GitHub:** Railway CLI
> ```bash
> npm install -g @railway/cli
> railway login
> railway init
> railway up
> ```

### Шаг 3 — Запустить бота

Открой своего бота в Telegram, напиши `/start` — он спросит время напоминания и всё готово!

---

## Команды

| Команда     | Описание                              |
|-------------|---------------------------------------|
| `/start`    | Первый запуск, установить время       |
| `/fill`     | Заполнить дневник прямо сейчас        |
| `/stats`    | Текстовые итоги за последние 7 дней   |
| `/heatmap`  | Тепловая карта за 30 дней (картинка)  |
| `/trends`   | График динамики за 14 дней (картинка) |
| `/time`     | Изменить время напоминания            |

---

## Локальный запуск (для разработки)

```bash
pip install -r requirements.txt
export BOT_TOKEN="твой_токен"
python bot.py
```

---

## Структура проекта

```
bot.py          — основная логика бота
database.py     — работа с SQLite
analytics.py    — графики и статистика
requirements.txt
Procfile        — для Railway
```

Данные хранятся в `mood_tracker.db` (SQLite). На Railway файловая система эфемерна — если нужно постоянное хранение, подключи Railway PostgreSQL или смонтируй Volume.

---

## Добавить Volume на Railway (чтобы данные не терялись при перезапуске)

1. В Railway → твой сервис → **Volumes** → **Add Volume**
2. Mount path: `/data`
3. В переменных добавь: `DB_PATH=/data/mood_tracker.db`
