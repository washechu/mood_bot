# Mood Tracker Bot

Telegram-бот для ежедневного отслеживания самочувствия по 6 категориям:
💊 Здоровье · 😊 Настроение · 🏃 Активность · 🍎 Еда · 😴 Сон · 📚 Саморазвитие

---

## Быстрый старт

### Шаг 1 — Создать бота в Telegram

1. Открой [@BotFather](https://t.me/BotFather)
2. Напиши `/newbot`, придумай имя и username
3. Скопируй токен

### Шаг 2 — Задеплоить на Railway

1. Зарегистрируйся на [railway.app](https://railway.app)
2. **New Project → Deploy from GitHub repo** → выбери этот репозиторий
3. Добавь Volume, mount path: `/data`
4. В **Variables** добавь:
   ```
   BOT_TOKEN=<токен от BotFather>
   ROUTER_AI_KEY=<ключ RouterAI>
   DB_PATH=/data/mood_tracker.db
   ```
5. Railway задеплоит бота — через ~1 минуту он живой

### Шаг 3 — Запустить

Открой бота в Telegram, напиши `/start`.

---

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Первый запуск |
| `/fill` | Заполнить дневник прямо сейчас |
| `/time` | Изменить время напоминания |

Также доступны кнопки меню: **📝 Заполнить**, **📈 Динамика**, **🔔 Напоминание**.

---

## Локальный запуск

```bash
pip install -r requirements.txt
export BOT_TOKEN="твой_токен"
export ROUTER_AI_KEY="твой_ключ"
python bot.py
```

---

## Структура

```
bot.py          — бот + Flask viewer (запускается в одном процессе)
database.py     — работа с SQLite
viewer.py       — веб-интерфейс для просмотра данных
requirements.txt
Procfile        — для Railway
```

Данные хранятся в `mood_tracker.db` (SQLite). На Railway подключи Volume с mount path `/data` и задай `DB_PATH=/data/mood_tracker.db`.
