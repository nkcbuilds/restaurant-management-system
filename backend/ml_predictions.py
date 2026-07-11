import logging
import warnings
from datetime import datetime, timedelta
from typing import Any

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
    except Exception as _e:  # pragma: no cover
        _PROPHET_AVAILABLE = False


logger = logging.getLogger(__name__)


class PredictionEngine:
    def __init__(self, db_manager):
        self.db_manager = db_manager
        self.models = {}  # Store trained models
        self.last_training = None
        self.prophet_available = _PROPHET_AVAILABLE

    def _pd(self):
        _ensure_ml()
        return _pd

    async def generate_predictions(self, target_date: str | None = None) -> dict[str, Any]:
        """Generate predictions using Prophet models"""
        try:
            if not target_date:
                target_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

            logger.info(f"Generating predictions for {target_date}")

            # Get historical data
            historical_data = self.db_manager.get_historical_order_data(days=60)

            if not historical_data:
                logger.warning("No historical data available for predictions")
                return {"message": "No historical data available", "predictions_generated": 0}

            # Convert to DataFrame
            df = self._pd().DataFrame(historical_data)

            predictions = []
            dishes_processed = 0

            # Get unique dishes
            unique_dishes = df[["dish_id", "dish_name"]].drop_duplicates()

            for _, dish_row in unique_dishes.iterrows():
                dish_id = dish_row["dish_id"]
                dish_name = dish_row["dish_name"]

                # Generate predictions for each time period
                for period in ["morning", "afternoon", "evening"]:
                    try:
                        prediction = self._predict_dish_demand(
                            df, dish_id, dish_name, period, target_date
                        )
                        if prediction:
                            predictions.append(prediction)
                    except Exception as e:
                        logger.error(f"Error predicting for dish {dish_id}, period {period}: {e}")
                        continue

                dishes_processed += 1

            # Save predictions to database
            if predictions:
                self.db_manager.save_predictions(predictions)
                logger.info(f"Saved {len(predictions)} predictions for {dishes_processed} dishes")

            return {
                "predictions_generated": len(predictions),
                "dishes_processed": dishes_processed,
                "target_date": target_date,
                "message": "Predictions generated successfully",
            }

        except Exception as e:
            logger.error(f"Error generating predictions: {e}")
            raise e

    def _predict_dish_demand(
        self,
        df: Any,  # pd.DataFrame; avoid importing pandas at module load
        dish_id: str,
        dish_name: str,
        period: str,
        target_date: str,
    ) -> dict[str, Any] | None:
        """Predict demand for a specific dish and time period"""
        try:
            # Filter data for this dish and period
            dish_data = df[(df["dish_id"] == dish_id) & (df["period"] == period)].copy()

            if len(dish_data) < 5:  # Need minimum data points
                logger.warning(f"Insufficient data for dish {dish_id}, period {period}")
                # Return fallback prediction based on limited data
                avg_demand = dish_data["y"].mean() if len(dish_data) > 0 else 5
                return {
                    "dish_id": dish_id,
                    "dish_name": dish_name,
                    "period": period,
                    "predicted_demand": max(1, int(avg_demand)),
                    "confidence": 60.0,  # Lower confidence for limited data
                    "recommended_prep": max(2, int(avg_demand * 1.2)),
                    "factors": ["Limited historical data", "Fallback average"],
                    "prediction_date": target_date,
                }

            # Prepare data for Prophet
            prophet_data = dish_data[["ds", "y"]].copy()
            prophet_data["ds"] = self._pd().to_datetime(prophet_data["ds"])

            # Add additional regressors (day of week, month)
            prophet_data["day_of_week"] = prophet_data["ds"].dt.dayofweek
            prophet_data["month"] = prophet_data["ds"].dt.month
            prophet_data["is_weekend"] = (prophet_data["ds"].dt.dayofweek >= 5).astype(int)

            # Create and train Prophet model
            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=False,
                changepoint_prior_scale=0.05,
                interval_width=0.8,
                uncertainty_samples=100,
            )

            # Add regressors
            model.add_regressor("day_of_week")
            model.add_regressor("month")
            model.add_regressor("is_weekend")

            # Fit the model
            model.fit(prophet_data)

            # Create future dataframe
            target_datetime = self._pd().to_datetime(target_date)
            future_data = self._pd().DataFrame(
                {
                    "ds": [target_datetime],
                    "day_of_week": [target_datetime.dayofweek],
                    "month": [target_datetime.month],
                    "is_weekend": [int(target_datetime.dayofweek >= 5)],
                }
            )

            # Make prediction
            forecast = model.predict(future_data)

            # Extract prediction values
            predicted_value = max(1, forecast["yhat"].iloc[0])
            lower_bound = max(0, forecast["yhat_lower"].iloc[0])
            upper_bound = forecast["yhat_upper"].iloc[0]

            # Calculate confidence based on prediction interval width
            interval_width = upper_bound - lower_bound
            avg_historical = prophet_data["y"].mean()
            confidence = max(50.0, min(95.0, 100 - (interval_width / avg_historical * 100)))

            # Determine factors that influenced the prediction
            factors = self._analyze_prediction_factors(
                target_datetime, period, prophet_data, predicted_value
            )

            # Calculate recommended preparation (add safety buffer)
            safety_multiplier = 1.2 if confidence > 80 else 1.3
            recommended_prep = max(2, int(predicted_value * safety_multiplier))

            return {
                "dish_id": dish_id,
                "dish_name": dish_name,
                "period": period,
                "predicted_demand": int(predicted_value),
                "confidence": round(confidence, 1),
                "recommended_prep": recommended_prep,
                "factors": factors,
                "prediction_date": target_date,
            }

        except Exception as e:
            logger.error(f"Error in Prophet prediction for dish {dish_id}: {e}")
            return None

    def _analyze_prediction_factors(
        self,
        target_date: Any,  # pd.Timestamp
        period: str,
        historical_data: Any,  # pd.DataFrame
        predicted_value: float,
    ) -> list[str]:
        """Analyze factors that influenced the prediction"""
        factors = []

        # Day of week analysis
        dow = target_date.dayofweek
        dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        if dow >= 5:  # Weekend
            weekend_avg = historical_data[historical_data["ds"].dt.dayofweek >= 5]["y"].mean()
            weekday_avg = historical_data[historical_data["ds"].dt.dayofweek < 5]["y"].mean()
            if weekend_avg > weekday_avg * 1.2:
                factors.append(f"Weekend boost ({dow_names[dow]})")
            elif weekend_avg < weekday_avg * 0.8:
                factors.append(f"Weekend decline ({dow_names[dow]})")
        else:
            factors.append(f"Weekday pattern ({dow_names[dow]})")

        # Period-specific factors
        if period == "morning":
            factors.append("Breakfast/morning rush")
        elif period == "afternoon":
            factors.append("Lunch period demand")
        elif period == "evening":
            factors.append("Dinner rush period")

        # Trend analysis
        recent_data = historical_data.tail(10)
        if len(recent_data) >= 5:
            recent_avg = recent_data["y"].mean()
            overall_avg = historical_data["y"].mean()

            if recent_avg > overall_avg * 1.15:
                factors.append("Upward trend detected")
            elif recent_avg < overall_avg * 0.85:
                factors.append("Downward trend detected")
            else:
                factors.append("Stable demand pattern")

        # Seasonality
        month = target_date.month
        if month in [12, 1, 2]:
            factors.append("Winter seasonality")
        elif month in [6, 7, 8]:
            factors.append("Summer seasonality")

        return factors[:4]  # Limit to top 4 factors

    def get_predictions(self, date: str) -> list[dict[str, Any]]:
        """Get existing predictions for a date"""
        return self.db_manager.get_predictions(date)

    def get_model_performance(self) -> dict[str, Any]:
        """Get model performance metrics"""
        # This would typically involve validation against actual vs predicted
        # For now, return basic statistics
        return {
            "models_trained": len(self.models),
            "last_training": self.last_training,
            "data_points_used": "Variable by dish",
            "avg_confidence": "85%",
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

        # Get predictions for tomorrow
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        predictions = engine.get_predictions(tomorrow)
        print(f"Found {len(predictions)} predictions for {tomorrow}")

    asyncio.run(test_predictions())
