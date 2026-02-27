import re

_JP_MOBILE_PREFIX = {
    "8190": "090",
    "8180": "080",
    "8170": "070",
}


def normalize_phone(phone: str) -> str:
    """
    電話番号を正規化する。
    1) 数字以外をすべて除去
    2) +81 携帯番号を国内形式に戻す (8190→090, 8180→080, 8170→070)
    空/None はそのまま返す。
    """
    if not phone:
        return phone or ""
    digits = re.sub(r"\D", "", phone)
    for intl, domestic in _JP_MOBILE_PREFIX.items():
        if digits.startswith(intl):
            digits = domestic + digits[len(intl):]
            break
    return digits
