import os
import re
import sqlite3
import logging
import requests
import xml.etree.ElementTree as ET
from llm import ask
from notifier import notify

log = logging.getLogger("trends")

NICHES = ["знакомств", "отношени", "свидани", "влюб", "флирт", "пара", "измен", "разрыв",
          "краш", "тиндер", "психолог", "дейтинг", "любовь", "свадьб", "секс"]

RSS_SOURCES = [
    "https://news.google.com/rss/search?q=знакомства+отношения+свидания&hl=ru&gl=RU&ceid=RU:ru",
    "https://lenta.ru/rss/news",
    "https://life.ru/rss/life.xml"
]

def db():
    c = sqlite3.connect("agent.db")
    c.execute("""CREATE TABLE IF NOT EXISTS trends(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT,
        url TEXT UNIQUE,
        title TEXT,
        text TEXT,
        heat REAL,
        ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        status TEXT DEFAULT 'new'
    )""")
    return c

def add_trend(source: str, url: str, title: str, text: str = "", engagement: int = 0):
    if not title: return
    c = db()
    try:
        t = (title + " " + text).lower()
        heat = sum(2.5 for k in NICHES if k in t) + min(engagement / 500, 5) + 1.0
        c.execute(
            "INSERT OR IGNORE INTO trends (source, url, title, text, heat, status) VALUES (?, ?, ?, ?, ?, 'new')",
            (source, url or "", title[:250], text[:1200], heat)
        )
        c.commit()
    except Exception as e:
        log.warning(f"Ошибка тренда: {e}")
    finally:
        c.close()

def fetch_rss_trends():
    """Сбор трендов через встроенный XML-парсер без внешних библиотек."""
    for feed_url in RSS_SOURCES:
        try:
            r = requests.get(feed_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            if r.status_code != 200: continue
            root = ET.fromstring(r.content)
            for item in root.iter("item"):
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                desc = item.findtext("description") or ""
                desc_clean = re.sub(r'<[^>]+>', '', desc)
                add_trend("news", link, title, desc_clean)
        except Exception as e:
            log.warning(f"Сбой сбора RSS ({feed_url[:30]}): {e}")

def get_hot_trends(limit: int = 5) -> list:
    c = db()
    rows = c.execute(
        "SELECT id, source, title, heat, url FROM trends WHERE status='new' ORDER BY heat DESC LIMIT ?",
        (limit,)
    ).fetchall()
    c.close()
    return rows

def pitch_trend_to_post(trend_id: int) -> tuple[str, str]:
    c = db()
    row = c.execute("SELECT title, text FROM trends WHERE id=?", (trend_id,)).fetchone()
    if not row:
        c.close()
        return None, None
    c.execute("UPDATE trends SET status='pitched' WHERE id=?", (trend_id,))
    c.commit()
    c.close()

    news_title, news_text = row[0], row[1]
    prompt_base = f"Горячий тренд: «{news_title}». Суть: {news_text[:400]}.\n" \
                  f"Напиши вирусный пост для дейтинг-канала в стиле 'НА ПРИКОЛЕ' с зумерским сленгом, " \
                  f"обстеби ситуацию, дай жизненный вывод и свяжи с отношениями."
    
    from news import STYLE, clean_html
    v1 = clean_html(ask(prompt_base + " Сделай упор на иронию и мемы.", system=STYLE, temperature=0.92))
    v2 = clean_html(ask(prompt_base + " Сделай упор на практический лайфхак.", system=STYLE, temperature=0.94))
    return v1, v2
