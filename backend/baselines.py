"""
Phase 2: trustworthy forecasting baselines.

These are deliberately simple. The point is that they should be
correct, fast, and explainable BEFORE we bring in Prophet. We always
run baseline + Prophet; the backtester picks the lower-WAPE model per
(dish, period).

A baseline takes:
  * `history`        -- a list of (date_str, quantity) tuples ordered
                         ASCENDING in time
  * `target_date`    -- the date we want a forecast for (datetime.date)
  * `period`         -- 'morning' | 'afternoon' | 'evening' (not used by
                         the math, but useful for downstream naming)

It returns a `BaselineForecast`:
  * `point`          -- best single-number prediction
  * `low`, `high`    -- realistic range (used to size the safety buffer)
  * `confidence`     -- 0..1, derived from sample size and dispersion
  * `data_sufficiency` -- 'insufficient' | 'low' | 'ok' | 'strong'
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class BaselineForecast:
    point: float
    low: float
    high: float
    confidence: float  # 0..1
    data_sufficiency: str  # 'insufficient' | 'low' | 'ok' | 'strong'
    model: str  # which baseline produced this


HistoryRow = tuple[str, float]  # (date_str, quantity)


def _parse_date(s: str) -> date:
    """Tolerant YYYY-MM-DD parser."""
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _classify_sample_size(n: int) -> str:
    if n <= 0:
        return "insufficient"
    if n < 4:
        return "insufficient"
    if n < 8:
        return "low"
    if n < 16:
        return "ok"
    return "strong"


def _confidence_from_data(n: int, dispersion_cv: float) -> float:
    """Convert (n, coefficient of variation) to a 0..1 confidence.

    The shape is intentionally simple: more data -> higher confidence;
    higher dispersion -> lower confidence. We clamp at [0.05, 0.95] so
    we never claim either certainty.
    """
    if n <= 0:
        return 0.05
    size_score = min(1.0, math.log2(n + 1) / 4.0)  # 0..1 across n=0..16
    dispersion_score = max(0.0, 1.0 - dispersion_cv)
    raw = 0.5 * size_score + 0.5 * dispersion_score
    return float(max(0.05, min(0.95, raw)))


def _cv(values: Sequence[float]) -> float:
    """Coefficient of variation = stdev / mean. Returns 0.0 when mean is 0."""
    if len(values) < 2:
        return 0.0
    m = statistics.mean(values)
    if m <= 0:
        return 0.0
    return statistics.stdev(values) / m


def _safe_round(x: float) -> float:
    """Round to 2 dp without going negative for quantities."""
    return max(0.0, round(x, 2))


# ---------------------------------------------------------------------------
# Baseline 1: same-weekday average over the last 8 weeks.
# ---------------------------------------------------------------------------


def baseline_same_weekday(
    history: Iterable[HistoryRow],
    target_date: date,
    period: str,
) -> BaselineForecast:
    rows = list(history)
    target_dow = target_date.weekday()  # Monday=0
    weeks_back = 8
    same_dow_values: list[float] = []

    for date_str, qty in rows:
        try:
            d = _parse_date(date_str)
        except ValueError:
            continue
        if d.weekday() != target_dow:
            continue
        if (target_date - d).days < 0 or (target_date - d).days > weeks_back * 7:
            continue
        same_dow_values.append(float(qty))

    if not same_dow_values:
        return BaselineForecast(
            point=0.0,
            low=0.0,
            high=0.0,
            confidence=0.05,
            data_sufficiency="insufficient",
            model="baseline_same_weekday",
        )

    n = len(same_dow_values)
    cv = _cv(same_dow_values)
    # Weights: more recent weeks count more (geometric decay).
    # Without per-week timestamps inside the window we approximate by
    # sorting by value's index; for Phase 2 this is a 1-week decay per
    # older sample (close enough).
    weights = [0.6**i for i in range(n)][::-1]  # newer = higher weight
    weighted = sum(v * w for v, w in zip(same_dow_values, weights)) / sum(weights)

    low = max(0.0, weighted * (1 - cv))
    high = weighted * (1 + cv)

    return BaselineForecast(
        point=_safe_round(weighted),
        low=_safe_round(low),
        high=_safe_round(high),
        confidence=_confidence_from_data(n, cv),
        data_sufficiency=_classify_sample_size(n),
        model="baseline_same_weekday",
    )


# ---------------------------------------------------------------------------
# Baseline 2: moving average of the last 4 same-period observations.
# ---------------------------------------------------------------------------


def baseline_moving_average(
    history: Iterable[HistoryRow],
    target_date: date,
    period: str,
    window: int = 4,
) -> BaselineForecast:
    rows = list(history)
    recent = [(d, float(q)) for d, q in rows[-window:]]
    if not recent:
        return BaselineForecast(
            point=0.0,
            low=0.0,
            high=0.0,
            confidence=0.05,
            data_sufficiency="insufficient",
            model="baseline_ma",
        )

    values = [v for _, v in recent]
    mean = statistics.mean(values)
    cv = _cv(values)
    n = len(values)

    return BaselineForecast(
        point=_safe_round(mean),
        low=_safe_round(max(0.0, mean * (1 - cv))),
        high=_safe_round(mean * (1 + cv)),
        confidence=_confidence_from_data(n, cv),
        data_sufficiency=_classify_sample_size(n),
        model="baseline_ma",
    )


# ---------------------------------------------------------------------------
# Baseline 3: exponential weighted moving average (half-life 14 days).
# ---------------------------------------------------------------------------


def baseline_recent_weighted(
    history: Iterable[HistoryRow],
    target_date: date,
    period: str,
    half_life_days: int = 14,
) -> BaselineForecast:
    rows = list(history)
    if not rows:
        return BaselineForecast(
            point=0.0,
            low=0.0,
            high=0.0,
            confidence=0.05,
            data_sufficiency="insufficient",
            model="baseline_recent",
        )

    weights: list[float] = []
    values: list[float] = []
    for date_str, qty in rows:
        try:
            d = _parse_date(date_str)
        except ValueError:
            continue
        days_old = max(0, (target_date - d).days)
        w = 0.5 ** (days_old / half_life_days)
        weights.append(w)
        values.append(float(qty))

    if not values:
        return BaselineForecast(
            point=0.0,
            low=0.0,
            high=0.0,
            confidence=0.05,
            data_sufficiency="insufficient",
            model="baseline_recent",
        )

    total_w = sum(weights)
    weighted = sum(v * w for v, w in zip(values, weights)) / total_w

    # Effective sample size after decay.
    ess = total_w**2 / sum(w * w for w in weights) if weights else 0
    cv = _cv(values)

    return BaselineForecast(
        point=_safe_round(weighted),
        low=_safe_round(max(0.0, weighted * (1 - cv))),
        high=_safe_round(weighted * (1 + cv)),
        confidence=_confidence_from_data(int(round(ess)), cv),
        data_sufficiency=_classify_sample_size(int(round(ess))),
        model="baseline_recent",
    )


# ---------------------------------------------------------------------------
# Aggregator: run all baselines and return the best.
# ---------------------------------------------------------------------------


def run_all_baselines(
    history: Iterable[HistoryRow],
    target_date: date,
    period: str,
) -> list[BaselineForecast]:
    """Run every baseline. Caller picks the best one."""
    return [
        baseline_same_weekday(history, target_date, period),
        baseline_moving_average(history, target_date, period),
        baseline_recent_weighted(history, target_date, period),
    ]


def pick_best(baselines: list[BaselineForecast]) -> BaselineForecast:
    """Pick the baseline with the highest confidence that is also above
    the 'insufficient' threshold. If every baseline is insufficient,
    return the first one (so the caller always has *something*)."""
    usable = [b for b in baselines if b.data_sufficiency != "insufficient"]
    if not usable:
        return baselines[0]
    return max(usable, key=lambda b: b.confidence)


# ---------------------------------------------------------------------------
# Forecast accuracy metrics
# ---------------------------------------------------------------------------


def wape(actual: list[float], predicted: list[float]) -> float:
    """Weighted Absolute Percentage Error.

    Sum(|a - p|) / sum(|a|). Returns NaN if actuals are all zero.
    """
    denom = sum(abs(a) for a in actual)
    if denom == 0:
        return float("nan")
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / denom


def mae(actual: list[float], predicted: list[float]) -> float:
    n = len(actual)
    if n == 0:
        return 0.0
    return sum(abs(a - p) for a, p in zip(actual, predicted)) / n


def bias(actual: list[float], predicted: list[float]) -> float:
    """Mean signed error. Positive = under-forecasting, negative = over-forecasting."""
    n = len(actual)
    if n == 0:
        return 0.0
    return sum(p - a for a, p in zip(actual, predicted)) / n


def stockout_rate(actual: list[float], predicted: list[float]) -> float:
    """Fraction of (actual, predicted) pairs where actual > predicted (we ran out)."""
    n = len(actual)
    if n == 0:
        return 0.0
    return sum(1 for a, p in zip(actual, predicted) if a > p) / n


def overprep_waste(
    actual: list[float], predicted: list[float], safety_buffer: float = 0.2
) -> float:
    """Total over-prep waste = sum(max(0, (predicted * (1 + buffer)) - actual))."""
    return sum(max(0.0, p * (1 + safety_buffer) - a) for a, p in zip(actual, predicted))
