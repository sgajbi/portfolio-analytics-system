import logging
from decimal import Decimal
from portfolio_common.database_models import Cashflow
from portfolio_common.events import TransactionEvent
from .cashflow_config import CashflowRule, CashflowCalculationType

logger = logging.getLogger(__name__)

class CashflowLogic:
    """
    A stateless calculator that generates a Cashflow object from a transaction
    based on a given business rule.
    """
    @staticmethod
    def calculate(
        transaction: TransactionEvent,
        rule: CashflowRule
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

        # FIX: Correct the sign logic for performance calculation formulas.
        # Contributions TO the portfolio (BUYs, Deposits) must be positive.
        # Withdrawals FROM the portfolio (SELLs, Fees, Dividends) must be negative.
        if rule.classification in [
            "INVESTMENT_OUTFLOW", # e.g., BUY
            "CASHFLOW_IN"         # e.g., DEPOSIT
        ]:
            amount = abs(amount)
        else: # e.g., SELL, DIVIDEND, FEE, WITHDRAWAL
            amount = -abs(amount)

        # Create the Cashflow database object
        cashflow = Cashflow(
            transaction_id=transaction.transaction_id,
            portfolio_id=transaction.portfolio_id,
            security_id=transaction.security_id if rule.level == "POSITION" else None,
            cashflow_date=transaction.transaction_date.date(),
            amount=amount,
            currency=transaction.currency,
            classification=rule.classification.value,
            timing=rule.timing.value,
            level=rule.level.value,
            calculation_type=rule.calc_type.value,
        )

        logger.info(f"Calculated cashflow for txn {transaction.transaction_id}: Amount={amount}, Class='{rule.classification.value}'")
        return cashflow