"""Unit tests for condition_evaluator.py"""
from dataclasses import dataclass
from typing import Optional

from app.services.condition_evaluator import (
    _extract_cashback_rate,
    _volume_matches,
    evaluate_conditions,
    evaluate_single_condition,
)


@dataclass
class MockCondition:
    min_discount_rate: Optional[int] = None
    cashback_only: bool = False
    min_cashback_rate: Optional[int] = None
    volume_filter: Optional[list] = None
    cheapest_only: bool = False
    free_only: bool = False


@dataclass
class MockSaleItem:
    discount_rate: int = 0
    cashback_info: Optional[str] = None
    volume: Optional[str] = None
    is_cheapest: bool = False
    is_free: bool = False
    is_high_return: bool = False
    point_rate: int = 0


@dataclass
class MockBook:
    notify_on_cheapest: bool = True
    notify_on_high_return: bool = True
    notify_on_free: bool = True
    notify_on_cashback: bool = True
    notify_discount_threshold: Optional[int] = None
    notify_return_threshold: Optional[int] = None
    notify_price_threshold: Optional[int] = None


class TestEvaluateSingleCondition:
    def test_discount_rate_meets_threshold(self):
        cond = MockCondition(min_discount_rate=50)
        sale = MockSaleItem(discount_rate=60)
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is True
        assert len(matched) == 1
        assert len(unmet) == 0

    def test_discount_rate_below_threshold(self):
        cond = MockCondition(min_discount_rate=50)
        sale = MockSaleItem(discount_rate=30)
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is False
        assert len(unmet) == 1
        assert "条件未満" in unmet[0]

    def test_cashback_only_with_cashback(self):
        cond = MockCondition(cashback_only=True)
        sale = MockSaleItem(cashback_info="30%還元")
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is True
        assert "キャッシュバック対象" in matched

    def test_cashback_only_without_cashback(self):
        cond = MockCondition(cashback_only=True)
        sale = MockSaleItem(cashback_info=None)
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is False
        assert "キャッシュバック対象外" in unmet

    def test_cheapest_only_is_cheapest(self):
        cond = MockCondition(cheapest_only=True)
        sale = MockSaleItem(is_cheapest=True)
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is True
        assert "過去最安値更新" in matched

    def test_cheapest_only_not_cheapest(self):
        cond = MockCondition(cheapest_only=True)
        sale = MockSaleItem(is_cheapest=False)
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is False

    def test_free_only_is_free(self):
        cond = MockCondition(free_only=True)
        sale = MockSaleItem(is_free=True)
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is True

    def test_free_only_not_free(self):
        cond = MockCondition(free_only=True)
        sale = MockSaleItem(is_free=False)
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is False

    def test_combined_conditions_all_met(self):
        cond = MockCondition(min_discount_rate=50, cashback_only=True)
        sale = MockSaleItem(discount_rate=60, cashback_info="20%還元")
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is True
        assert len(unmet) == 0

    def test_combined_conditions_one_not_met(self):
        cond = MockCondition(min_discount_rate=50, cashback_only=True)
        sale = MockSaleItem(discount_rate=60, cashback_info=None)
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is False
        assert len(unmet) == 1

    def test_volume_filter_match(self):
        cond = MockCondition(volume_filter=["1", "2", "3"])
        sale = MockSaleItem(volume="第1巻")
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is True

    def test_volume_filter_no_match(self):
        cond = MockCondition(volume_filter=["1", "2"])
        sale = MockSaleItem(volume="第5巻")
        ok, matched, unmet = evaluate_single_condition(cond, sale)
        assert ok is False


class TestEvaluateConditions:
    def test_no_conditions_falls_back_to_legacy(self):
        book = MockBook(notify_on_cheapest=True)
        sale = MockSaleItem(is_cheapest=True)
        result = evaluate_conditions(book, sale, [])
        assert result.should_notify is True

    def test_no_conditions_legacy_no_match(self):
        book = MockBook(
            notify_on_cheapest=False,
            notify_on_high_return=False,
            notify_on_free=False,
            notify_on_cashback=False,
        )
        sale = MockSaleItem()
        result = evaluate_conditions(book, sale, [])
        assert result.should_notify is False

    def test_single_condition_met(self):
        book = MockBook()
        cond = MockCondition(min_discount_rate=50)
        sale = MockSaleItem(discount_rate=70)
        result = evaluate_conditions(book, sale, [cond])
        assert result.should_notify is True
        assert len(result.matched_reasons) > 0

    def test_single_condition_not_met(self):
        book = MockBook()
        cond = MockCondition(min_discount_rate=50)
        sale = MockSaleItem(discount_rate=30)
        result = evaluate_conditions(book, sale, [cond])
        assert result.should_notify is False
        assert len(result.skip_reasons) > 0

    def test_multiple_conditions_or_logic_first_met(self):
        book = MockBook()
        cond1 = MockCondition(min_discount_rate=50)
        cond2 = MockCondition(min_discount_rate=30)
        sale = MockSaleItem(discount_rate=40)
        # cond1 not met (40 < 50), cond2 met (40 >= 30)
        result = evaluate_conditions(book, sale, [cond1, cond2])
        assert result.should_notify is True

    def test_multiple_conditions_none_met(self):
        book = MockBook()
        cond1 = MockCondition(min_discount_rate=70)
        cond2 = MockCondition(cheapest_only=True)
        sale = MockSaleItem(discount_rate=40, is_cheapest=False)
        result = evaluate_conditions(book, sale, [cond1, cond2])
        assert result.should_notify is False


class TestExtractCashbackRate:
    def test_extracts_percentage(self):
        assert _extract_cashback_rate("30%還元") == 30
        assert _extract_cashback_rate("20% ポイント") == 20

    def test_returns_none_for_no_percent(self):
        assert _extract_cashback_rate("ポイント還元") is None
        assert _extract_cashback_rate(None) is None
        assert _extract_cashback_rate("") is None


class TestVolumeMatches:
    def test_empty_filter_matches_all(self):
        assert _volume_matches([], "第1巻") is True
        assert _volume_matches([], None) is True

    def test_latest_matches_any(self):
        assert _volume_matches(["latest"], "第10巻") is True

    def test_volume_match(self):
        assert _volume_matches(["1", "2"], "第1巻") is True

    def test_volume_no_match(self):
        assert _volume_matches(["1", "2"], "第5巻") is False

    def test_none_sale_volume_no_match(self):
        assert _volume_matches(["1", "2"], None) is False
