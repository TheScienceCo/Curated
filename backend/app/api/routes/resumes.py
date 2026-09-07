"""Résumé variant endpoints (§17)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import db_session
from app.core.errors import NotFoundError
from app.db.models import ResumeDocument
from app.schemas.api import ResumeCreate, ResumeRead
from app.services import embeddings as embeddings_service
from app.services.analysis import get_active_candidate
from app.services.skills import extract_skills_from_text

router = APIRouter(prefix="/api/resumes", tags=["resumes"])


def _to_read(resume: ResumeDocument) -> ResumeRead:
    payload = ResumeRead.model_validate(resume)
    payload.has_embedding = bool(resume.embedding)
    return payload


@router.post("", response_model=ResumeRead, status_code=201)
def create_resume(payload: ResumeCreate, db: Session = Depends(db_session)) -> ResumeRead:
    """Store a résumé variant.

    Skills are mined from the text at write time so matching stays fast and
    the stored list is inspectable - you can see exactly what the system
    thinks this résumé proves.
    """
    candidate = get_active_candidate(db, payload.candidate_id)
    resume = ResumeDocument(
        candidate_id=candidate.id,
        title=payload.title,
        raw_text=payload.raw_text,
        parsed_sections=payload.parsed_sections,
        target_families=payload.target_families,
        active=payload.active,
        skills=extract_skills_from_text(payload.raw_text),
        embedding=embeddings_service.embed_text(payload.raw_text),
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    return _to_read(resume)


@router.get("", response_model=list[ResumeRead])
def list_resumes(
    candidate_id: str | None = Query(default=None),
    db: Session = Depends(db_session),
) -> list[ResumeRead]:
    candidate = get_active_candidate(db, candidate_id)
    resumes = (
        db.query(ResumeDocument)
        .filter(ResumeDocument.candidate_id == candidate.id)
        .order_by(ResumeDocument.created_at)
        .all()
    )
    return [_to_read(r) for r in resumes]


@router.get("/{resume_id}", response_model=ResumeRead)
def read_resume(resume_id: str, db: Session = Depends(db_session)) -> ResumeRead:
    resume = db.get(ResumeDocument, resume_id)
    if resume is None:
        raise NotFoundError(f"Résumé {resume_id} not found")
    return _to_read(resume)


@router.delete("/{resume_id}", status_code=204, response_class=Response)
def delete_resume(resume_id: str, db: Session = Depends(db_session)) -> Response:
    resume = db.get(ResumeDocument, resume_id)
    if resume is None:
        raise NotFoundError(f"Résumé {resume_id} not found")
    db.delete(resume)
    db.commit()
    return Response(status_code=204)
