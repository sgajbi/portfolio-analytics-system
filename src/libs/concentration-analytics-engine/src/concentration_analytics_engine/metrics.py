# src/libs/concentration-analytics-engine/src/concentration_analytics_engine/metrics.py
from typing import List, Dict
import pandas as pd
from decimal import Decimal

from .exceptions import InsufficientDataError


def calculate_bulk_concentration(
    positions_df: pd.DataFrame, top_n_config: List[int]
) -> Dict:
    """
    Calculates bulk concentration metrics from a DataFrame of positions.

    Args:
        positions_df: DataFrame with at least a 'market_value' column.
        top_n_config: A list of integers for Top-N calculations (e.g., [5, 10]).

    Returns:
        A dictionary containing the single-position weight, Top-N weights, and HHI.
    """
    if positions_df.empty:
        raise InsufficientDataError(
            "Cannot calculate concentration on an empty DataFrame."
        )

    total_market_value = positions_df["market_value"].sum()

    if total_market_value == Decimal("0"):
        return {
            "single_position_weight": 0.0,
            "top_n_weights": {str(n): 0.0 for n in top_n_config},
            "hhi": 0.0,
        }

    positions_df["weight"] = positions_df["market_value"] / total_market_value
    sorted_weights = positions_df["weight"].sort_values(ascending=False)

    single_position_weight = float(sorted_weights.iloc[0])
    hhi = float((sorted_weights**2).sum())

    top_n_weights = {
        str(n): float(sorted_weights.head(n).sum()) for n in top_n_config
    }

    return {
        "single_position_weight": single_position_weight,
        "top_n_weights": top_n_weights,
        "hhi": hhi,
    }