"""Candidate profile endpoints (§17)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.errors import NotFoundError, ValidationError
from app.db.models import CandidateProfile
from app.schemas.api import (
    CandidateProfileCreate,
    CandidateProfileRead,
    CandidateProfileUpdate,
)
from app.services.analysis import get_active_candidate
from app.services.scoring import ScoringConfig

router = APIRouter(prefix="/api/profile", tags=["profile"])


@router.post("", response_model=CandidateProfileRead, status_code=201)
def create_profile(
    payload: CandidateProfileCreate, db: Session = Depends(db_session)
) -> CandidateProfile:
    """Create a candidate profile."""
    _validate_scoring_config(payload.scoring_config)
    profile = CandidateProfile(**_dump(payload))
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("", response_model=CandidateProfileRead)
def read_profile(
    candidate_id: str | None = Query(default=None), db: Session = Depends(db_session)
) -> CandidateProfile:
    """Read the active profile (or a specific one by id)."""
    return get_active_candidate(db, candidate_id)


@router.get("/all", response_model=list[CandidateProfileRead])
def list_profiles(db: Session = Depends(db_session)) -> list[CandidateProfile]:
    return db.query(CandidateProfile).order_by(CandidateProfile.created_at).all()


@router.patch("", response_model=CandidateProfileRead)
def update_profile(
    payload: CandidateProfileUpdate,
    candidate_id: str | None = Query(default=None),
    db: Session = Depends(db_session),
) -> CandidateProfile:
    """Partial update. Only the fields present in the body change."""
    profile = get_active_candidate(db, candidate_id)
    updates = payload.model_dump(exclude_unset=True)
    if "scoring_config" in updates:
        _validate_scoring_config(updates["scoring_config"])
    for key, value in updates.items():
        setattr(profile, key, _coerce(value))
    db.commit()
    db.refresh(profile)
    return profile


@router.patch("/{profile_id}", response_model=CandidateProfileRead)
def update_profile_by_id(
    profile_id: str, payload: CandidateProfileUpdate, db: Session = Depends(db_session)
) -> CandidateProfile:
    profile = db.get(CandidateProfile, profile_id)
    if profile is None:
        raise NotFoundError(f"Candidate profile {profile_id} not found")
    updates = payload.model_dump(exclude_unset=True)
    if "scoring_config" in updates:
        _validate_scoring_config(updates["scoring_config"])
    for key, value in updates.items():
        setattr(profile, key, _coerce(value))
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/scoring-config/defaults")
def scoring_defaults() -> dict:
    """The default weights and bands, so the UI can show what it is overriding."""
    return ScoringConfig().model_dump()


def _dump(payload: CandidateProfileCreate) -> dict:
    return {k: _coerce(v) for k, v in payload.model_dump().items()}


def _coerce(value):
    """Unwrap enums so the ORM stores plain strings."""
    return value.value if hasattr(value, "value") else value


def _validate_scoring_config(raw: dict | None) -> None:
    """Reject a malformed override at the boundary rather than silently
    falling back to defaults later."""
    if not raw:
        return
    try:
        ScoringConfig.model_validate(raw)
    except Exception as exc:  # noqa: BLE001 - surfaced to the caller as a 422
        raise ValidationError(f"Invalid scoring_config: {exc}") from exc
