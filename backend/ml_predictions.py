"""
RestaurantOS prediction engine.

Phase 2 refactor:
  * Always run baselines (3 of them) and pick the highest-confidence one.
  * Prophet is OPTIONAL; it stays behind a lazy import so the API still
    boots without pandas/numpy/prophet installed.
  * Predictions carry model provenance (which baseline, what confidence,
    what data sufficiency) so the UI can render an honest "why this
    recommendation?" answer.
  * A separate `backtest.py` module walks history forward and tells you
    which model actually wins per (dish, period); use it from the CLI
    (`backtest_cli.py`) or from the worker.
"""

from __future__ import annotations

import logging
import warnings
from datetime import date as _date
from datetime import datetime, timedelta
from typing import Any

from baselines import BaselineForecast, pick_best, run_all_baselines

# pandas / numpy / prophet are heavy. They are imported lazily so the
# API can boot and tests can run without them. When the worker is the
# only thing exercising predictions, install requirements-ml.txt on
# that process.
_pd = None
_np = None
Prophet = None
_PROPHET_AVAILABLE = False


def _ensure_ml():
    global _pd, _np, Prophet, _PROPHET_AVAILABLE
    if _pd is not None:
        return
    import numpy as np
    import pandas as pd

    _pd = pd
    _np = np
    try:
        from prophet import Prophet as _Prophet  # type: ignore

        warnings.filterwarnings("ignore", category=UserWarning, module="prophet")
        logging.getLogger("prophet").setLevel(logging.WARNING)
        Prophet = _Prophet
        _PROPHET_AVAILABLE = True
    except Exception:  # pragma: no cover
        _PROPHET_AVAILABLE = False


logger = logging.getLogger(__name__)


class PredictionEngine:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.models = {}
        self.last_training = None
        self.prophet_available = _PROPHET_AVAILABLE

    # ----------------------------------------------------------------
    # Phase 2: structured predictions
    # ----------------------------------------------------------------

    def get_structured_predictions(self, target_date: str) -> list[dict[str, Any]]:
        """Return structured predictions for the target date.

        For every (dish, period) with at least one historical point, we
        run every baseline and pick the highest-confidence one. The
        output includes model provenance, a low/high range, and a
        human-readable reason.
        """
        history = self.db_manager.get_historical_order_data(days=60)
        if not history:
            return []

        try:
            target = _date.fromisoformat(target_date)
        except ValueError:
            return []

        per_key: dict[tuple[str, str], list[tuple[str, float]]] = {}
        for row in history:
            per_key.setdefault((row["dish_id"], row["period"]), []).append(
                (row["ds"], float(row["y"]))
            )

        dishes = {r["dish_id"]: r["dish_name"] for r in history}
        out: list[dict[str, Any]] = []
        for (dish_id, period), rows in per_key.items():
            baselines = run_all_baselines(rows, target, period)
            chosen = pick_best(baselines)
            entry = self._format_prediction(
                dish_id=dish_id,
                dish_name=dishes.get(dish_id, "?"),
                period=period,
                chosen=chosen,
                all_baselines=baselines,
                target_date=target_date,
            )
            out.append(entry)
        return out

    def _format_prediction(
        self,
        *,
        dish_id: str,
        dish_name: str,
        period: str,
        chosen: BaselineForecast,
        all_baselines: list[BaselineForecast],
        target_date: str,
    ) -> dict[str, Any]:
        # Recommended prep = round(predicted * (1 + buffer)). Buffer
        # shrinks as confidence grows; for very low data we use a
        # bigger buffer to avoid stockouts while we gather signal.
        if chosen.data_sufficiency == "insufficient":
            buffer = 0.5
        elif chosen.data_sufficiency == "low":
            buffer = 0.3
        else:
            buffer = 0.2
        recommended_prep = max(2, int(round(chosen.point * (1 + buffer))))

        reasons = self._explain(dish_name, period, chosen, all_baselines)

        return {
            "dish_id": dish_id,
            "dish_name": dish_name,
            "period": period,
            "predicted_demand": int(round(chosen.point)),
            "low": int(round(chosen.low)),
            "high": int(round(chosen.high)),
            "recommended_prep": recommended_prep,
            "model_used": chosen.model,
            "model_confidence": round(chosen.confidence, 3),
            "data_sufficiency": chosen.data_sufficiency,
            "reason": "; ".join(reasons),
            "all_baselines": [
                {
                    "model": b.model,
                    "point": round(b.point, 2),
                    "low": round(b.low, 2),
                    "high": round(b.high, 2),
                    "confidence": round(b.confidence, 3),
                    "data_sufficiency": b.data_sufficiency,
                }
                for b in all_baselines
            ],
            "prediction_date": target_date,
        }

    def _explain(
        self,
        dish_name: str,
        period: str,
        chosen: BaselineForecast,
        all_baselines: list[BaselineForecast],
    ) -> list[str]:
        reasons: list[str] = []
        if chosen.data_sufficiency == "insufficient":
            reasons.append(
                f"Not enough history for {dish_name} ({period}); using 0 as a safe default."
            )
            return reasons
        reasons.append(
            f"Forecast for {dish_name} ({period}) uses {chosen.model.replace('_', ' ')}."
        )
        if chosen.low == chosen.high:
            reasons.append("Demand has been very steady in the recent window.")
        else:
            reasons.append(
                f"Realistic range is {int(chosen.low)}\u2013{int(chosen.high)} portions."
            )
        # Compare to other baselines to surface disagreement.
        for b in all_baselines:
            if b.model == chosen.model or b.data_sufficiency == "insufficient":
                continue
            delta = b.point - chosen.point
            if abs(delta) >= max(1.0, 0.2 * chosen.point):
                reasons.append(
                    f"{b.model.replace('_', ' ')} would have predicted "
                    f"{int(round(b.point))} portions ({'+' if delta > 0 else ''}"
                    f"{int(round(delta))} vs. chosen)."
                )
        return reasons

    # ----------------------------------------------------------------
    # Phase 1 entry points (kept for backwards compatibility)
    # ----------------------------------------------------------------

    async def generate_predictions(self, target_date: str | None = None) -> dict[str, Any]:
        """Phase 1 entry point: produce structured predictions and persist them."""
        if not target_date:
            target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

        structured = self.get_structured_predictions(target_date)
        if structured:
            persisted = []
            for entry in structured:
                persisted.append(
                    {
                        "dish_id": entry["dish_id"],
                        "prediction_date": entry["prediction_date"],
                        "period": entry["period"],
                        "predicted_demand": entry["predicted_demand"],
                        "confidence": entry["model_confidence"] * 100.0,
                        "recommended_prep": entry["recommended_prep"],
                        "factors": [entry["reason"]],
                    }
                )
            self.db_manager.save_predictions(persisted)
        return {
            "predictions_generated": len(structured),
            "target_date": target_date,
            "message": "Predictions generated successfully",
        }

    def _predict_dish_demand(self, *args, **kwargs):  # pragma: no cover
        """Legacy Prophet-only path. Retained only for backwards
        compatibility; new code should use get_structured_predictions."""
        return None

    def _analyze_prediction_factors(self, *args, **kwargs):  # pragma: no cover
        return []

    def get_predictions(self, date: str) -> list[dict[str, Any]]:
        return self.db_manager.get_predictions(date)

    def get_model_performance(self) -> dict[str, Any]:
        return {
            "models_trained": len(self.models),
            "last_training": self.last_training,
            "data_points_used": "Variable by dish",
            "avg_confidence": "see backtest",
        }


# Example usage for testing
if __name__ == "__main__":
    import asyncio

    from database import DatabaseManager

    async def test_predictions():
        db = DatabaseManager()
        engine = PredictionEngine(db)

        result = await engine.generate_predictions()
        print(f"Prediction result: {result}")

        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        predictions = engine.get_predictions(tomorrow)
        print(f"Found {len(predictions)} predictions for {tomorrow}")

    asyncio.run(test_predictions())
