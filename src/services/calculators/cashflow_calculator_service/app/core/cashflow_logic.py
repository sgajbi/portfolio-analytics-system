import logging
from decimal import Decimal
from typing import Optional
from portfolio_common.database_models import Cashflow
from portfolio_common.events import TransactionEvent
from .cashflow_config import CashflowRule, CashflowCalculationType, CashflowClassification

logger = logging.getLogger(__name__)

class CashflowLogic:
    """
    A stateless calculator that generates a Cashflow object from a transaction
    based on a given business rule.
    """
    @staticmethod
    def calculate(
        transaction: TransactionEvent,
        rule: CashflowRule,
        epoch: Optional[int] = 0
    ) -> Cashflow:
        """
        Applies the calculation rule to a transaction to generate a cashflow.
        """
        amount = Decimal(0)

        # Determine the amount based on the calculation type
        if rule.calc_type == CashflowCalculationType.GROSS:
            amount = transaction.gross_transaction_amount
        elif rule.calc_type == CashflowCalculationType.NET:
            # For NET, we adjust the gross amount by the fee.
            if transaction.transaction_type in ["BUY", "FEE"]:
                amount = transaction.gross_transaction_amount + (transaction.trade_fee or 0)
            else: # SELL, DIVIDEND, INTEREST, etc.
                amount = transaction.gross_transaction_amount - (transaction.trade_fee or 0)
        elif rule.calc_type == CashflowCalculationType.MVT:
            amount = transaction.quantity * transaction.price

        # --- FIX: Corrected Sign Logic ---
        # Convention: Inflows to the portfolio are positive, outflows are negative.
        positive_classifications = [
            CashflowClassification.INVESTMENT_INFLOW,  # From a SELL
            CashflowClassification.INCOME,             # From DIVIDEND, INTEREST
            CashflowClassification.CASHFLOW_IN         # From DEPOSIT
        ]

        if rule.classification in positive_classifications:
            amount = abs(amount)
        elif rule.classification == CashflowClassification.TRANSFER:
            if transaction.transaction_type == "TRANSFER_IN":
                amount = abs(amount)
            else: # TRANSFER_OUT
                amount = -abs(amount)
        else:
            # All other classifications are outflows (INVESTMENT_OUTFLOW, EXPENSE, CASHFLOW_OUT)
            amount = -abs(amount)
        # --- END FIX ---

        # Create the Cashflow database object
        cashflow = Cashflow(
            transaction_id=transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id,
            cashflow_date=transaction.transaction_date.date(),
            amount=amount,
            currency=transaction.currency,
            classification=rule.classification.value,
            timing=rule.timing.value,
            calculation_type=rule.calc_type.value,
            is_position_flow=rule.is_position_flow,
            is_portfolio_flow=rule.is_portfolio_flow,
            epoch=epoch or 0
        )

        logger.info(f"Calculated cashflow for txn {transaction.transaction_id}: Amount={amount}, Class='{rule.classification.value}'")
        return cashflow