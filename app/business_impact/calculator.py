from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

ZERO = Decimal("0")
ONE = Decimal("1")
RATE_QUANTUM = Decimal("0.000001")
MINUTE_QUANTUM = Decimal("0.01")


class ImpactCalculator:
    @staticmethod
    def minutes_saved(manual_minutes: Decimal, ai_minutes: Decimal) -> Decimal:
        return max(manual_minutes - ai_minutes, ZERO).quantize(
            MINUTE_QUANTUM, rounding=ROUND_HALF_UP
        )

    @staticmethod
    def automation_rate(automated_steps: int, steps_before: int) -> Decimal:
        denominator = max(steps_before, 1)
        value = Decimal(max(automated_steps, 0)) / Decimal(denominator)
        return min(value, ONE).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)

    @staticmethod
    def ratio(numerator: int, denominator: int) -> Decimal:
        if denominator <= 0:
            return ZERO.quantize(RATE_QUANTUM)
        return (Decimal(max(numerator, 0)) / Decimal(denominator)).quantize(
            RATE_QUANTUM, rounding=ROUND_HALF_UP
        )

    @classmethod
    def first_pass_acceptance_rate(cls, accepted: int, completed: int) -> Decimal:
        return cls.ratio(accepted, completed)

    @classmethod
    def revision_rate(cls, tasks_with_rework: int, completed: int) -> Decimal:
        return cls.ratio(tasks_with_rework, completed)

    @classmethod
    def error_rate(cls, tasks_with_errors: int, completed: int) -> Decimal:
        return cls.ratio(tasks_with_errors, completed)

    @staticmethod
    def user_satisfaction(ratings: Iterable[int]) -> Decimal:
        values = list(ratings)
        if not values:
            return ZERO.quantize(MINUTE_QUANTUM)
        return (Decimal(sum(values)) / Decimal(len(values))).quantize(
            MINUTE_QUANTUM, rounding=ROUND_HALF_UP
        )

    @classmethod
    def would_use_again_rate(cls, positive: int, feedback_count: int) -> Decimal:
        return cls.ratio(positive, feedback_count)
