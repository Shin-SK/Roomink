"""売上見込みと精算で共用する、雑費控除前の報酬計算。"""

LEGACY_PAY_VERSION = 1
CURRENT_PAY_VERSION = 2


def compensation_parts(cast, course_sales, options_sales, nomination_sales=0,
                       extension_sales=0, *, version=CURRENT_PAY_VERSION):
    if version not in (LEGACY_PAY_VERSION, CURRENT_PAY_VERSION):
        raise ValueError("未対応の報酬計算方式です")
    course_base = course_sales + (extension_sales if version == CURRENT_PAY_VERSION else 0)
    return {
        "course_pay": course_base * cast.course_back_rate // 100,
        "option_pay": options_sales * cast.option_back_rate // 100,
        "nomination_pay": nomination_sales if cast.store.nomination_fullback_enabled else 0,
    }


def compensation_total(cast, course_sales, options_sales, nomination_sales=0,
                       extension_sales=0, *, version=CURRENT_PAY_VERSION):
    return sum(compensation_parts(
        cast, course_sales, options_sales, nomination_sales, extension_sales, version=version,
    ).values())
