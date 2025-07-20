# src/logic/parser.py

import logging
from typing import Any, List # Changed Tuple to List as only one list is returned
from pydantic import ValidationError, TypeAdapter
from decimal import Decimal # Needed for Decimal(0) in stub creation

from app.cost_engine.core.models.transaction import Transaction # Adjusted import
from app.cost_engine.core.models.response import ErroredTransaction # Adjusted import
from app.cost_engine.core.enums.transaction_type import TransactionType # Adjusted import
from app.cost_engine.logic.error_reporter import ErrorReporter # Adjusted import

logger = logging.getLogger(__name__)

class TransactionParser:
    """
    Parses raw transaction dictionaries into validated Transaction objects.
    Handles data type conversions and initial validation using Pydantic.
    All parsing errors are reported to the shared ErrorReporter.
    """
    def __init__(self, error_reporter: ErrorReporter):
        self._single_transaction_adapter = TypeAdapter(Transaction)
        self._error_reporter = error_reporter

    def parse_transactions(
        self, raw_transactions_data: list[dict[str, Any]]
    ) -> list[Transaction]: # MODIFIED: Returns only list[Transaction]
        """
        Parses a list of raw transaction dictionaries into validated Transaction objects.
        If a transaction fails parsing, it's still returned in the list but marked with error_reason,
        and the error is reported to the central ErrorReporter.
        """
        logger.info(f"TransactionParser: Type of raw_transactions_data received: {type(raw_transactions_data)}")
        if raw_transactions_data:
            logger.info(f"TransactionParser: Type of first item in raw_transactions_data (before loop): {type(raw_transactions_data[0])}")
        else:
            logger.info("TransactionParser: raw_transactions_data is empty or None.")

        parsed_transactions: list[Transaction] = []
        # REMOVED: errored_transactions: list[ErroredTransaction] = []

        for raw_txn_data in raw_transactions_data:
            logger.info(f"TransactionParser: Type of raw_txn_data in loop (before .get()): {type(raw_txn_data)}")

            transaction_id = raw_txn_data.get("transaction_id", "UNKNOWN_ID_BEFORE_PARSE")

            # Attempt to create a Transaction object even for errored ones,
            # so we can set its error_reason.
            # A robust way: first attempt full validation, if fails, create minimal Transaction for internal tracking.

            try:
                # Attempt full validation
                validated_txn = self._single_transaction_adapter.validate_python(raw_txn_data)
                parsed_transactions.append(validated_txn)
            except ValidationError as e:
                error_messages = "; ".join([f"{err['loc'][0]}: {err['msg']}" for err in e.errors()])
                error_reason = f"Validation error: {error_messages}"

                # Create a Transaction object from raw data, setting default values for missing required fields
                # if possible, to allow setting error_reason for internal filtering.
                # If transaction_id is missing/invalid, create a stub.
                temp_txn = None
                try:
                    # Try to create a Transaction model using only the fields that are present in raw_txn_data
                    # and are also defined in the Transaction model. This allows for partial population.
                    # Pydantic's 'model_validate' can be used, and if strict, it will raise errors.
                    # For this purpose, we need to construct something that matches Transaction's structure.
                    # Simplest is to try direct construction with defaults or known types, then assign error.
                    # Alternatively, iterate fields and assign what's available to a new Transaction instance.

                    # For a robust stub, extract known fields or rely on Pydantic's BaseModel creation
                    # with 'extra='ignore'' if there are non-model fields in raw_txn_data.
                    # Or, construct a minimal valid Transaction to avoid further errors if raw_txn_data is bad.
                    temp_txn = Transaction(
                        transaction_id=raw_txn_data.get("transaction_id", "UNKNOWN_ID_AFTER_PARSE_FAIL"),
                        portfolio_id=raw_txn_data.get("portfolio_id", "UNKNOWN"),
                        instrument_id=raw_txn_data.get("instrument_id", "UNKNOWN"),
                        security_id=raw_txn_data.get("security_id", "UNKNOWN"),
                        transaction_type=raw_txn_data.get("transaction_type", "UNKNOWN"),
                        transaction_date=raw_txn_data.get("transaction_date", "1970-01-01"), # Use a default date
                        settlement_date=raw_txn_data.get("settlement_date", "1970-01-01"), # Use a default date
                        quantity=raw_txn_data.get("quantity", Decimal(0)),
                        gross_transaction_amount=raw_txn_data.get("gross_transaction_amount", Decimal(0)),
                        trade_currency=raw_txn_data.get("trade_currency", "UNKNOWN")
                    )
                except Exception as ex_inner:
                    logger.warning(f"Failed to construct even a partial Transaction stub for ID {transaction_id} during validation error: {ex_inner}. Creating a minimal stub.")
                    # Fallback for truly malformed inputs
                    temp_txn = Transaction(
                        transaction_id=transaction_id,
                        portfolio_id="MALFORMED", instrument_id="MALFORMED", security_id="MALFORMED",
                        transaction_type="MALFORMED", transaction_date="1970-01-01", settlement_date="1970-01-01",
                        quantity=Decimal(0), gross_transaction_amount=Decimal(0), trade_currency="MALFORMED"
                    )

                temp_txn.error_reason = error_reason # Mark for internal filtering by TransactionProcessor
                parsed_transactions.append(temp_txn)
                self._error_reporter.add_error(transaction_id, error_reason) # Report to central reporter
            except Exception as e:
                error_reason = f"Unexpected parsing error: {type(e).__name__}: {str(e)}"
                temp_txn = None
                try:
                     temp_txn = Transaction(
                        transaction_id=raw_txn_data.get("transaction_id", "UNKNOWN_ID_AFTER_PARSE_FAIL"),
                        portfolio_id=raw_txn_data.get("portfolio_id", "UNKNOWN"),
                        instrument_id=raw_txn_data.get("instrument_id", "UNKNOWN"),
                        security_id=raw_txn_data.get("security_id", "UNKNOWN"),
                        transaction_type=raw_txn_data.get("transaction_type", "UNKNOWN"),
                        transaction_date=raw_txn_data.get("transaction_date", "1970-01-01"),
                        settlement_date=raw_txn_data.get("settlement_date", "1970-01-01"),
                        quantity=raw_txn_data.get("quantity", Decimal(0)),
                        gross_transaction_amount=raw_txn_data.get("gross_transaction_amount", Decimal(0)),
                        trade_currency=raw_txn_data.get("trade_currency", "UNKNOWN")
                    )
                except Exception as ex_inner:
                    logger.warning(f"Failed to construct even a partial Transaction stub for ID {transaction_id} during unexpected error: {ex_inner}. Creating a minimal stub.")
                    temp_txn = Transaction(
                        transaction_id=transaction_id,
                        portfolio_id="MALFORMED", instrument_id="MALFORMED", security_id="MALFORMED",
                        transaction_type="MALFORMED", transaction_date="1970-01-01", settlement_date="1970-01-01",
                        quantity=Decimal(0), gross_transaction_amount=Decimal(0), trade_currency="MALFORMED"
                    )

                temp_txn.error_reason = error_reason # Mark for internal filtering by TransactionProcessor
                parsed_transactions.append(temp_txn)
                self._error_reporter.add_error(transaction_id, error_reason) # Report to central reporter

        return parsed_transactions