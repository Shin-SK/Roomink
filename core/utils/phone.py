import re


def normalize_phone(phone: str) -> str:
    """数字以外をすべて除去して電話番号を正規化する。空/Noneはそのまま返す。"""
    if not phone:
        return phone or ""
    return re.sub(r"\D", "", phone)
