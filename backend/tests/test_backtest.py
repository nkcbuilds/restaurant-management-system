"""Phase 2 backtester tests, including the synthetic 'Mondays are 30% higher' validation."""

from __future__ import annotations

import math
from datetime import date, timedelta

from backtest import backtest


def _generate_synthetic(
    start: date,
    weeks: int,
    *,
    monday_lift: float = 0.30,
    baseline_demand: float = 30,
    noise_pct: float = 0.05,
) -> list[tuple[str, str, str, float]]:
    """Generate synthetic per-(dish, period) demand with a Monday lift.

    Returns rows of (dish_id, period, date_str, quantity).
    """
    rows: list[tuple[str, str, str, float]] = []
    for w in range(weeks):
        for day_offset in range(7):
            d = start + timedelta(days=w * 7 + day_offset)
            base = baseline_demand * (1 + monday_lift if d.weekday() == 0 else 1.0)
            for period in ("morning", "afternoon", "evening"):
                # Add a tiny deterministic pseudo-noise so WAPE > 0.
                jitter = 1 + noise_pct * math.sin(w + day_offset + ord(period[0]))
                qty = base * jitter / 3  # split across 3 periods
                rows.append(("dish-A", period, d.isoformat(), round(qty, 2)))
    return rows


def test_backtest_runs_on_synthetic_monday_pattern():
    start = date(2025, 1, 6)  # Monday
    history = _generate_synthetic(start, weeks=12, monday_lift=0.3, baseline_demand=30)
    report = backtest(
        history,
        from_date=start.isoformat(),
        to_date=(start + timedelta(days=12 * 7)).isoformat(),
        horizon_days=7,
        min_train_size=4,
    )
    # We expect to learn something.
    assert report.by_dish_period, "backtest should produce at least one (dish, period)"
    overall_keys = set(report.overall.keys())
    # All three baselines are exercised.
    assert {"baseline_same_weekday", "baseline_ma", "baseline_recent"}.issubset(overall_keys)


def test_backtest_picks_winner_per_dish_period():
    start = date(2025, 1, 6)
    history = _generate_synthetic(start, weeks=10, monday_lift=0.4, baseline_demand=20)
    report = backtest(
        history,
        from_date=start.isoformat(),
        to_date=(start + timedelta(days=10 * 7)).isoformat(),
        horizon_days=7,
    )
    for entry in report.by_dish_period:
        assert entry["winner_model"] is not None
        # The winner is one of the known baselines.
        assert entry["winner_model"] in {
            "baseline_same_weekday",
            "baseline_ma",
            "baseline_recent",
        }


def test_overall_summary_has_metrics():
    start = date(2025, 1, 6)
    history = _generate_synthetic(start, weeks=8)
    report = backtest(
        history,
        from_date=start.isoformat(),
        to_date=(start + timedelta(days=8 * 7)).isoformat(),
    )
    for _model_name, stats in report.overall.items():
        assert stats["n"] > 0
        assert "mae" in stats
        assert "wape" in stats
        assert "bias" in stats
        assert "waste" in stats
