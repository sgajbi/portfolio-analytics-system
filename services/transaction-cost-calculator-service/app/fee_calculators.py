from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any

class TieredPercentageFeeCalculator:
    """
    Calculates transaction fees based on a tiered percentage structure.
    Tiers are defined as a list of (upper_bound, percentage_rate) tuples.
    The upper_bound is exclusive. For example, (1000, 0.01) means 1% for amounts up to 1000.
    The last tier's upper_bound should be None to indicate no upper limit.
    """
    def __init__(self, tiers: list[tuple[float | None, float]]):
        # Sort tiers by upper_bound to ensure correct processing
        # and convert to Decimal immediately for precision
        self.tiers = sorted([(Decimal(str(ub)) if ub is not None else None, Decimal(str(rate)))
                             for ub, rate in tiers],
                            key=lambda x: x[0] if x[0] is not None else Decimal('inf'))

    def calculate_fee(self, amount: float) -> float:
        """
        Calculates the fee for a given amount based on the tiered structure.
        """
        decimal_amount = Decimal(str(amount))
        total_fee = Decimal('0')
        previous_upper_bound = Decimal('0')

        for upper_bound, rate in self.tiers:
            if decimal_amount <= previous_upper_bound:
                # Amount is entirely covered by previous tiers, no more fee
                break

            if upper_bound is None:
                # This is the last tier, applies to all remaining amount
                tier_amount = decimal_amount - previous_upper_bound
            else:
                # Current tier's ceiling
                current_tier_ceiling = upper_bound

                # Amount within current tier's bucket
                tier_amount = min(decimal_amount, current_tier_ceiling) - previous_upper_bound
                if tier_amount < 0:
                    tier_amount = Decimal('0')

            # Calculate fee for the portion within this tier
            fee_in_tier = (tier_amount * rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            total_fee += fee_in_tier

            if upper_bound is not None:
                previous_upper_bound = upper_bound
            else:
                # If it's the last tier (upper_bound is None), we've processed all amount
                break
        
        return float(total_fee)