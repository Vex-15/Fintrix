"""
Forward Cash Forecaster — Predict expected settlement inflows for 7–14 days.

Uses:
  - Historical settlement data grouped by day-of-week
  - Weighted moving average with exponential decay
  - Pending captured-but-unsettled transactions as known future inflows
  - Day-of-week seasonality adjustment

No external ML libraries required.
"""

from datetime import datetime, timedelta, date
from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models import Settlement, Transaction


async def forecast_inflows(
    db: AsyncSession,
    days_ahead: int = 14,
    lookback_days: int = 60,
    merchant_id: str | None = None,
) -> dict:
    """
    Generate a forward cash forecast for the next `days_ahead` days.

    Returns:
        {
            "forecast_days": int,
            "lookback_days": int,
            "daily_forecast": [
                {
                    "date": "2026-09-04",
                    "day_of_week": "Thursday",
                    "predicted_amount_paise": int,
                    "predicted_amount_rupees": float,
                    "low_paise": int,
                    "high_paise": int,
                    "pending_settlements_paise": int,
                    "confidence": float,
                }
            ],
            "summary": {
                "total_predicted_paise": int,
                "total_predicted_rupees": float,
                "total_pending_paise": int,
                "avg_daily_paise": int,
                "historical_avg_daily_paise": int,
            }
        }
    """
    now = datetime.utcnow()
    cutoff = now - timedelta(days=lookback_days)

    # --- Fetch historical settlements ---
    query = select(Settlement).where(
        Settlement.status == "processed",
        Settlement.created_at >= cutoff,
    )
    if merchant_id:
        query = query.where(Settlement.merchant_id == merchant_id)

    result = await db.execute(query)
    settlements = result.scalars().all()

    # --- Group by date and day-of-week ---
    daily_amounts: dict[date, int] = defaultdict(int)
    dow_amounts: dict[int, list[int]] = defaultdict(list)  # 0=Mon, 6=Sun

    for s in settlements:
        if s.created_at:
            d = s.created_at.date()
            daily_amounts[d] += s.amount
            dow_amounts[d.weekday()].append(s.amount)

    # Fill missing dates with 0
    all_dates = []
    current = cutoff.date()
    today = now.date()
    while current <= today:
        all_dates.append(current)
        if current not in daily_amounts:
            daily_amounts[current] = 0
            dow_amounts[current.weekday()].append(0)
        current += timedelta(days=1)

    # --- Compute day-of-week averages ---
    dow_avg: dict[int, float] = {}
    for dow in range(7):
        values = dow_amounts.get(dow, [0])
        if values:
            dow_avg[dow] = sum(values) / len(values)
        else:
            dow_avg[dow] = 0

    # --- Compute exponentially weighted moving average ---
    sorted_dates = sorted(daily_amounts.keys())
    if sorted_dates:
        alpha = 0.15  # Smoothing factor (higher = more weight on recent)
        ewma = daily_amounts[sorted_dates[0]]
        ewma_variance = 0.0

        for d in sorted_dates[1:]:
            value = daily_amounts[d]
            ewma = alpha * value + (1 - alpha) * ewma
            ewma_variance = alpha * (value - ewma) ** 2 + (1 - alpha) * ewma_variance
    else:
        ewma = 0
        ewma_variance = 0

    ewma_std = ewma_variance ** 0.5

    # --- Fetch pending (captured but unsettled) transactions ---
    pending_query = select(
        func.sum(Transaction.amount),
        func.count(Transaction.id),
    ).where(
        Transaction.type == "payment",
        Transaction.status == "captured",
        Transaction.settlement_id.is_(None),
    )
    if merchant_id:
        pending_query = pending_query.where(Transaction.merchant_id == merchant_id)

    pending_result = await db.execute(pending_query)
    pending_row = pending_result.one()
    total_pending_amount = pending_row[0] or 0
    pending_count = pending_row[1] or 0

    # Distribute pending amount over next 3 days (typical settlement cycle)
    pending_per_day = total_pending_amount // min(3, max(1, days_ahead))

    # --- Generate forecast ---
    historical_avg = sum(daily_amounts.values()) / max(len(daily_amounts), 1)
    daily_forecast = []
    total_predicted = 0

    for i in range(1, days_ahead + 1):
        forecast_date = today + timedelta(days=i)
        dow = forecast_date.weekday()
        day_name = forecast_date.strftime("%A")

        # Blend EWMA trend with day-of-week seasonality
        dow_factor = dow_avg.get(dow, 0)
        overall_avg = sum(dow_avg.values()) / 7 if sum(dow_avg.values()) > 0 else 1
        seasonality_ratio = dow_factor / overall_avg if overall_avg > 0 else 1.0

        predicted = int(ewma * seasonality_ratio)

        # Add pending settlements for first 3 days
        pending_component = pending_per_day if i <= 3 else 0

        # Confidence decays with distance
        confidence = max(0.3, min(0.95, 0.95 - (i - 1) * 0.04))

        # Confidence interval (±1.5 std dev, widening with time)
        spread = int(ewma_std * 1.5 * (1 + (i - 1) * 0.1))
        low = max(0, predicted - spread)
        high = predicted + spread

        entry = {
            "date": forecast_date.isoformat(),
            "day_of_week": day_name,
            "predicted_amount_paise": predicted + pending_component,
            "predicted_amount_rupees": round((predicted + pending_component) / 100, 2),
            "low_paise": max(0, low + pending_component),
            "high_paise": high + pending_component,
            "pending_settlements_paise": pending_component,
            "confidence": round(confidence, 2),
        }
        daily_forecast.append(entry)
        total_predicted += predicted + pending_component

    return {
        "forecast_days": days_ahead,
        "lookback_days": lookback_days,
        "daily_forecast": daily_forecast,
        "summary": {
            "total_predicted_paise": total_predicted,
            "total_predicted_rupees": round(total_predicted / 100, 2),
            "total_pending_paise": total_pending_amount,
            "total_pending_rupees": round(total_pending_amount / 100, 2),
            "pending_transaction_count": pending_count,
            "avg_daily_predicted_paise": total_predicted // max(days_ahead, 1),
            "historical_avg_daily_paise": int(historical_avg),
            "historical_avg_daily_rupees": round(historical_avg / 100, 2),
            "trend_direction": "up" if ewma > historical_avg else "down" if ewma < historical_avg * 0.9 else "stable",
        },
    }
