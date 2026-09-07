"""User decision endpoints - the feedback loop described in §16.

Every decision is stored verbatim. v1 does no learning from it beyond making
it visible; the point is to accumulate honest labels before building anything
that consumes them.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.enums import DecisionType, MessageStatus
from app.core.errors import NotFoundError
from app.db.models import JobOpportunity, RecruiterMessage, UserDecision
from app.schemas.api import DecisionCreate, DecisionRead, MessageStatusUpdate, RecruiterMessageRead

router = APIRouter(prefix="/api", tags=["decisions"])

#: Decisions that imply the drafted reply was actually used.
_RESPONDED = {DecisionType.RESPONDED, DecisionType.INTERVIEWED, DecisionType.OFFER}


@router.post("/decisions", response_model=DecisionRead, status_code=201)
def create_decision(payload: DecisionCreate, db: Session = Depends(db_session)) -> UserDecision:
    """Record pursue / maybe / reject / responded / offer / accepted etc."""
    job = db.get(JobOpportunity, payload.opportunity_id)
    if job is None:
        raise NotFoundError(f"Opportunity {payload.opportunity_id} not found")

    decision = UserDecision(
        opportunity_id=payload.opportunity_id,
        decision=payload.decision.value,
        reason=payload.reason,
        edited_response=payload.edited_response,
        outcome_metadata=payload.outcome_metadata,
    )
    db.add(decision)

    # Keep the message status in step with the decision, so the dashboard
    # never shows "draft awaiting approval" for a job you already rejected.
    message = (
        db.query(RecruiterMessage)
        .filter(RecruiterMessage.opportunity_id == payload.opportunity_id)
        .order_by(desc(RecruiterMessage.timestamp))
        .first()
    )
    if message is not None:
        if payload.edited_response:
            message.approved_response = payload.edited_response
            message.status = MessageStatus.EDITED.value
        elif payload.decision in _RESPONDED:
            message.status = MessageStatus.APPROVED.value
        elif payload.decision is DecisionType.REJECT:
            message.status = MessageStatus.REJECTED.value
        elif payload.decision is DecisionType.IGNORE:
            message.status = MessageStatus.IGNORED.value

    db.commit()
    db.refresh(decision)
    return decision


@router.get("/decisions", response_model=list[DecisionRead])
def list_decisions(
    opportunity_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(db_session),
) -> list[UserDecision]:
    query = db.query(UserDecision)
    if opportunity_id:
        query = query.filter(UserDecision.opportunity_id == opportunity_id)
    return query.order_by(desc(UserDecision.timestamp)).limit(limit).all()


@router.patch("/messages/{message_id}", response_model=RecruiterMessageRead)
def update_message(
    message_id: str, payload: MessageStatusUpdate, db: Session = Depends(db_session)
) -> RecruiterMessage:
    """Approve, edit or reject a drafted reply.

    Approval is explicitly a human action: nothing is ever sent by the system,
    so 'approved' means 'the user is happy to send this themselves'.
    """
    message = db.get(RecruiterMessage, message_id)
    if message is None:
        raise NotFoundError(f"Message {message_id} not found")
    message.status = payload.status.value
    if payload.approved_response is not None:
        message.approved_response = payload.approved_response
        if (
            payload.status is MessageStatus.APPROVED
            and payload.approved_response != message.response_draft
        ):
            message.status = MessageStatus.EDITED.value
    db.commit()
    db.refresh(message)
    return message


@router.get("/messages/{message_id}", response_model=RecruiterMessageRead)
def read_message(message_id: str, db: Session = Depends(db_session)) -> RecruiterMessage:
    message = db.get(RecruiterMessage, message_id)
    if message is None:
        raise NotFoundError(f"Message {message_id} not found")
    return message
