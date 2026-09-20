import os
import asyncio
import logging
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.custom import Button

from llm import ask_llm
from drafts import add_draft
from db import get_db

ADMIN_CHAT_ID = int(os.getenv("ADMIN_CHAT_ID", "721042205"))
TG_API_ID = int(os.getenv("TG_API_ID", "0"))
TG_API_HASH = os.getenv("TG_API_HASH", "")
TG_STRING_SESSION = os.getenv("TG_STRING_SESSION", "")

CUPIDON_BOT_USERNAME = "AI_cupidon_bot"  # Юзернейм вашего бота Купидон

async def run_cupidon_live_test(client: TelegramClient) -> str:
    """Агент отправляет реальное сообщение боту Купидон и ждет живой ответ."""
    try:
        # Отправляем команду /start
        await client.send_message(CUPIDON_BOT_USERNAME, "/start")
        await asyncio.sleep(3)
        
        # Читаем последний ответ бота
        messages = await client.get_messages(CUPIDON_BOT_USERNAME, limit=1)
        if messages:
            reply_text = messages[0].text
            return f"✅ Ответ получен ({len(reply_text)} симв.): «{reply_text[:100]}...»"
        return "⚠️ Бот не ответил на /start за 3 секунды"
    except Exception as e:
        return f"❌ Ошибка отправки боту: {e}"

async def send_user_message(client: TelegramClient, target_user: str, text: str) -> bool:
    """Отправка сообщения пользователю по команде /say из пульта."""
    try:
        await client.send_message(target_user, text)
        return True
    except Exception as e:
        print(f"Ошибка /say: {e}")
        return False

async def handle_incoming_dialog(event, client: TelegramClient):
    """Обработка входящих сообщений от живых людей."""
    sender = await event.get_sender()
    sender_id = str(event.sender_id)
    text = event.raw_text.strip()
    
    # Игнорируем сообщения от самого себя и от пейджер-бота
    if event.is_channel or event.is_group or sender_id == str(ADMIN_CHAT_ID):
        return

    # Логируем в базу
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO dialogs (platform, user_id, user_name) VALUES ('tg', ?, ?)",
            (sender_id, getattr(sender, 'username', sender_id) or sender_id)
        )
        conn.commit()

    # Формируем умный ответ через ИИ
    system_prompt = (
        "Ты — дружелюбный ассистент проекта 'Купидон'. "
        "Отвечай вежливо, кратко, с легким юмором. "
        "Если тебя спрашивают, человек ли ты — честно скажи, что ты ИИ-помощник."
    )
    ai_reply, _ = ask_llm(f"Пользователь написал: '{text}'. Ответь ему.", system_prompt)
    
    # Отправляем ответ пользователю
    await event.reply(ai_reply)
    
    # Если вопрос важный или конфликтный — создаем черновик-уведомление для оператора
    if any(word in text.lower() for word in ["баг", "ошибка", "верни деньги", "жалоба", "человек", "админ"]):
        add_draft(
            draft_type="operator_escalation",
            target=f"TG: {sender_id}",
            payload=f"Пользователь {sender_id} написал: «{text}»|||Предложенный ответ ИИ: «{ai_reply}»"
        )
