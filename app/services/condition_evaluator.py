import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class EvaluationResult:
    should_notify: bool
    matched_reasons: list[str] = field(default_factory=list)
    skip_reasons: list[str] = field(default_factory=list)


def evaluate_conditions(book, sale_item, conditions: list) -> EvaluationResult:
    """
    Evaluate notification conditions for a sale item.
    If conditions is empty, fall back to legacy Book flag logic.
    If conditions exist, notify if ANY one AND-group condition is fully met.
    """
    if not conditions:
        return evaluate_legacy(book, sale_item)

    all_skip_reasons: list[str] = []
    for condition in conditions:
        ok, matched, unmet = evaluate_single_condition(condition, sale_item)
        if ok:
            return EvaluationResult(should_notify=True, matched_reasons=matched)
        all_skip_reasons.extend(unmet)

    return EvaluationResult(should_notify=False, skip_reasons=all_skip_reasons)


def evaluate_single_condition(condition, sale_item) -> tuple[bool, list[str], list[str]]:
    """
    Evaluate a single AND-group condition against a sale item.
    Returns (all_met, matched_reasons, unmet_reasons).
    """
    matched: list[str] = []
    unmet: list[str] = []

    if condition.min_discount_rate is not None:
        rate = sale_item.discount_rate or 0
        if rate >= condition.min_discount_rate:
            matched.append(f"割引率{rate}% >= {condition.min_discount_rate}%")
        else:
            unmet.append(f"割引率が条件未満 ({rate}% < {condition.min_discount_rate}%)")

    if condition.cashback_only:
        if sale_item.cashback_info:
            matched.append("キャッシュバック対象")
        else:
            unmet.append("キャッシュバック対象外")

    if condition.min_cashback_rate is not None:
        rate = _extract_cashback_rate(sale_item.cashback_info)
        if rate is not None and rate >= condition.min_cashback_rate:
            matched.append(f"キャッシュバック率{rate}% >= {condition.min_cashback_rate}%")
        else:
            actual = f"{rate}%" if rate is not None else "なし"
            unmet.append(f"キャッシュバック率が条件未満 ({actual} < {condition.min_cashback_rate}%)")

    if condition.volume_filter:
        volume_list = _parse_volume_filter(condition.volume_filter)
        if _volume_matches(volume_list, sale_item.volume):
            matched.append(f"対象巻: {sale_item.volume}")
        else:
            unmet.append(f"対象巻ではない ({sale_item.volume})")

    if condition.cheapest_only:
        if getattr(sale_item, "is_cheapest", False):
            matched.append("過去最安値更新")
        else:
            unmet.append("過去最安値ではない")

    if condition.free_only:
        if getattr(sale_item, "is_free", False):
            matched.append("無料")
        else:
            unmet.append("無料ではない")

    all_met = len(unmet) == 0
    return all_met, matched, unmet


def evaluate_legacy(book, sale_item) -> EvaluationResult:
    """Legacy Book flag-based notification logic (used when no conditions are set)."""
    should_notify = False
    reasons: list[str] = []

    if getattr(sale_item, "is_cheapest", False) and getattr(book, "notify_on_cheapest", True):
        should_notify = True
        reasons.append("過去最安値として掲載")
    if getattr(sale_item, "is_high_return", False) and getattr(book, "notify_on_high_return", True):
        should_notify = True
        reasons.append("高還元として掲載")
    if getattr(sale_item, "is_free", False) and getattr(book, "notify_on_free", True):
        should_notify = True
        reasons.append("無料として掲載")
    if getattr(sale_item, "cashback_info", None) and getattr(book, "notify_on_cashback", True):
        should_notify = True
        reasons.append("キャッシュバック対象として掲載")
    if (getattr(book, "notify_discount_threshold", None) and
            getattr(sale_item, "discount_rate", None) and
            sale_item.discount_rate >= book.notify_discount_threshold):
        should_notify = True
        reasons.append(f"割引率{sale_item.discount_rate}%（閾値{book.notify_discount_threshold}%以上）")
    if (getattr(book, "notify_return_threshold", None) and
            getattr(sale_item, "point_rate", None) and
            sale_item.point_rate >= book.notify_return_threshold):
        should_notify = True
        reasons.append(f"還元率{sale_item.point_rate}%（閾値{book.notify_return_threshold}%以上）")
    if (getattr(book, "notify_price_threshold", None) and
            getattr(sale_item, "effective_price", None) and
            sale_item.effective_price <= book.notify_price_threshold):
        should_notify = True
        reasons.append(f"実質価格{sale_item.effective_price}円（閾値{book.notify_price_threshold}円以下）")

    if should_notify:
        return EvaluationResult(should_notify=True, matched_reasons=reasons)
    return EvaluationResult(should_notify=False, skip_reasons=["通知条件に一致する項目なし（レガシー判定）"])


def _extract_cashback_rate(cashback_info: str | None) -> int | None:
    """Extract numeric cashback rate from cashback_info string. Returns None if not found."""
    if not cashback_info:
        return None
    import re
    match = re.search(r"(\d+)\s*%", cashback_info)
    if match:
        return int(match.group(1))
    return None


def _parse_volume_filter(volume_filter) -> list[str]:
    """Parse volume_filter which may be a JSON string or already a list."""
    if isinstance(volume_filter, list):
        return volume_filter
    if isinstance(volume_filter, str):
        try:
            parsed = json.loads(volume_filter)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def _volume_matches(volume_list: list[str], sale_volume: str | None) -> bool:
    """Check if sale_volume matches any of the volume_filter entries."""
    if not volume_list:
        return True
    if not sale_volume:
        return False

    import unicodedata

    def norm(s: str) -> str:
        return unicodedata.normalize("NFKC", s).strip().lower()

    norm_sale = norm(sale_volume)

    for v in volume_list:
        if v == "latest":
            return True
        if norm(str(v)) in norm_sale or norm_sale in norm(str(v)):
            return True
    return False
