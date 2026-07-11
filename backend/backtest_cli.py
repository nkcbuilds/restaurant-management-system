#!/usr/bin/env python3
"""Phase 2 backtest CLI.

Pulls historical order data from the SQLite DB, runs the backtester,
and prints a per-model summary to stdout. Used by the worker (and by
humans) to verify the forecasting engine is actually useful.

Usage:
    python backtest_cli.py --days 90
    python backtest_cli.py --days 90 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

from backtest import backtest
from database import DatabaseManager


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2 forecast backtester")
    parser.add_argument("--days", type=int, default=90, help="history window in days")
    parser.add_argument("--horizon", type=int, default=7, help="walk-forward stride (days)")
    parser.add_argument("--min-train", type=int, default=4, help="min history points per key")
    parser.add_argument("--buffer", type=float, default=0.2, help="over-prep safety buffer")
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a table")
    args = parser.parse_args()

    db = DatabaseManager()
    raw = db.get_historical_order_data(days=args.days)

    # group by (dish_id, period) → (date, qty)
    rows: list[tuple[str, str, str, float]] = []
    for r in raw:
        rows.append((r["dish_id"], r["period"], r["ds"], float(r["y"])))

    if not rows:
        print("No historical data yet. Place some orders first.", file=sys.stderr)
        return 1

    end = date.today()
    start = end - timedelta(days=args.days)
    report = backtest(
        rows,
        from_date=start.isoformat(),
        to_date=end.isoformat(),
        horizon_days=args.horizon,
        min_train_size=args.min_train,
        safety_buffer=args.buffer,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "from_date": report.from_date,
                    "to_date": report.to_date,
                    "overall": report.overall,
                    "by_dish_period": report.by_dish_period,
                },
                indent=2,
            )
        )
        return 0

    print(f"Backtest window: {report.from_date} -> {report.to_date}")
    print()
    print(f"{'Model':<24} {'N':>6} {'MAE':>8} {'WAPE':>8} {'Bias':>8} {'Waste':>10}")
    print("-" * 70)
    for model, stats in sorted(report.overall.items()):
        print(
            f"{model:<24} {stats['n']:>6} {stats['mae']:>8.2f} {stats['wape']:>8.3f} "
            f"{stats['bias']:>8.2f} {stats['waste']:>10.2f}"
        )
    print()
    print(f"Per (dish, period) winners: {len(report.by_dish_period)} keys")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
