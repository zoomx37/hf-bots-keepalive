import os
import re
import sqlite3
import random
import logging
import datetime as dt

from llm import ask
from imagegen import generate_image
from publish_img import tg_post_photo, vk_post_photo
from notifier import notify

log = logging.getLogger("news")
BRAND_TAG = "#ИИКупидон"

# Темы строго на зумерско-миллениальском вайбе
TOPICS = [
    "Как не стать тюбиком на первом свидании: инструкция для нормальных чечиков",
    "Твой краш оказался душнилой: как экологично слиться и не словить тильт",
    "Бежевые флаги в дейтинге: когда вроде не кринж, но осадочек странный",
    "Свидание в шаурмичной или кофейне: кринж или лютая база?",
    "Почему он прочитал и молчит: разбираем дейтинг-загоны без драмы",
    "Анкета без кринжа: как упаковать свой профиль, чтобы тебе писали первыми",
    "Ситуатионшип вместо отношений: как вылезти из этой ловушки без слез",
    "Ред флаги в переписке, которые кричат 'беги', а ты думаешь 'ну он милый'",
    "Как прокачать свой Rizz и не выглядеть так, будто ты гуглил пикап-фразы 2007 года"
]

STYLE = f"""Ты — дерзкий, остроумный SMM-редактор канала знакомств 'ИИ-Купидон'.
ТВОЙ ЯЗЫК: зумерско-миллениальский сленг, НА ПРИКОЛЕ, с самоиронией, мемами и лёгким сарказмом!
Используй современные словечки: краш, ризз (rizz), вайб, тюбик, масик, чечик, ред-флаги, кринж, база, тильт, душнила, рофл — но органично и к месту! Никакого нафталина, душноты и скуки.

Формат генерации:
1) Первая строка строго:
[ХЕДЛАЙН: Короткий хайповый заголовок с эмодзи до 60 знаков]
2) Текст поста на 400–650 знаков: жизненная ситуация, смешной разбор и годный лайфхак.
3) Забавный вопрос в конце в стиле: 'А вы с какими тюбиками сталкивались? Го в комменты 👇'.
4) Хештеги: {BRAND_TAG} #дейтинг #флирт #отношения #вайб #краш.
5) Используй ТОЛЬКО HTML: <b>жирный</b> и <i>курсив</i>. Звёздочки ** строго запрещены!
6) Последняя строка строго:
[КАРТИНКА: неоновый арт или стильный интерьер кофейни/вечернего города без людей, теплый кино-свет, без текста]"""

# Обязательный призыв к действию с ботом и байтом на подарки
FOOTER_TG = (
    "\n\n━━━━━━━━━━━━━━━━━━━━\n"
    "🚀 <b>Качай свой Rizz в боте:</b> @AI_cupidon_bot\n"
    "🔒 <i>Доступ открыт строго для подписчиков нашего ТГ-канала и паблика ВК!</i>\n\n"
    "🎁 <b>Есть Telegram Premium?</b> Закиньте буст или подарок нашему каналу — покажите свой люкс-вайб, не будьте скуфами! 💎✨"
)

FOOTER_VK = (
    "\n\n━━━━━━━━━━━━━━━━━━━━\n"
    "🚀 Качай свой Rizz в боте: t.me/AI_cupidon_bot\n"
    "🔒 Доступ открыт строго для подписчиков нашего паблика ВК и ТГ-канала t.me/qpd_n!\n\n"
    "🎁 Премиальные котики — закидывайте реакции и донаты сообществу, покажите свой уровень щедрости! 💎✨"
)

HEAD_PATTERN = re.compile(r"\[ХЕДЛАЙН:\s*(.+?)\]", re.DOTALL | re.IGNORECASE)
IMG_PATTERN = re.compile(r"\[КАРТИНКА:\s*(.+?)\]", re.DOTALL | re.IGNORECASE)

def clean_html(text: str) -> str:
    if not text: return ""
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.*?)__', r'<i>\1</i>', text)
    text = re.sub(r'(?m)^\*\s+', '• ', text)
    return text.strip()

def clean_for_vk(text: str) -> str:
    if not text: return ""
    return re.sub(r'<[^>]+>', '', text).strip()

def db():
    c = sqlite3.connect("agent.db")
    c.execute("CREATE TABLE IF NOT EXISTS used_topics(topic TEXT, used_at TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS published(channel TEXT, text TEXT, ts TEXT)")
    return c

def recent_posts(n=3):
    c = db()
    rows = c.execute("SELECT text FROM published ORDER BY ts DESC LIMIT ?", (n,)).fetchall()
    c.close()
    return "\n---\n".join(r[0][:200] for r in rows) or "(нет прошлых постов)"

def pick_fresh_topic():
    c = db()
    used = {r[0] for r in c.execute("SELECT topic FROM used_topics WHERE used_at > date('now','-15 day')")}
    fresh = [t for t in TOPICS if t not in used] or TOPICS
    topic = random.choice(fresh)
    c.execute("INSERT INTO used_topics VALUES(?, date('now'))", (topic,))
    c.commit(); c.close()
    return topic

def generate_post_variants(topic: str):
    prompt_v1 = f"Тема: {topic}. Сделай упор на зумерский юмор, самоиронию и мемы.\n\nНе повторяй старое:\n{recent_posts()}"
    prompt_v2 = f"Тема: {topic}. Сделай упор на практический лайфхак и психологию чечиков.\n\nНе повторяй старое:\n{recent_posts()}"
    
    v1 = clean_html(ask(prompt_v1, system=STYLE, temperature=0.92))
    v2 = clean_html(ask(prompt_v2, system=STYLE, temperature=0.95))
    return v1, v2

def publish_approved_news(payload: str, variant_idx: int = 1) -> str:
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
    
    # Добавляем обязательный брендовый хвост со ссылкой на бота и подарки
    full_tg_text = (f"<b>{headline}</b>\n\n{body_clean}" if headline else body_clean) + FOOTER_TG
    full_vk_text = clean_for_vk((f"{headline}\n\n{body_clean}" if headline else body_clean) + FOOTER_VK)

    photo_bytes = None
    if img_match:
        try:
            photo_bytes = generate_image(img_match.group(1).strip())
        except Exception as e:
            log.warning(f"Ошибка фото: {e}")

    # 1. Публикация в Telegram (@qpd_n)
    tg_ok = False
    try:
        if photo_bytes:
            caption = f"<b>{headline}</b>" if headline else full_tg_text[:1024]
            tg_ok = tg_post_photo(channel_target, caption, photo_bytes)
            # Если был хедлайн — сам текст со ссылкой и подарками отправляем следом
            from publisher import post_to_telegram
            post_to_telegram(channel_target, body_clean + FOOTER_TG)
        else:
            from publisher import post_to_telegram
            tg_ok, _ = post_to_telegram(channel_target, full_tg_text)
    except Exception as e:
        log.error(f"Сбой публикации в TG: {e}")

    # 2. Публикация во ВКонтакте (без HTML-тегов)
    vk_ok = False
    if os.getenv("VK_ENABLED", "false").lower() == "true":
        try:
            if photo_bytes:
                vk_ok = vk_post_photo(-239533580, full_vk_text, photo_bytes)
            else:
                from publisher import post_to_vk
                vk_ok, _ = post_to_vk(-239533580, full_vk_text)
        except Exception as e:
            log.error(f"Сбой публикации в VK: {e}")

    c = db()
    c.execute("INSERT INTO published VALUES(?,?,datetime('now'))", (channel_target, full_tg_text[:400]))
    c.commit(); c.close()

    res_tg = f"✅ TG: Опубликовано в {channel_target}" if tg_ok else f"❌ TG: Сбой отправки"
    res_vk = f"\n✅ VK: Опубликовано в vk.com/qp_on" if vk_ok else ""
    return res_tg + res_vk
