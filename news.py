import os
import re
import sqlite3
import random
import logging
import datetime as dt
import yaml

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
1) Самой первой строкой ОБЯЗАТЕЛЬНО выведи короткий цепляющий заголовок до 60 знаков строго в формате:
[ХЕДЛАЙН: Текст заголовка с одним эмодзи]
2) Далее живой, полезный текст на 450–700 знаков. В теле поста хедлайн не повторяй.
3) Интерактивный вопрос к читателям в конце для вовлечения.
4) 3–4 хештега в конце: {BRAND_TAG} #знакомства #отношения #свидание.
5) Используй ТОЛЬКО HTML-теги: <b>жирный</b> и <i>курсив</i>.
КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО писать звездочки **1. Текст** или Markdown!
6) В самой последней строке добавь:
[КАРТИНКА: подробное описание сцены свидания, тёплый свет, кинематографично, без текста на изображении]
Выведи только готовый текст поста."""

HEAD_PATTERN = re.compile(r"\[ХЕДЛАЙН:\s*(.+?)\]", re.DOTALL | re.IGNORECASE)
IMG_PATTERN = re.compile(r"\[КАРТИНКА:\s*(.+?)\]", re.DOTALL | re.IGNORECASE)

def clean_html_formatting(text: str) -> str:
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
    prompt_v1 = f"Тема: {topic}. Фокус на психологии общения.\n\nНе повторяй прошлые посты:\n{recent_posts()}"
    prompt_v2 = f"Тема: {topic}. Фокус на конкретных практических советах.\n\nНе повторяй прошлые посты:\n{recent_posts()}"
    
    v1 = clean_html_formatting(ask(prompt_v1, system=STYLE, temperature=0.85))
    v2 = clean_html_formatting(ask(prompt_v2, system=STYLE, temperature=0.9))
    return v1, v2

def publish_approved_news(payload: str, variant_idx: int = 1):
    parts = payload.split("|||")
    channel_target = parts[0].strip() if len(parts) > 2 else "@qpd_n"
    variants = parts[1:] if len(parts) > 2 else parts
    
    idx = variant_idx - 1 if 0 <= variant_idx - 1 < len(variants) else 0
    raw_text = clean_html_formatting(variants[idx].strip())
    
    # 1. Извлекаем Хедлайн
    head_match = HEAD_PATTERN.search(raw_text)
    headline = head_match.group(1).strip() if head_match else ""
    text_without_head = HEAD_PATTERN.sub("", raw_text).strip()
    
    # 2. Извлекаем промпт картинки
    img_match = IMG_PATTERN.search(text_without_head)
    clean_body = IMG_PATTERN.sub("", text_without_head).strip()
    
    photo_bytes = None
    if img_match:
        img_prompt = img_match.group(1).strip()
        notify(f"🎨 <i>Генерирую авторскую иллюстрацию к посту...</i>\n«{img_prompt[:80]}...»", html=True)
        photo_bytes = generate_image(img_prompt)
    
    caption_text = f"<b>{headline}</b>" if headline else clean_body[:1024]
    
    # Публикация в Telegram (@qpd_n)
    tg_status = False
    try:
        if photo_bytes:
            tg_status = tg_post_photo(channel_target, caption_text, photo_bytes)
            # Текст поста отправляем следом за фото с хедлайном
            if headline:
                from publisher import post_to_telegram
                post_to_telegram(channel_target, clean_body)
        else:
            from publisher import post_to_telegram
            full_text = f"<b>{headline}</b>\n\n{clean_body}" if headline else clean_body
            tg_status = post_to_telegram(channel_target, full_text)[0]
    except Exception as e:
        log.error(f"Сбой публикации TG: {e}")

    # Публикация во ВКонтакте (-239533580)
    vk_status = False
    vk_body = f"{headline}\n\n{clean_body}" if headline else clean_body
    if os.getenv("VK_ENABLED", "false").lower() == "true":
        try:
            if photo_bytes:
                vk_status = vk_post_photo(-239533580, vk_body, photo_bytes)
            else:
                from publisher import post_to_vk
                vk_status = post_to_vk(-239533580, vk_body)[0]
        except Exception as e:
            log.error(f"Сбой публикации VK: {e}")

    c = db()
    c.execute("INSERT INTO published VALUES(?,?,datetime('now'))", (channel_target, clean_body))
    c.commit()
    c.close()
    
    img_note = " (с чистой иллюстрацией 🖼)" if photo_bytes else ""
    vk_note = " и vk.com/qp_on" if vk_status else " (ВК на паузе)"
    notify(f"✅ <b>Пост опубликован в {channel_target}{vk_note}{img_note}!</b>", html=True)
