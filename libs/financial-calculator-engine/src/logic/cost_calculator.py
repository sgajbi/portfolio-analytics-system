# libs/financial-calculator-engine/src/logic/cost_calculator.py
from typing import Protocol, Optional
from decimal import Decimal

from core.models.transaction import Transaction
from core.enums.transaction_type import TransactionType
from logic.disposition_engine import DispositionEngine
from logic.error_reporter import ErrorReporter

class TransactionCostStrategy(Protocol):
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None: ...

class BuyStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        total_fees_local = transaction.fees.total_fees if transaction.fees else Decimal(0)
        accrued_interest_local = transaction.accrued_interest or Decimal(0)
        
        # Calculate cost in the original trade currency
        transaction.net_cost_local = transaction.gross_transaction_amount + total_fees_local + accrued_interest_local
        
        # Convert to portfolio base currency
        fx_rate = transaction.transaction_fx_rate or Decimal(1.0)
        transaction.net_cost = transaction.net_cost_local * fx_rate
        
        if transaction.quantity > Decimal(0):
            try:
                disposition_engine.add_buy_lot(transaction)
            except ValueError as e:
                error_reporter.add_error(transaction.transaction_id, str(e))

class SellStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        sell_quantity = transaction.quantity
        sell_fees_local = transaction.fees.total_fees if transaction.fees else Decimal(0)

        # Calculate proceeds in local currency
        net_sell_proceeds_local = transaction.gross_transaction_amount - sell_fees_local

        # Convert proceeds to portfolio base currency
        fx_rate = transaction.transaction_fx_rate or Decimal(1.0)
        net_sell_proceeds_base = net_sell_proceeds_local * fx_rate
        
        # Consume from lots to get cost of goods sold (COGS) in both currencies
        cogs_base, cogs_local, consumed_quantity, error_reason = disposition_engine.consume_sell_quantity(transaction)
        
        if error_reason:
            error_reporter.add_error(transaction.transaction_id, error_reason)
            return

        if consumed_quantity > Decimal(0):
            # Calculate PnL in both currencies
            transaction.realized_gain_loss_local = net_sell_proceeds_local - cogs_local
            transaction.realized_gain_loss = net_sell_proceeds_base - cogs_base
            
            # Net cost for a sell is the negative COGS in the base currency
            transaction.net_cost = -cogs_base
            transaction.net_cost_local = -cogs_local

class DefaultStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.net_cost_local = transaction.gross_transaction_amount
        fx_rate = transaction.transaction_fx_rate or Decimal(1.0)
        transaction.net_cost = transaction.net_cost_local * fx_rate

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
        if transaction.trade_currency != transaction.portfolio_base_currency and not transaction.transaction_fx_rate:
            self._error_reporter.add_error(transaction.transaction_id, f"Missing FX rate for cross-currency transaction from {transaction.trade_currency} to {transaction.portfolio_base_currency}.")
            return

        try:
            transaction_type_enum = TransactionType(transaction.transaction_type)
        except ValueError:
            self._error_reporter.add_error(transaction.transaction_id, f"Unknown transaction type '{transaction.transaction_type}'.")
            return
            
        strategy = self._strategies.get(transaction_type_enum, self._default_strategy)
        strategy.calculate_costs(transaction, self._disposition_engine, self._error_reporter)