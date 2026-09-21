async def main():
    print("🚀 [ИИ-Агент] Инициализация базы данных и запуск цикла...")
    init_db()
    
    try:
        # 1. Ротация тем и генерация свежего черновика поста (если очередь пуста)
        if not get_pending_drafts():
            from news import pick_fresh_topic, generate_post_variants
            topic = pick_fresh_topic()
            v1, v2 = generate_post_variants(topic)
            add_draft(
                draft_type="post",
                target="@qpd_n",
                payload=f"@qpd_n|||{v1}|||{v2}"
            )

        # 2. Чтение команд и кликов по кнопкам
        process_pager_updates()
        
        # 3. Антисон спейсов
        servers_status = run_keepalive_check()
        
        # 4. Живой тест TG Userbot
        tg_status, live_cupid_test = await test_telegram_userbot()
        
        # 5. Проверка VK через vkrate
        vk_status = test_vk_userbot()
        
        # 6. Тест ИИ-мозга
        ai_status = test_ai_qa_reasoning()

        # 7. Автомодерация спама
        mod_results = run_moderation_check()

        report = (
            "🤖 <b>[ОТЧЕТ АВТОНОМНОГО ИИ-АГЕНТА КУПИДОН]</b>\n\n"
            "📡 <b>1. Антисон & Серверы:</b>\n" + "\n".join(servers_status) + "\n\n"
            f"📱 <b>2. Telegram Userbot:</b> {tg_status}\n"
            f"💬 <b>Живой тест @AI_cupidon_bot:</b> {live_cupid_test}\n\n"
            f"🌐 <b>3. ВКонтакте Userbot:</b> {vk_status}\n\n"
            f"🧠 <b>4. ИИ-Мозг (QA-Тест):</b>\n{ai_status}\n\n"
            f"🛡 <b>5. Модерация спама:</b>\n" + "\n".join(mod_results) + "\n\n"
            "💡 <i>Команды: /queue (кнопки), /testimg (тест фото), /models, /doctor, /errors</i>"
        )

        send_telegram_report(report)
        print("✅ [ИИ-Агент] Цикл успешно завершён!")
    except Exception as e:
        tb = traceback.format_exc()
        print(f"💥 Сбой цикла: {e}")
        notify(f"💥 <b>ОШИБКА ЦИКЛА:</b>\n<pre>{tb[-2500:]}</pre>", html=True)

if __name__ == "__main__":
    asyncio.run(main())
