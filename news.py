import os
import re
import sqlite3
import random
import logging
import datetime as dt
import yaml
import requests

from llm import ask
from imagegen import generate_image
from publish_img import tg_post_photo, vk_post_photo
from notifier import notify

log = logging.getLogger("news")
BRAND_TAG = os.getenv("BRAND_HASHTAG", "#ИИКупидон")

TOPICS = [
    "3 правила успешного первого свидания",
    "Вопросы, после которых знакомство перестаёт быть неловким",
    "Как по переписке понять, что человек действительно заинтересован",
    "Необычные идеи для свиданий без больших затрат",
    "5 частых ошибок в анкете знакомств, которые отталкивают",
    "Как экологично отказать и не обидеть человека",
    "Главные темы и табу для первого созвона",
    "Знаки внимания в переписке, которые ценятся выше дежурных комплиментов",
    "Как преодолеть страх первого сообщения и начать диалог легко"
]

STYLE = f"""Ты — профессиональный SMM-редактор канала бота знакомств 'Купидон'. Формат поста:
1) Самой первой строкой выведи цепляющий заголовок до 60 знаков строго в формате:
[ХЕДЛАЙН: Текст заголовка с одним эмодзи]
2) Далее живой, увлекательный текст на 450–700 знаков.
3) Вопрос читателям в конце для обсуждения.
4) 3–4 хештега: {BRAND_TAG} #знакомства #отношения #свидание.
5) Используй ТОЛЬКО HTML: <b>жирный</b> и <i>курсив</i>. КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать звездочки **текст**!
6) Последней строкой:
[КАРТИНКА: подробное описание красивой романтичной сцены, тёплый свет, без текста на изображении]"""

HEAD_PATTERN = re.compile(r"\[ХЕДЛАЙН:\s*(.+?)\]", re.DOTALL | re.IGNORECASE)
IMG_PATTERN = re.compile(r"\[КАРТИНКА:\s*(.+?)\]", re.DOTALL | re.IGNORECASE)

def clean_html(text: str) -> str:
    if not text: return ""
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.*?)__', r'<i>\1</i>', text)
    text = re.sub(r'(?m)^\*\s+', '• ', text)
    return text.strip()

def db():
    c = sqlite3.connect("agent.db")
    c.execute("CREATE TABLE IF NOT EXISTS used_topics(topic TEXT, used_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS published(channel TEXT, text TEXT, ts TEXT)")
    return c

def recent_posts(n=3):
    c = db()
    rows = c.execute("SELECT text FROM published ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
    c.close()
    return "\n---\n".join(r[0][:250] for r in rows) or "(публикаций пока нет)"

def pick_fresh_topic():
    c = db()
    used = {r[0] for r in c.execute("SELECT topic FROM used_topics WHERE used_at > date('now','-20 day')")}
    fresh = [t for t in TOPICS if t not in used] or TOPICS
    topic = random.choice(fresh)
    c.execute("INSERT INTO used_topics VALUES(?, date('now'))", (topic,))
    c.commit()
    c.close()
    return topic

def generate_post_variants(topic: str):
    prompt_v1 = f"Тема: {topic}. Фокус на лёгкости и психологии общения.\n\nНе повторяй прошлые посты:\n{recent_posts()}"
    prompt_v2 = f"Тема: {topic}. Фокус на практических советах и лайфхаках.\n\nНе повторяй прошлые посты:\n{recent_posts()}"
    
    v1 = clean_html(ask(prompt_v1, system=STYLE, temperature=0.85))
    v2 = clean_html(ask(prompt_v2, system=STYLE, temperature=0.9))
    return v1, v2

def publish_approved_news(payload: str, variant_idx: int = 1) -> str:
    """Безотказная публикация: сначала пробуем с фото, если сбой фото — мгновенно шлем текстом."""
    parts = payload.split("|||")
    channel_target = parts[0].strip() if len(parts) > 2 else "@qpd_n"
    variants = parts[1:] if len(parts) > 2 else parts
    
    idx = variant_idx - 1 if 0 <= variant_idx - 1 < len(variants) else 0
    raw_text = clean_html(variants[idx].strip())
    
    head_match = HEAD_PATTERN.search(raw_text)
    headline = head_match.group(1).strip() if head_match else ""
    text_clean = HEAD_PATTERN.sub("", raw_text).strip()
    
    img_match = IMG_PATTERN.search(text_clean)
    body_clean = IMG_PATTERN.sub("", text_clean).strip()
    
    full_text = f"<b>{headline}</b>\n\n{body_clean}" if headline else body_clean

    photo_bytes = None
    if img_match:
        try:
            photo_bytes = generate_image(img_match.group(1).strip())
        except Exception as e:
            log.warning(f"Генерация фото не удалась: {e}")

    # 1. Публикация в Telegram (@qpd_n)
    tg_ok = False
    try:
        if photo_bytes:
            caption = f"<b>{headline}</b>" if headline else full_text[:1024]
            tg_ok = tg_post_photo(channel_target, caption, photo_bytes)
            if headline and tg_ok:
                from publisher import post_to_telegram
                post_to_telegram(channel_target, body_clean)
        
        # Если фото не вышло или вернуло False — гарантированно публикуем текст
        if not tg_ok:
            from publisher import post_to_telegram
            tg_ok, _ = post_to_telegram(channel_target, full_text)
    except Exception as e:
        log.error(f"Сбой публикации в TG: {e}")

    # 2. Публикация во ВКонтакте (если включен)
    vk_ok = False
    if os.getenv("VK_ENABLED", "false").lower() == "true":
        try:
            if photo_bytes:
                vk_ok = vk_post_photo(-239533580, full_text, photo_bytes)
            if not vk_ok:
                from publisher import post_to_vk
                vk_ok, _ = post_to_vk(-239533580, full_text)
        except Exception:
            pass

    # Запись в историю
    c = db()
    c.execute("INSERT INTO published VALUES(?,?,datetime('now'))", (channel_target, full_text[:500]))
    c.commit()
    c.close()

    res_tg = f"✅ TG: Опубликовано в {channel_target}" if tg_ok else f"❌ TG: Сбой отправки в {channel_target}"
    res_vk = f"\n✅ VK: Опубликовано в vk.com/qp_on" if vk_ok else ""
    return res_tg + res_vk
