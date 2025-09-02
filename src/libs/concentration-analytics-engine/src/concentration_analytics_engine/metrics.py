# src/libs/concentration-analytics-engine/src/concentration_analytics_engine/metrics.py
from typing import List, Dict, Any
import pandas as pd
import numpy as np

def calculate_bulk_concentration(positions: pd.DataFrame, top_n: List[int]) -> Dict[str, Any]:
    """
    Calculates bulk concentration metrics for a portfolio.
    
    Metrics include:
    - Herfindahl-Hirschman Index (HHI)
    - Weight of the single largest position
    - Cumulative weight of the Top-N largest positions
    """
    if positions.empty:
        return {
            "hhi": 0.0,
            "single_position_weight": 0.0,
            "top_n_weights": {str(n): 0.0 for n in top_n}
        }

    total_market_value = positions["market_value"].sum()
    if total_market_value == 0:
        return {
            "hhi": 0.0,
            "single_position_weight": 0.0,
            "top_n_weights": {str(n): 0.0 for n in top_n}
        }

    positions["weight"] = positions["market_value"] / total_market_value
    
    # HHI Calculation
    hhi = np.sum(positions["weight"] ** 2)
    
    # Sort positions by weight to find top contributors
    sorted_positions = positions.sort_values(by="weight", ascending=False)
    
    # Single largest position
    single_position_weight = sorted_positions["weight"].iloc[0] if not sorted_positions.empty else 0.0
    
    # Top-N positions
    top_n_weights = {}
    for n in top_n:
        top_n_weights[str(n)] = sorted_positions["weight"].head(n).sum()
        
    return {
        "hhi": float(hhi),
        "single_position_weight": float(single_position_weight),
        "top_n_weights": {k: float(v) for k, v in top_n_weights.items()}
    }

def calculate_issuer_concentration(positions: pd.DataFrame, top_n: int) -> List[Dict[str, Any]]:
    """
    Calculates issuer concentration, grouping positions by their issuer ID.
    """
    if positions.empty:
        return []

    total_market_value = positions["market_value"].sum()
    if total_market_value == 0:
        return []

    positions["issuer_id"] = positions["issuer_id"].fillna("UNCLASSIFIED")
    positions["issuer_name"] = positions.apply(
        lambda row: "Unclassified" if row["issuer_id"] == "UNCLASSIFIED" else row["issuer_name"],
        axis=1
    )

    issuer_groups = positions.groupby("issuer_id").agg(
        exposure=("market_value", "sum"),
        issuer_name=("issuer_name", "first")
    ).reset_index()
    
    issuer_groups["issuer_name"] = issuer_groups["issuer_name"].fillna(issuer_groups["issuer_id"])

    issuer_groups["weight"] = issuer_groups["exposure"] / total_market_value
    
    top_exposures = issuer_groups.sort_values(by="weight", ascending=False).head(top_n)
    
    return [
        {
            "issuer_id": row["issuer_id"],
            "issuer_name": row["issuer_name"],
            "exposure": float(row["exposure"]),
            "weight": float(row["weight"])
        }
        for _, row in top_exposures.iterrows()
    ]