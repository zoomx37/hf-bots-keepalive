elif data == "run_filter_search":
                    s = SEARCH_FILTERS
                    send_msg(f"🔎 <i>Ищу анкеты: {s['city']}, {s['sex'].upper()}, {s['age']} лет, вайб '{s['vibe']}'...</i>")
                    try:
                        from social import search_vk_candidates
                        ages = s["age"].split("-")
                        a_from = int(ages[0])
                        a_to = int(ages[1]) if len(ages) > 1 else int(ages[0]) + 3
                        users = search_vk_candidates(s["city"], a_from, a_to, s["sex"], s["vibe"])
                        if not users:
                            send_msg(f"📭 В г. {s['city']} свободных анкет с открытой личкой по этим параметрам не найдено.\nПопробуйте расширить возраст!")
                        else:
                            out = [f"👥 <b>[КАНДИДАТЫ ВК: {s['city']} | {s['age']} лет | {s['vibe'].title()}]</b>\n"]
                            for idx, u in enumerate(users, 1):
                                name = f"{u.get('first_name')} {u.get('last_name')}"
                                uid = u.get("id")
                                about = u.get("interests") or u.get("activities") or u.get("about") or u.get("status") or "анкета без подробного текста"
                                match_tag = " 🧘 <b>(Вайб совпал!)</b>" if u.get("_matched_vibe") else ""
                                out.append(f"<b>{idx}. {name}</b> (id{uid}){match_tag}\n<i>Интересы: {about[:90]}...</i>\n💍 Статус: свободна / в поиске\n👉 Взять: <code>/pick {uid} Начать легкий флирт</code>\n")
                            send_msg("\n".join(out))
                    except Exception as e:
                        send_msg(f"❌ Ошибка ВК: {e}")
