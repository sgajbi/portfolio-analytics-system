# src/logic/cost_calculator.py

from typing import Protocol, Optional
from decimal import Decimal

from app.cost_engine.core.models.transaction import Transaction # Adjusted import
from app.cost_engine.core.enums.transaction_type import TransactionType # Adjusted import
from app.cost_engine.logic.disposition_engine import DispositionEngine # Adjusted import
from app.cost_engine.logic.error_reporter import ErrorReporter # Adjusted import

# Precision set in main.py

class TransactionCostStrategy(Protocol):
    """
    Protocol (interface) for transaction cost calculation strategies.
    Each strategy implements specific logic for a transaction type.
    """
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter
    ) -> None:
        """
        Calculates the net cost, gross cost, and realized gain/loss for a transaction.
        Modifies the transaction object in place.
        """
        ...


class BuyStrategy:
    """Strategy for calculating costs for BUY transactions."""
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter
    ) -> None:
        """
        Calculates Net Cost, Gross Cost, and Average Price for a BUY transaction.
        Adds the lot to the disposition engine if quantity > 0.
        """
        transaction.gross_cost = Decimal(str(transaction.gross_transaction_amount))

        total_fees = transaction.fees.total_fees if transaction.fees else Decimal(0)
        accrued_interest = Decimal(str(transaction.accrued_interest)) if transaction.accrued_interest is not None else Decimal(0)

        transaction.net_cost = transaction.gross_cost + total_fees + accrued_interest

        if transaction.quantity > Decimal(0):
            calculated_average_price = transaction.net_cost / transaction.quantity
            if transaction.average_price is None:
                transaction.average_price = calculated_average_price
        else:
            transaction.average_price = Decimal(0)

        if transaction.quantity > Decimal(0):
            try:
                disposition_engine.add_buy_lot(transaction)
            except ValueError as e:
                error_reporter.add_error(transaction.transaction_id, str(e))


class SellStrategy:
    """Strategy for calculating costs and realized gain/loss for SELL transactions."""
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter
    ) -> None:
        """
        Calculates Realized Gain/Loss for a SELL transaction using the disposition engine.
        Selling fees are subtracted from proceeds for gain/loss calculation.
        Gross/Net cost are set to the negative of the matched cost basis.
        """
        sell_quantity = Decimal(str(transaction.quantity))
        gross_sell_proceeds = Decimal(str(transaction.gross_transaction_amount))

        # NEW: Subtract fees from proceeds for realized gain/loss calculation
        sell_fees = transaction.fees.total_fees if transaction.fees else Decimal(0)
        net_sell_proceeds = gross_sell_proceeds - sell_fees # Proceeds net of selling fees

        total_matched_cost, consumed_quantity, error_reason = \
            disposition_engine.consume_sell_quantity(transaction)

        if error_reason:
            error_reporter.add_error(transaction.transaction_id, error_reason)
            transaction.realized_gain_loss = None
            transaction.gross_cost = Decimal(0)
            transaction.net_cost = Decimal(0)
            return

        if consumed_quantity > Decimal(0):
            # Realized Gain/Loss = Net Sell Proceeds - Matched Buy Cost
            transaction.realized_gain_loss = net_sell_proceeds - total_matched_cost
            transaction.gross_cost = -total_matched_cost
            transaction.net_cost = -total_matched_cost
        else:
            transaction.realized_gain_loss = Decimal(0)
            transaction.gross_cost = Decimal(0)
            transaction.net_cost = Decimal(0)

        if sell_quantity > Decimal(0):
            transaction.average_price = gross_sell_proceeds / sell_quantity # Average price might still be gross
        else:
            transaction.average_price = Decimal(0)


class DefaultStrategy:
    """
    Default strategy for other transaction types (Interest, Dividend, Deposit, Withdrawal, Fee, Other).
    These typically don't involve cost basis or realized gain/loss calculations in the same way.
    """
    def calculate_costs(
        self,
        transaction: Transaction,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter
    ) -> None:
        """
        Sets gross_cost and net_cost based on transaction amounts.
        Realized gain/loss is not applicable.
        """
        transaction.gross_cost = Decimal(str(transaction.gross_transaction_amount))
        if transaction.net_transaction_amount is not None:
            transaction.net_cost = Decimal(str(transaction.net_transaction_amount))
        else:
            transaction.net_cost = transaction.gross_cost

        transaction.realized_gain_loss = None
        transaction.average_price = None


class CostCalculator:
    """
    Applies the appropriate cost calculation strategy based on transaction type.
    """

    def __init__(
        self,
        disposition_engine: DispositionEngine,
        error_reporter: ErrorReporter
    ):
        self._disposition_engine = disposition_engine
        self._error_reporter = error_reporter
        self._strategies: dict[TransactionType, TransactionCostStrategy] = {
            TransactionType.BUY: BuyStrategy(),
            TransactionType.SELL: SellStrategy(),
            TransactionType.INTEREST: DefaultStrategy(),
            TransactionType.DIVIDEND: DefaultStrategy(),
            TransactionType.DEPOSIT: DefaultStrategy(),
            TransactionType.WITHDRAWAL: DefaultStrategy(),
            TransactionType.FEE: DefaultStrategy(),
            TransactionType.OTHER: DefaultStrategy(),
        }
        self._default_strategy = DefaultStrategy()

    def calculate_transaction_costs(self, transaction: Transaction):
        """
        Delegates cost calculation to the appropriate strategy based on transaction type.
        """
        transaction_type_enum: Optional[TransactionType] = None
        try:
            transaction_type_enum = TransactionType(transaction.transaction_type)
        except ValueError:
            self._error_reporter.add_error(
                transaction.transaction_id,
                f"Unknown transaction type '{transaction.transaction_type}'. Cannot calculate costs."
            )
            return

        strategy = self._strategies.get(transaction_type_enum, self._default_strategy)
        strategy.calculate_costs(transaction, self._disposition_engine, self._error_reporter)