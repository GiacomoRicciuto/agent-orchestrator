"""
Billing routes: balance, topup, transaction history.
"""

from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User, BillingTxn
from app.dependencies import get_current_user

router = APIRouter(prefix="/api/billing", tags=["billing"])


class BalanceResponse(BaseModel):
    credits: float
    currency: str = "EUR"


class TopupRequest(BaseModel):
    amount_eur: float  # Amount in EUR
    # In production: stripe_payment_method_id or checkout_session_id


class TopupResponse(BaseModel):
    credits_added: float
    new_balance: float
    # In production: stripe_checkout_url for redirect


class TxnResponse(BaseModel):
    id: str
    type: str
    amount: float
    credits_delta: float
    description: str | None
    created_at: str


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(user: User = Depends(get_current_user)):
    return BalanceResponse(credits=float(user.credits))


@router.post("/topup", response_model=TopupResponse)
async def topup(
    req: TopupRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Add credits to user account.

    MVP: Direct credit assignment (admin-verified payments).
    Production: Stripe Checkout → webhook confirms → credits added.
    """
    if req.amount_eur < 1.0:
        raise HTTPException(status_code=400, detail="Minimum topup is €1.00")
    if req.amount_eur > 1000.0:
        raise HTTPException(status_code=400, detail="Maximum topup is €1,000.00")

    # Calculate credits: €1 = 1 sprint (simplified for MVP)
    credits_to_add = Decimal(str(req.amount_eur))

    # TODO: In production, create Stripe Checkout session here
    # and add credits only after webhook confirmation.
    # For MVP, we add credits directly (admin manually verifies).

    user.credits += credits_to_add

    txn = BillingTxn(
        user_id=user.id,
        type="topup",
        amount=Decimal(str(req.amount_eur)),
        credits_delta=credits_to_add,
        description=f"Top-up: €{req.amount_eur:.2f} → {credits_to_add} sprints",
    )
    db.add(txn)

    return TopupResponse(
        credits_added=float(credits_to_add),
        new_balance=float(user.credits),
    )


@router.get("/transactions", response_model=list[TxnResponse])
async def list_transactions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(BillingTxn)
        .where(BillingTxn.user_id == user.id)
        .order_by(BillingTxn.created_at.desc())
        .limit(50)
    )
    txns = result.scalars().all()

    return [
        TxnResponse(
            id=str(t.id),
            type=t.type,
            amount=float(t.amount),
            credits_delta=float(t.credits_delta),
            description=t.description,
            created_at=t.created_at.isoformat(),
        )
        for t in txns
    ]
