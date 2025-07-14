from fastapi import FastAPI, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import date, datetime
from typing import Optional

from common.db import get_db_session
from common.models import Transaction, TransactionCost
from app.repository import TransactionRepository
from app.fee_calculators import TieredPercentageFeeCalculator
from app.schemas import TransactionRead, TransactionCostRead, TransactionCostCreate # Import necessary schemas

app = FastAPI()

# Initialize the fee calculator with predefined tiers
# Example tiers:
# 0.5% for amounts up to 1000
# 0.3% for amounts up to 5000 (i.e., between 1000 and 5000)
# 0.1% for amounts above 5000
FEE_TIERS = [
    (1000, 0.005),
    (5000, 0.003),
    (None, 0.001)
]
fee_calculator = TieredPercentageFeeCalculator(tiers=FEE_TIERS)

@app.get("/")
def read_root():
    return {"message": "Transaction Cost Calculator Service is running"}

@app.get("/calculate-transaction-cost/{transaction_id}", response_model=TransactionCostRead)
async def calculate_and_store_transaction_cost(
    transaction_id: str,
    portfolio_id: str = Query(..., description="Portfolio ID"),
    instrument_id: str = Query(..., description="Instrument ID"),
    transaction_date: date = Query(..., description="Transaction date (YYYY-MM-DD)"),
    db: Session = Depends(get_db_session)
):
    """
    Calculates and stores the transaction cost for a given transaction.
    Fetches the transaction details from the database using its composite primary key.
    """
    repo = TransactionRepository(db)

    # 1. Fetch the transaction from the database
    transaction = repo.get_transaction_by_pk(
        transaction_id=transaction_id,
        portfolio_id=portfolio_id,
        instrument_id=instrument_id,
        transaction_date=transaction_date
    )

    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found with the provided details."
        )

    # 2. Calculate the transaction cost
    # The 'amount' for fee calculation is quantity * price
    amount_for_fee_calculation = transaction.quantity * transaction.price
    cost_amount = fee_calculator.calculate_fee(amount_for_fee_calculation)

    # 3. Create a TransactionCost ORM object
    new_transaction_cost_orm = TransactionCost(
        transaction_id=transaction.transaction_id,
        portfolio_id=transaction.portfolio_id,
        instrument_id=transaction.instrument_id,
        transaction_date=transaction.transaction_date,
        cost_amount=cost_amount,
        cost_currency=transaction.currency, # Assuming cost currency is same as transaction currency
        calculation_date=datetime.now() # Use current time for calculation_date
    )

    # 4. Save the TransactionCost to the database
    try:
        created_cost = repo.create_transaction_cost(new_transaction_cost_orm)
        return TransactionCostRead.model_validate(created_cost) # Use model_validate for Pydantic v2
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save transaction cost: {e}"
        )