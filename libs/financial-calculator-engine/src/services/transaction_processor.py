# src/services/transaction_processor.py

import logging
from typing import Tuple, List, Any
from src.core.models.transaction import Transaction
from src.core.models.response import ErroredTransaction
from src.logic.parser import TransactionParser
from src.logic.sorter import TransactionSorter
from src.logic.disposition_engine import DispositionEngine
from src.logic.cost_calculator import CostCalculator
from src.logic.error_reporter import ErrorReporter

logger = logging.getLogger(__name__)

class TransactionProcessor:
    """
    Orchestrates the end-to-end processing of financial transactions.
    """
    def __init__(
        self,
        parser: TransactionParser,
        sorter: TransactionSorter,
        disposition_engine: DispositionEngine,
        cost_calculator: CostCalculator,
        error_reporter: ErrorReporter
    ):
        self._parser = parser
        self._sorter = sorter
        self._disposition_engine = disposition_engine
        self._cost_calculator = cost_calculator
        self._error_reporter = error_reporter

    def process_transactions(
        self,
        existing_transactions_raw: list[dict[str, Any]],
        new_transactions_raw: list[dict[str, Any]]
    ) -> Tuple[list[Transaction], list[ErroredTransaction]]:
        """
        Main method to process transactions.
        """
        self._error_reporter.clear()
        
        parsed_existing = self._parser.parse_transactions(existing_transactions_raw)
        parsed_new = self._parser.parse_transactions(new_transactions_raw)
        
        new_transaction_ids = {txn.transaction_id for txn in parsed_new}
        
        valid_existing = [txn for txn in parsed_existing if not txn.error_reason]
        valid_new = [txn for txn in parsed_new if not txn.error_reason]

        sorted_transactions = self._sorter.sort_transactions(
            existing_transactions=valid_existing,
            new_transactions=valid_new
        )
        
        self._disposition_engine.set_initial_lots(valid_existing)

        processed_transactions: list[Transaction] = []
        for transaction in sorted_transactions:
            if transaction.transaction_id in new_transaction_ids:
                try:
                    self._cost_calculator.calculate_transaction_costs(transaction)
                    if not self._error_reporter.has_errors_for(transaction.transaction_id):
                        processed_transactions.append(transaction)
                except Exception as e:
                    logger.error(f"Unexpected error for transaction {transaction.transaction_id}: {e}")
                    self._error_reporter.add_error(transaction.transaction_id, f"Unexpected error: {str(e)}")

        final_errored = self._error_reporter.get_errors()
        final_processed = [
            txn for txn in processed_transactions if not self._error_reporter.has_errors_for(txn.transaction_id)
        ]
        
        return final_processed, final_errored