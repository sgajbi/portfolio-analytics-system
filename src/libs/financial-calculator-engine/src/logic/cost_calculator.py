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
        
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount + total_fees_local + accrued_interest_local
        
        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        transaction.net_cost = transaction.net_cost_local * fx_rate
        
        if transaction.quantity > Decimal(0):
            try:
                disposition_engine.add_buy_lot(transaction)
            except ValueError as e:
                error_reporter.add_error(transaction.transaction_id, str(e))

class SellStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        sell_fees_local = transaction.fees.total_fees if transaction.fees else Decimal(0)
        net_sell_proceeds_local = transaction.gross_transaction_amount - sell_fees_local
        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        net_sell_proceeds_base = net_sell_proceeds_local * fx_rate
        
        cogs_base, cogs_local, consumed_quantity, error_reason = disposition_engine.consume_sell_quantity(transaction)
        
        if error_reason:
            error_reporter.add_error(transaction.transaction_id, error_reason)
            return

        if consumed_quantity > Decimal(0):
            transaction.realized_gain_loss_local = net_sell_proceeds_local - cogs_local
            transaction.realized_gain_loss = net_sell_proceeds_base - cogs_base
            transaction.net_cost = -cogs_base
            transaction.net_cost_local = -cogs_local
            transaction.gross_cost = -cogs_base

class CashInflowStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount
        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        transaction.net_cost = transaction.net_cost_local * fx_rate
        cash_buy_equivalent = transaction.model_copy()
        cash_buy_equivalent.quantity = transaction.gross_transaction_amount
        
        
        disposition_engine.add_buy_lot(cash_buy_equivalent)

class SecurityInflowStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount
        
        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        transaction.net_cost = transaction.net_cost_local * fx_rate
        
        if transaction.quantity > Decimal(0):
            try:
                disposition_engine.add_buy_lot(transaction)
            except ValueError as e:
                error_reporter.add_error(transaction.transaction_id, str(e))

class SecurityOutflowStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        """Consumes a cost lot for a security transfer out, but does not realize a P&L."""
        cogs_base, cogs_local, consumed_quantity, error_reason = disposition_engine.consume_sell_quantity(transaction)
        
        if error_reason:
            error_reporter.add_error(transaction.transaction_id, error_reason)
            return

        if consumed_quantity > Decimal(0):
            transaction.net_cost = -cogs_base
            transaction.net_cost_local = -cogs_local
            transaction.gross_cost = -cogs_base
            transaction.realized_gain_loss = None
            transaction.realized_gain_loss_local = None

class IncomeStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.net_cost = Decimal(0)
        transaction.net_cost_local = Decimal(0)
        transaction.gross_cost = Decimal(0)
        transaction.realized_gain_loss = None
        transaction.realized_gain_loss_local = None

class DefaultStrategy:
    def calculate_costs(self, transaction: Transaction, disposition_engine: DispositionEngine, error_reporter: ErrorReporter) -> None:
        transaction.gross_cost = transaction.gross_transaction_amount
        transaction.net_cost_local = transaction.gross_transaction_amount
        fx_rate = transaction.transaction_fx_rate or Decimal(1)
        transaction.net_cost = transaction.net_cost_local * fx_rate

class CostCalculator:
    def __init__(self, disposition_engine: DispositionEngine, error_reporter: ErrorReporter):
        self._disposition_engine = disposition_engine
        self._error_reporter = error_reporter
        self._strategies: dict[TransactionType, TransactionCostStrategy] = {
            TransactionType.BUY: BuyStrategy(),
            TransactionType.SELL: SellStrategy(),
            TransactionType.INTEREST: IncomeStrategy(),
            TransactionType.DIVIDEND: IncomeStrategy(),
            TransactionType.DEPOSIT: CashInflowStrategy(),
            TransactionType.TRANSFER_IN: SecurityInflowStrategy(),
            TransactionType.TRANSFER_OUT: SecurityOutflowStrategy(),
            TransactionType.WITHDRAWAL: SecurityOutflowStrategy(),
            TransactionType.FEE: DefaultStrategy(),
            TransactionType.OTHER: DefaultStrategy(),
        }
        self._default_strategy = DefaultStrategy()

    def _validate_fx(self, t: Transaction) -> bool:
        if t.trade_currency == t.portfolio_base_currency:
            if not t.transaction_fx_rate:
                t.transaction_fx_rate = Decimal(1)
            return True
        if t.transaction_fx_rate is None or t.transaction_fx_rate <= 0:
            self._error_reporter.add_error(
                t.transaction_id,
                f"Missing/invalid FX rate for cross-currency transaction from {t.trade_currency} to {t.portfolio_base_currency}."
            )
            return False
        return True

    def calculate_transaction_costs(self, transaction: Transaction):
        if not self._validate_fx(transaction):
            return
        try:
            if transaction.transaction_type not in TransactionType.list():
                self._error_reporter.add_error(transaction.transaction_id, f"Unknown transaction type '{transaction.transaction_type}'.")
                return
            transaction_type_enum = TransactionType(transaction.transaction_type)
        except ValueError:
            self._error_reporter.add_error(transaction.transaction_id, f"Unknown transaction type '{transaction.transaction_type}'.")
            return
        strategy = self._strategies.get(transaction_type_enum, self._default_strategy)
        strategy.calculate_costs(transaction, self._disposition_engine, self._error_reporter)