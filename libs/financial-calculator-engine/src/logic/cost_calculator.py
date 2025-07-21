from typing import Protocol, Optional
from decimal import Decimal

from src.core.models.transaction import Transaction
from src.core.enums.transaction_type import TransactionType
from src.logic.disposition_engine import DispositionEngine
from src.logic.error_reporter import ErrorReporter

class TransactionCostStrategy(Protocol):
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None: ...

class BuyStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.gross_cost = Decimal(str(transaction.gross_transaction_amount))
        
        # This is the corrected logic:
        total_fees = transaction.fees.total_fees if transaction.fees else Decimal(0)
        
        accrued_interest = Decimal(str(transaction.accrued_interest)) if transaction.accrued_interest is not None else Decimal(0)
        transaction.net_cost = transaction.gross_cost + total_fees + accrued_interest

        if transaction.quantity > Decimal(0):
            calculated_average_price = transaction.net_cost / transaction.quantity
            if transaction.average_price is None:
                transaction.average_price = calculated_average_price
            try:
                disposition_engine.add_buy_lot(transaction)
            except ValueError as e:
                error_reporter.add_error(transaction.transaction_id, str(e))
        else:
            transaction.average_price = Decimal(0)

class SellStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        sell_quantity = Decimal(str(transaction.quantity))
        gross_sell_proceeds = Decimal(str(transaction.gross_transaction_amount))

        # This is the corrected logic:
        sell_fees = transaction.fees.total_fees if transaction.fees else Decimal(0)
        net_sell_proceeds = gross_sell_proceeds - sell_fees

        total_matched_cost, consumed_quantity, error_reason = disposition_engine.consume_sell_quantity(transaction)
        
        if error_reason:
            error_reporter.add_error(transaction.transaction_id, error_reason)
            return

        if consumed_quantity > Decimal(0):
            transaction.realized_gain_loss = net_sell_proceeds - total_matched_cost
            transaction.gross_cost = -total_matched_cost
            transaction.net_cost = -total_matched_cost
        
        if sell_quantity > Decimal(0):
            transaction.average_price = gross_sell_proceeds / sell_quantity
        else:
            transaction.average_price = Decimal(0)

class DefaultStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.gross_cost = Decimal(str(transaction.gross_transaction_amount))
        if transaction.net_transaction_amount is not None:
            transaction.net_cost = Decimal(str(transaction.net_transaction_amount))
        else:
            transaction.net_cost = transaction.gross_cost
        transaction.realized_gain_loss = None
        transaction.average_price = None

class CostCalculator:
    def __init__(self, disposition_engine: DispositionEngine, error_reporter: ErrorReporter):
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
        try:
            transaction_type_enum = TransactionType(transaction.transaction_type)
        except ValueError:
            self._error_reporter.add_error(transaction.transaction_id, f"Unknown transaction type '{transaction.transaction_type}'.")
            return
        strategy = self._strategies.get(transaction_type_enum, self._default_strategy)
        strategy.calculate_costs(transaction, self._disposition_engine, self._error_reporter)