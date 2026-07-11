"""
Phase 2: forecast backtester.

Walks the history forward week-by-week, asks every model to predict
each (dish, period) at that point, then compares against what actually
happened. Reports per-model MAE / WAPE / bias / stockout rate / waste
plus a per-(dish, period) winner.

This is what makes the prediction engine trustworthy: the operator can
look at the backtest output and see which model actually works for
each dish, not just a generic "85% accuracy" label.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from baselines import (
    bias,
    mae,
    overprep_waste,
    run_all_baselines,
    stockout_rate,
    wape,
)


@dataclass
class BacktestResult:
    """One (dish, period, model) result over the backtest window."""

    dish_id: str
    period: str
    model: str
    n: int
    mae: float
    wape: float
    bias: float
    stockout_rate: float
    waste: float
    is_winner: bool = False


@dataclass
class BacktestReport:
    """Aggregate backtest output across all (dish, period, model)."""

    from_date: str
    to_date: str
    by_dish_period: list[dict[str, Any]] = field(default_factory=list)
    overall: dict[str, dict[str, float]] = field(default_factory=dict)


def _bucket(period_str: str) -> str:
    """Bucket a date+time into morning/afternoon/evening."""
    return period_str


def _per_dish_period(
    history: list[tuple[str, str, str, float]],
) -> dict[tuple[str, str], list[tuple[str, float]]]:
    """Group rows by (dish_id, period) -> sorted [(date, quantity)]."""
    out: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    for dish_id, period, date_str, qty in history:
        out[(dish_id, period)].append((date_str, qty))
    for k in out:
        out[k].sort(key=lambda r: r[0])
    return out


def _parse_iso(s: str) -> date:
    return datetime.strptime(s[:10], "%Y-%m-%d").date()


def _simulate_forecast(
    train_history: list[tuple[str, float]],
    target_date: date,
    period: str,
    models: list[str],
) -> dict[str, float]:
    """Run the named models on the (target_date, period) with the
    trimmed training history."""
    out: dict[str, float] = {}
    for f in run_all_baselines(train_history, target_date, period):
        if f.model in models:
            out[f.model] = f.point
    return out


def backtest(
    history: list[tuple[str, str, str, float]],
    *,
    from_date: str,
    to_date: str,
    horizon_days: int = 7,
    min_train_size: int = 4,
    safety_buffer: float = 0.2,
) -> BacktestReport:
    """Walk forward and evaluate every baseline per (dish, period).

    `history` is a flat list of (dish_id, period, date_str, quantity).

    For each evaluation date D in [from_date, to_date] with stride
    `horizon_days`, we use only data whose date is STRICTLY before D
    as training history, predict D, and record the error.
    """
    grouped = _per_dish_period(history)
    start = _parse_iso(from_date)
    end = _parse_iso(to_date)
    eval_dates: list[date] = []
    d = start
    while d <= end:
        eval_dates.append(d)
        d = d + timedelta(days=horizon_days)

    per_key: dict[tuple[str, str], dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    # Also track actuals once per (key, eval_date).
    actuals_lookup: dict[tuple[str, str, date], float] = {}

    for (dish_id, period), rows in grouped.items():
        date_index = {dt: qty for dt, qty in rows}
        for eval_date in eval_dates:
            iso = eval_date.isoformat()
            actuals_lookup[(dish_id, period, eval_date)] = date_index.get(iso, 0.0)

    for (dish_id, period), rows in grouped.items():
        # Build a training-only history by chopping at each eval date.
        for eval_date in eval_dates:
            train = [(d, q) for d, q in rows if _parse_iso(d) < eval_date]
            if len(train) < min_train_size:
                continue
            actual = actuals_lookup.get((dish_id, period, eval_date))
            if actual is None:
                continue
            preds = _simulate_forecast(
                train,
                eval_date,
                period,
                [
                    "baseline_same_weekday",
                    "baseline_ma",
                    "baseline_recent",
                ],
            )
            for model_name, pred in preds.items():
                per_key[(dish_id, period)][model_name].append(pred)
                per_key[(dish_id, period)]["__actual__"].append(actual)

    # Build results
    results: list[BacktestResult] = []
    per_key_aggregates: dict[tuple[str, str], dict[str, dict[str, float]]] = {}
    for key, model_actual in per_key.items():
        dish_id, period = key
        actuals = model_actual.pop("__actual__", [])
        agg_for_key: dict[str, dict[str, float]] = {}
        for model_name, preds in model_actual.items():
            r = BacktestResult(
                dish_id=dish_id,
                period=period,
                model=model_name,
                n=len(preds),
                mae=mae(actuals, preds),
                wape=wape(actuals, preds),
                bias=bias(actuals, preds),
                stockout_rate=stockout_rate(actuals, preds),
                waste=overprep_waste(actuals, preds, safety_buffer=safety_buffer),
            )
            agg_for_key[model_name] = {
                "mae": r.mae,
                "wape": r.wape,
                "bias": r.bias,
                "stockout_rate": r.stockout_rate,
                "waste": r.waste,
                "n": r.n,
            }
            results.append(r)
        per_key_aggregates[key] = agg_for_key

    # Mark winners (lowest WAPE per key, ties broken by lowest MAE).
    by_key: dict[tuple[str, str], list[BacktestResult]] = defaultdict(list)
    for r in results:
        by_key[(r.dish_id, r.period)].append(r)
    for _key, rows in by_key.items():
        # Drop degenerate rows where wape is NaN.
        candidates = [r for r in rows if r.wape == r.wape]  # NaN-safe
        if not candidates:
            continue
        winner = min(candidates, key=lambda r: (r.wape, r.mae))
        for r in rows:
            r.is_winner = r is winner

    # Per-dish-period summary
    by_dish_period: list[dict[str, Any]] = []
    for (dish_id, period), models in per_key_aggregates.items():
        winner_model = None
        winner_wape = float("inf")
        for m, stats in models.items():
            if stats["wape"] == stats["wape"] and stats["wape"] < winner_wape:
                winner_wape = stats["wape"]
                winner_model = m
        by_dish_period.append(
            {
                "dish_id": dish_id,
                "period": period,
                "winner_model": winner_model,
                "models": models,
            }
        )

    # Overall summary across every (key, model)
    overall: dict[str, dict[str, float]] = {}
    for r in results:
        agg = overall.setdefault(
            r.model,
            {"n": 0, "mae_sum": 0.0, "wape_sum": 0.0, "bias_sum": 0.0, "waste_sum": 0.0},
        )
        agg["n"] += r.n
        agg["mae_sum"] += r.mae * r.n
        if r.wape == r.wape:
            agg["wape_sum"] += r.wape * r.n
        agg["bias_sum"] += r.bias * r.n
        agg["waste_sum"] += r.waste
    overall_summary = {
        m: {
            "n": int(v["n"]),
            "mae": round(v["mae_sum"] / v["n"], 3) if v["n"] else 0.0,
            "wape": round(v["wape_sum"] / v["n"], 3) if v["n"] else 0.0,
            "bias": round(v["bias_sum"] / v["n"], 3) if v["n"] else 0.0,
            "waste": round(v["waste_sum"], 2),
        }
        for m, v in overall.items()
    }

    return BacktestReport(
        from_date=from_date,
        to_date=to_date,
        by_dish_period=by_dish_period,
        overall=overall_summary,
    )
