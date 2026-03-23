import re


def normalize_phone(phone: str) -> str:
    """
    電話番号を正規化する。
    1) 数字以外をすべて除去
    2) +81（日本国番号）を国内形式に戻す (81X… → 0X…)
       携帯 (090/080/070)、IP電話 (050)、固定電話 (03/06 等) すべて対応
    空/None はそのまま返す。
    """
    if not phone:
        return phone or ""
    digits = re.sub(r"\D", "", phone)
    # 81 + 1桁以上 で始まり、81の後が 0 以外 → 日本の国際番号
    if len(digits) >= 11 and digits.startswith("81") and digits[2] != "0":
        digits = "0" + digits[2:]
    return digits
