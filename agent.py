def run_keepalive_check() -> list[str]:
    hf_token = os.getenv("HF_TOKEN")
    hf_api = HfApi(token=hf_token) if hf_token else None
    results = []

    for space in SPACES:
        is_ok = False
        stage_info = "RUNNING"

        # Официальный опрос через API (работает даже для Private спейсов без 404!)
        if hf_api:
            try:
                runtime = hf_api.get_space_runtime(repo_id=space)
                stage_info = runtime.stage
                if stage_info in ["RUNNING", "APP_STARTING"]:
                    is_ok = True
                elif stage_info in ["SLEEPING", "PAUSED"]:
                    hf_api.restart_space(repo_id=space)
                    results.append(f"• <b>{space}</b>: 🚨 Спал ({stage_info}) ➔ Разбужен")
                    continue
            except Exception:
                pass

        if not is_ok:
            subdomain = space.replace("/", "-")
            headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
            try:
                res = requests.get(f"https://{subdomain}.hf.space/ping", headers=headers, timeout=8)
                if res.status_code in [200, 302]:
                    is_ok = True
            except Exception:
                pass

        if is_ok:
            results.append(f"• <b>{space}</b>: ✅ Работает (RUNNING)")
        else:
            if hf_api:
                try: hf_api.restart_space(repo_id=space)
                except: pass
            results.append(f"• <b>{space}</b>: ⚠️ Код ({stage_info}) ➔ Перезапущен")

    return results
