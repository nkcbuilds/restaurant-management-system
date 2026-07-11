"""Phase 2 baselines: each is simple, deterministic, and explainable."""

from datetime import date, timedelta

from baselines import (
    BaselineForecast,
    baseline_moving_average,
    baseline_recent_weighted,
    baseline_same_weekday,
    bias,
    mae,
    overprep_waste,
    pick_best,
    run_all_baselines,
    stockout_rate,
    wape,
)


def _weekly_history(base_date: date, weekly_values: list[float]) -> list[tuple[str, float]]:
    """Build a (date_str, qty) list for the same weekday, N weeks back."""
    out: list[tuple[str, float]] = []
    for i, v in enumerate(weekly_values):
        d = base_date - timedelta(days=7 * i)
        out.append((d.isoformat(), v))
    return list(reversed(out))


def test_same_weekday_average_basic():
    target = date(2026, 1, 12)  # Monday
    # Constant weekly demand: 20 every Monday for the last 4 weeks.
    history = _weekly_history(target, [20, 20, 20, 20])
    f = baseline_same_weekday(history, target, "evening")
    assert isinstance(f, BaselineForecast)
    assert f.model == "baseline_same_weekday"
    assert f.point == 20.0
    assert f.low <= f.point <= f.high
    # n=4 → 'low' sufficiency (per _classify_sample_size)
    assert f.data_sufficiency == "low"


def test_same_weekday_average_follows_recent():
    target = date(2026, 1, 12)  # Monday
    # Weekly demand rising toward today: oldest=14, most-recent=20.
    # The most recent week should dominate the weighted average.
    history = _weekly_history(target, [20, 18, 16, 14])
    f = baseline_same_weekday(history, target, "evening")
    assert 17.0 <= f.point <= 19.5  # heavily weighted toward 20 (most recent)


def test_same_weekday_insufficient_when_no_history():
    f = baseline_same_weekday([], date(2026, 1, 12), "morning")
    assert f.data_sufficiency == "insufficient"
    assert f.point == 0.0
    assert f.confidence < 0.2


def test_moving_average_window_respected():
    target = date(2026, 1, 12)
    history = [
        (d.isoformat(), float(q))
        for d, q in zip(
            [target - timedelta(days=k) for k in range(1, 11)],
            [5, 10, 15, 20, 25, 30, 35, 40, 45, 50],
        )
    ]
    f = baseline_moving_average(history, target, "evening", window=4)
    # Last 4 = 35,40,45,50 -> mean 42.5
    assert 40.0 <= f.point <= 45.0


def test_moving_average_insufficient_when_empty():
    f = baseline_moving_average([], date(2026, 1, 12), "evening")
    assert f.data_sufficiency == "insufficient"


def test_recent_weighted_emphasises_recent():
    target = date(2026, 1, 12)
    # 28 days of constant=10, then a spike one day ago.
    rows = [(target - timedelta(days=k), 10.0) for k in range(2, 30)]
    rows.append((target - timedelta(days=1), 100.0))
    history = [(d.isoformat(), v) for d, v in rows]
    f = baseline_recent_weighted(history, target, "evening", half_life_days=14)
    # The recent spike should pull the weighted average above the
    # 28-day-old baseline of 10.
    assert f.point >= 12.0
    assert f.point <= 50.0


def test_pick_best_prefers_higher_confidence():
    a = BaselineForecast(10, 8, 12, 0.4, "low", "a")
    b = BaselineForecast(10, 8, 12, 0.8, "strong", "b")
    c = BaselineForecast(10, 8, 12, 0.05, "insufficient", "c")
    assert pick_best([a, b, c]).model == "b"


def test_pick_best_falls_back_when_all_insufficient():
    a = BaselineForecast(0, 0, 0, 0.05, "insufficient", "a")
    b = BaselineForecast(0, 0, 0, 0.05, "insufficient", "b")
    assert pick_best([a, b]).model == "a"


def test_run_all_returns_three_baselines():
    history = _weekly_history(date(2026, 1, 12), [10, 12, 14, 16, 18])
    out = run_all_baselines(history, date(2026, 1, 12), "evening")
    models = {b.model for b in out}
    assert models == {"baseline_same_weekday", "baseline_ma", "baseline_recent"}


# ---- Accuracy metrics ----------------------------------------------------


def test_wape_zero_when_perfect():
    a = [10, 20, 30]
    p = [10, 20, 30]
    assert wape(a, p) == 0.0


def test_wape_known_value():
    # |10-12|+|20-22|+|30-28| = 2+2+2 = 6, denom = 60
    a = [10, 20, 30]
    p = [12, 22, 28]
    assert abs(wape(a, p) - 0.1) < 1e-9


def test_wape_undefined_when_all_zeros():
    assert wape([0, 0, 0], [1, 2, 3]) != wape([0, 0, 0], [1, 2, 3])  # NaN != NaN


def test_mae_simple():
    assert mae([10, 20], [12, 22]) == 2.0


def test_bias_positive_when_under_forecast():
    # predicted > actual => we prepared too much.
    assert bias([10, 20], [12, 22]) == 2.0


def test_stockout_rate_simple():
    a = [10, 20, 30]
    p = [15, 15, 35]  # first one is a stockout (10 < 15 is false; 20 > 15 true)
    assert stockout_rate(a, p) == 1 / 3


def test_overprep_waste_with_buffer():
    a = [10, 10, 10]
    p = [10, 10, 10]
    # When prediction matches actual, the safety buffer itself becomes waste:
    # (10 * 1.2 - 10) * 3 = 2 * 3 = 6
    assert overprep_waste(a, p, safety_buffer=0.2) == 6.0

    a = [10, 10, 10]
    p = [100, 100, 100]
    # (100 * 1.2 - 10) * 3 = 110 * 3 = 330
    assert overprep_waste(a, p, safety_buffer=0.2) == 330.0

    a = [10, 10, 10]
    p = [5, 5, 5]
    # (5 * 1.2 - 10) = -4 each, max(0, ...) = 0 — under-forecasting never
    # produces over-prep waste.
    assert overprep_waste(a, p, safety_buffer=0.2) == 0.0
