from db import get_db

def add_draft(draft_type: str, payload: str, target: str = "") -> int:
    """Сохраняет черновик со статусом pending и возвращает его ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO drafts (type, target, payload, status) VALUES (?, ?, ?, 'pending')",
            (draft_type, target, payload)
        )
        conn.commit()
        return cursor.lastrowid

def get_pending_drafts():
    """Возвращает все ожидающие согласования черновики."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM drafts WHERE status = 'pending' ORDER BY id ASC")
        return cursor.fetchall()

def approve_draft(draft_id: int, variant_idx: int = 1) -> tuple[bool, str]:
    """Утверждает черновик и возвращает выбранный текст."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM drafts WHERE id = ? AND status = 'pending'", (draft_id,))
        draft = cursor.fetchone()
        if not draft:
            return False, "Черновик не найден или уже обработан."
        
        variants = draft["payload"].split("|||")
        selected_text = variants[variant_idx - 1].strip() if 0 < variant_idx <= len(variants) else variants[0].strip()
        
        cursor.execute("UPDATE drafts SET status = 'approved' WHERE id = ?", (draft_id,))
        conn.commit()
        return True, selected_text

def reject_draft(draft_id: int) -> bool:
    """Отклоняет черновик."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE drafts SET status = 'rejected' WHERE id = ?", (draft_id,))
        conn.commit()
        return cursor.rowcount > 0
