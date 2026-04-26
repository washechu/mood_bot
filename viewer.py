import sqlite3
import os
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string

DB_PATH = os.environ.get('DB_PATH', 'mood_tracker.db')
VIEWER_PORT = int(os.environ.get('VIEWER_PORT', 5000))

app = Flask(__name__)

CATEGORIES = ['Здоровье', 'Настроение', 'Активность', 'Еда', 'Сон', 'Саморазвитие']
EMOJI = {
    'Здоровье': '💊',
    'Настроение': '😊',
    'Активность': '🏃',
    'Еда': '🍎',
    'Сон': '😴',
    'Саморазвитие': '📚',
}

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f5f7fa; color: #333; font-size: 14px; }
a { color: #4a6fa5; text-decoration: none; }
a:hover { text-decoration: underline; }
.container { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
h1 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
.subtitle { color: #777; font-size: 13px; margin-bottom: 24px; }
.card { background: #fff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.08);
        overflow: hidden; margin-bottom: 24px; }
.card-header { padding: 14px 20px; border-bottom: 1px solid #f0f0f0;
               font-weight: 600; font-size: 15px; display: flex;
               align-items: center; gap: 8px; }
table { width: 100%; border-collapse: collapse; }
th { background: #f8f9fb; text-align: left; padding: 10px 14px;
     font-size: 12px; text-transform: uppercase; letter-spacing: .5px;
     color: #888; border-bottom: 1px solid #eee; }
td { padding: 10px 14px; border-bottom: 1px solid #f5f5f5; vertical-align: top; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: #fafbfc; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 12px;
         font-size: 12px; font-weight: 600; }
.badge-score { min-width: 32px; text-align: center; }
.score-low  { background: #fde8e8; color: #c0392b; }
.score-mid  { background: #fef9e7; color: #b7950b; }
.score-high { background: #e8f8f0; color: #1e8449; }
.score-none { background: #eee; color: #999; }
.filters { display: flex; gap: 12px; align-items: flex-end; flex-wrap: wrap;
           padding: 16px 20px; background: #f8f9fb; border-bottom: 1px solid #eee; }
.filter-group { display: flex; flex-direction: column; gap: 4px; }
.filter-group label { font-size: 12px; color: #777; font-weight: 500; }
.filter-group input, .filter-group select {
    border: 1px solid #ddd; border-radius: 6px; padding: 6px 10px;
    font-size: 13px; background: #fff; }
.btn { padding: 7px 16px; border-radius: 6px; border: none; cursor: pointer;
       font-size: 13px; font-weight: 500; }
.btn-primary { background: #4a6fa5; color: #fff; }
.btn-primary:hover { background: #3a5f95; }
.avgs-row { display: flex; gap: 12px; flex-wrap: wrap; padding: 16px 20px; }
.avg-chip { display: flex; align-items: center; gap: 6px; padding: 6px 12px;
            border-radius: 8px; background: #f0f4fb; font-size: 13px; }
.avg-chip .val { font-weight: 700; }
.back { display: inline-flex; align-items: center; gap: 4px; margin-bottom: 16px;
        font-size: 13px; color: #777; }
.comment { color: #555; font-style: italic; max-width: 300px; }
.empty { padding: 40px; text-align: center; color: #aaa; }
"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mood Bot — Просмотр данных</title>
<style>{{ css }}</style></head>
<body>
<div class="container">
  <h1>📊 Mood Bot — Данные пользователей</h1>
  <p class="subtitle">База данных: {{ db_path }} &nbsp;·&nbsp; Пользователей: {{ users|length }}</p>
  <div class="card">
    <div class="card-header">👥 Пользователи</div>
    {% if users %}
    <table>
      <thead>
        <tr>
          <th>Пользователь</th>
          <th>ID</th>
          <th>Напоминание</th>
          <th>Записей</th>
          <th>Последняя запись</th>
          <th>Зарегистрирован</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for u in users %}
        <tr>
          <td>
            <strong>{{ u['first_name'] or '—' }}</strong>
            {% if u['username'] %}<br><span style="color:#999;font-size:12px">@{{ u['username'] }}</span>{% endif %}
          </td>
          <td style="color:#999">{{ u['user_id'] }}</td>
          <td>{{ u['reminder_time'] }}</td>
          <td><span class="badge" style="background:#e8f0fe;color:#3c4dc0">{{ u['entry_count'] }}</span></td>
          <td>{{ u['last_entry'] or '—' }}</td>
          <td style="color:#999;font-size:12px">{{ (u['created_at'] or '')[:10] }}</td>
          <td><a href="/user/{{ u['user_id'] }}">Открыть →</a></td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty">Нет пользователей в базе данных</div>
    {% endif %}
  </div>
</div>
</body></html>"""

USER_TEMPLATE = """<!DOCTYPE html>
<html lang="ru">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{ user['first_name'] or user['user_id'] }} — Mood Bot</title>
<style>{{ css }}</style></head>
<body>
<div class="container">
  <a class="back" href="/">← Все пользователи</a>
  <h1>{{ user['first_name'] or '—' }}
    {% if user['username'] %}<span style="font-weight:400;color:#999;font-size:16px"> @{{ user['username'] }}</span>{% endif %}
  </h1>
  <p class="subtitle">ID: {{ user['user_id'] }} &nbsp;·&nbsp; Напоминание: {{ user['reminder_time'] }}</p>

  <div class="card">
    <div class="card-header">📈 Средние значения (за период)</div>
    <div class="avgs-row">
      {% for cat in categories %}
      {% set val = avgs[cat] %}
      <div class="avg-chip">
        <span>{{ emoji[cat] }} {{ cat }}</span>
        <span class="val {% if val is none %}score-none{% elif val <= 5 %}score-low{% elif val <= 7 %}score-mid{% else %}score-high{% endif %} badge badge-score">
          {{ val if val is not none else '—' }}
        </span>
      </div>
      {% endfor %}
    </div>
  </div>

  <div class="card">
    <div class="card-header">🔍 Фильтры</div>
    <form method="get" class="filters">
      <div class="filter-group">
        <label>С даты</label>
        <input type="date" name="date_from" value="{{ date_from }}">
      </div>
      <div class="filter-group">
        <label>По дату</label>
        <input type="date" name="date_to" value="{{ date_to }}">
      </div>
      <div class="filter-group">
        <label>Категория</label>
        <select name="category">
          <option value="">Все категории</option>
          {% for cat in categories %}
          <option value="{{ cat }}" {% if selected_category == cat %}selected{% endif %}>
            {{ emoji[cat] }} {{ cat }}
          </option>
          {% endfor %}
        </select>
      </div>
      <button class="btn btn-primary" type="submit">Применить</button>
    </form>
  </div>

  <div class="card">
    <div class="card-header">📝 Ответы ({{ entries|length }})</div>
    {% if entries %}
    <table>
      <thead>
        <tr>
          <th>Дата</th>
          <th>Категория</th>
          <th>Оценка</th>
          <th>Комментарий</th>
          <th>Создано</th>
        </tr>
      </thead>
      <tbody>
        {% for e in entries %}
        <tr>
          <td>{{ e['date'] }}</td>
          <td>{{ emoji.get(e['category'], '') }} {{ e['category'] }}</td>
          <td>
            <span class="badge badge-score
              {% if e['score'] <= 5 %}score-low{% elif e['score'] <= 7 %}score-mid{% else %}score-high{% endif %}">
              {{ e['score'] }}
            </span>
          </td>
          <td class="comment">{{ e['comment'] or '' }}</td>
          <td style="color:#999;font-size:12px">{{ (e['created_at'] or '')[:16] }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <div class="empty">Нет записей за выбранный период</div>
    {% endif %}
  </div>
</div>
</body></html>"""


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.route('/')
def index():
    conn = get_db()
    users = conn.execute('''
        SELECT u.user_id, u.username, u.first_name, u.reminder_time, u.created_at,
               COUNT(e.id) AS entry_count,
               MAX(e.date) AS last_entry
        FROM users u
        LEFT JOIN entries e ON u.user_id = e.user_id
        GROUP BY u.user_id
        ORDER BY last_entry DESC
    ''').fetchall()
    conn.close()
    return render_template_string(INDEX_TEMPLATE, users=users, css=CSS, db_path=DB_PATH)


@app.route('/user/<int:user_id>')
def user_view(user_id):
    date_from = request.args.get('date_from', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    date_to = request.args.get('date_to', datetime.now().strftime('%Y-%m-%d'))
    selected_category = request.args.get('category', '')

    conn = get_db()
    user = conn.execute('SELECT * FROM users WHERE user_id = ?', (user_id,)).fetchone()

    query = '''
        SELECT date, category, score, comment, created_at FROM entries
        WHERE user_id = ? AND date >= ? AND date <= ?
    '''
    params = [user_id, date_from, date_to]
    if selected_category:
        query += ' AND category = ?'
        params.append(selected_category)
    query += ' ORDER BY date DESC, category'
    entries = conn.execute(query, params).fetchall()

    avgs = {}
    for cat in CATEGORIES:
        row = conn.execute('''
            SELECT AVG(score) FROM entries
            WHERE user_id = ? AND date >= ? AND date <= ? AND category = ?
        ''', (user_id, date_from, date_to, cat)).fetchone()
        avgs[cat] = round(row[0], 1) if row[0] is not None else None

    conn.close()
    return render_template_string(
        USER_TEMPLATE,
        user=user, entries=entries, avgs=avgs,
        categories=CATEGORIES, emoji=EMOJI,
        date_from=date_from, date_to=date_to,
        selected_category=selected_category,
        css=CSS,
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=VIEWER_PORT, debug=False)
