import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import seaborn as sns
import pandas as pd
import numpy as np

import database as db

matplotlib.rcParams['font.family'] = 'DejaVu Sans'

CATEGORIES = ['Здоровье', 'Настроение', 'Физактивность', 'Еда', 'Сон']
EMOJI = {
    'Здоровье':     '❤️',
    'Настроение':   '😊',
    'Физактивность':'💪',
    'Еда':          '🍎',
    'Сон':          '😴',
}
COLORS = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12', '#9b59b6']


def _to_dataframe(entries):
    if not entries:
        return None
    df = pd.DataFrame(entries, columns=['date', 'category', 'score', 'comment'])
    df['date'] = pd.to_datetime(df['date'])
    return df


def generate_heatmap(user_id: int, days: int = 30) -> io.BytesIO | None:
    df = _to_dataframe(db.get_entries(user_id, days))
    if df is None:
        return None

    pivot = df.pivot_table(values='score', index='category', columns='date', aggfunc='mean')
    pivot = pivot.reindex([c for c in CATEGORIES if c in pivot.index])
    pivot.columns = [d.strftime('%d.%m') for d in pivot.columns]

    fig, ax = plt.subplots(figsize=(max(10, len(pivot.columns) * 0.75), 4))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')

    sns.heatmap(
        pivot,
        annot=True,
        fmt='.0f',
        cmap='RdYlGn',
        vmin=1, vmax=10,
        linewidths=0.4,
        linecolor='#2d2d4e',
        ax=ax,
        cbar_kws={'label': 'Оценка', 'shrink': 0.8},
        annot_kws={'size': 11, 'weight': 'bold'}
    )

    ax.set_title('Тепловая карта', fontsize=14, color='white', pad=12)
    ax.set_xlabel('')
    ax.set_ylabel('')
    ax.tick_params(colors='#cccccc', axis='both')
    ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha='right', fontsize=9, color='#cccccc')

    y_labels = [f"{EMOJI.get(l.get_text(), '')} {l.get_text()}" for l in ax.get_yticklabels()]
    ax.set_yticklabels(y_labels, rotation=0, color='#cccccc', fontsize=10)

    cbar = ax.collections[0].colorbar
    cbar.ax.yaxis.label.set_color('white')
    cbar.ax.tick_params(colors='white')

    plt.tight_layout()
    return _save_fig(fig)


def generate_trends(user_id: int, days: int = 14) -> io.BytesIO | None:
    df = _to_dataframe(db.get_entries(user_id, days))
    if df is None:
        return None

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#1a1a2e')

    for i, cat in enumerate(CATEGORIES):
        data = df[df['category'] == cat].sort_values('date')
        if data.empty:
            continue
        color = COLORS[i]
        ax.plot(data['date'], data['score'],
                marker='o', linewidth=2, markersize=7,
                label=f"{EMOJI.get(cat, '')} {cat}",
                color=color, zorder=3)
        ax.fill_between(data['date'], data['score'], alpha=0.08, color=color)

    ax.set_ylim(0.5, 10.5)
    ax.set_yticks(range(1, 11))
    ax.yaxis.label.set_color('#cccccc')
    ax.tick_params(colors='#cccccc')
    ax.set_title(f'Динамика за {days} дней', fontsize=14, color='white', pad=12)
    ax.set_ylabel('Оценка', color='#cccccc')
    ax.grid(True, alpha=0.15, color='white')
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%d.%m'))
    ax.xaxis.set_major_locator(mdates.DayLocator(interval=max(1, days // 10)))
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right', color='#cccccc')

    legend = ax.legend(
        loc='upper left', bbox_to_anchor=(0, -0.22),
        ncol=5, frameon=False, labelcolor='white', fontsize=10
    )

    for spine in ax.spines.values():
        spine.set_edgecolor('#444466')

    plt.tight_layout()
    return _save_fig(fig)


def get_weekly_summary(user_id: int) -> str | None:
    df = _to_dataframe(db.get_entries(user_id, 7))
    if df is None:
        return None

    summary = df.groupby('category')['score'].agg(['mean', 'min', 'max']).round(1)
    summary = summary.reindex([c for c in CATEGORIES if c in summary.index])

    lines = ['📊 *Итоги последних 7 дней*\n']
    for cat, row in summary.iterrows():
        emoji = EMOJI.get(cat, '')
        filled = int(round(row['mean']))
        bar = '█' * filled + '░' * (10 - filled)
        lines.append(f"{emoji} *{cat}*")
        lines.append(f"`{bar}` {row['mean']:.1f}/10")
        lines.append(f"min {int(row['min'])} · max {int(row['max'])}\n")

    return '\n'.join(lines)


def _save_fig(fig) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    buf.seek(0)
    plt.close(fig)
    return buf
