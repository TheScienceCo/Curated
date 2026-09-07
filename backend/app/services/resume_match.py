"""§11 - pick the right résumé variant for a job and suggest honest tailoring.

Ranking is deterministic (skill overlap + job-family targeting + keyword
coverage). Optional embeddings add a semantic tiebreaker when enabled, but the
system works fully without them.

The hard rule: **never invent experience.** Every "highlight" is something the
résumé already contains, and every "missing keyword" is reported as a gap to
address truthfully, not as text to paste in.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from app.services.skills import extract_skills_from_text, label_for


@dataclass
class ResumeMatch:
    resume_id: str
    title: str
    score: float
    matched_skills: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)
    highlight: list[str] = field(default_factory=list)
    de_emphasize: list[str] = field(default_factory=list)
    rationale: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "resume_id": self.resume_id,
            "title": self.title,
            "score": round(self.score, 1),
            "matched_skills": [label_for(s) for s in self.matched_skills],
            "missing_keywords": [label_for(s) for s in self.missing_keywords],
            "highlight": self.highlight,
            "de_emphasize": self.de_emphasize,
            "rationale": self.rationale,
            "summary": self.summary,
        }


#: Categories that are usually noise on a technical résumé for a given family.
#: Used only to suggest *de-emphasis*, never deletion of true content.
_OFF_TOPIC_CATEGORIES: dict[str, tuple[str, ...]] = {
    "software": ("science",),
    "ai": ("science",),
    "cyber": ("science", "business"),
    "intelligence": ("science",),
    "science": ("cyber",),
    "business": ("science",),
}


def resume_skills(resume) -> list[str]:
    """Skills a résumé demonstrably contains, mined from its own text."""
    stored = list(resume.skills or [])
    if stored:
        return stored
    return extract_skills_from_text(resume.raw_text or "")


def cosine_similarity(a: list[float] | None, b: list[float] | None) -> float | None:
    """Cosine similarity, or None when either vector is missing."""
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return None
    return dot / (norm_a * norm_b)


def score_resume_for_job(resume, job, job_embedding: list[float] | None = None) -> ResumeMatch:
    """Score one résumé variant against one job."""
    required = list(job.required_skills or [])
    preferred = list(job.preferred_skills or [])
    have = set(resume_skills(resume))
    rationale: list[str] = []

    # --- required skill coverage (the dominant term) ----------------------
    if required:
        matched = [s for s in required if s in have]
        coverage = len(matched) / len(required)
        score = coverage * 60
        rationale.append(
            f"Covers {len(matched)}/{len(required)} required skills "
            f"({', '.join(label_for(s) for s in matched[:5]) or 'none'})."
        )
    else:
        matched = []
        score = 30.0
        rationale.append("Job lists no required skills; ranked on family targeting and overlap.")

    # --- preferred skills --------------------------------------------------
    matched_preferred = [s for s in preferred if s in have]
    if preferred:
        score += (len(matched_preferred) / len(preferred)) * 15
        if matched_preferred:
            rationale.append(
                f"Also covers preferred: {', '.join(label_for(s) for s in matched_preferred[:4])}."
            )

    # --- explicit family targeting ----------------------------------------
    targets = {str(t) for t in (resume.target_families or [])}
    if job.job_family and job.job_family in targets:
        score += 20
        rationale.append(
            f"This variant is explicitly written for {job.job_family.replace('_', ' ')} roles."
        )
    elif targets:
        rationale.append(
            "Written for a different job family ("
            + ", ".join(sorted(t.replace("_", " ") for t in targets)[:3])
            + ")."
        )

    # --- title keyword overlap ---------------------------------------------
    title_words = {w for w in re.findall(r"[a-z]+", (job.title or "").lower()) if len(w) > 3}
    resume_words = set(re.findall(r"[a-z]+", (resume.raw_text or "").lower()))
    if title_words:
        overlap = len(title_words & resume_words) / len(title_words)
        score += overlap * 5
        if overlap >= 0.6:
            rationale.append("Résumé language already mirrors the job title.")

    # --- optional semantic similarity --------------------------------------
    similarity = cosine_similarity(resume.embedding, job_embedding)
    if similarity is not None:
        score += similarity * 10
        rationale.append(f"Semantic similarity to the job description: {similarity:.2f}.")

    if not resume.active:
        score -= 15
        rationale.append("Marked inactive in your profile.")

    missing = [s for s in required if s not in have]

    return ResumeMatch(
        resume_id=resume.id,
        title=resume.title,
        score=max(0.0, min(100.0, score)),
        matched_skills=matched,
        missing_keywords=missing,
        highlight=_build_highlights(resume, job, matched + matched_preferred),
        de_emphasize=_build_de_emphasis(resume, job, have),
        rationale=rationale,
        summary=_build_summary(resume, job, matched, missing),
    )


def _build_highlights(resume, job, matched: list[str]) -> list[str]:
    """What to lead with. Only ever things the résumé already contains."""
    from app.core.enums import ClearanceLevel, PolygraphType
    from app.services.clearance import clearance_label, polygraph_label, polygraph_satisfies

    highlights = [label_for(s) for s in matched[:8]]

    # Credentials are usually the strongest card on a cleared role.
    text = (resume.raw_text or "").lower()
    if job.security_clearance not in (
        None,
        ClearanceLevel.UNSPECIFIED.value,
        ClearanceLevel.NONE.value,
    ):
        for token, level in (
            ("ts/sci", ClearanceLevel.TS_SCI),
            ("top secret", ClearanceLevel.TOP_SECRET),
        ):
            if token in text:
                highlights.insert(0, clearance_label(level.value))
                break
        if "poly" in text:
            held = PolygraphType.FULL_SCOPE if "full scope" in text else PolygraphType.CI
            # Only lead with a polygraph that actually meets the requirement.
            # Highlighting a CI poly on a full-scope role invites a rejection.
            required = job.polygraph_requirement or PolygraphType.UNKNOWN.value
            if polygraph_satisfies(held.value, required):
                highlights.insert(1, polygraph_label(held.value))

    if job.customer_facing_intensity in ("high", "medium") and "customer" in text:
        highlights.append("Customer-facing delivery experience")
    if job.ownership_level == "high" and re.search(r"\bown(?:ed|ership)\b|\bled\b|\bbuilt\b", text):
        highlights.append("End-to-end ownership examples")

    seen: set[str] = set()
    return [h for h in highlights if not (h in seen or seen.add(h))][:8]


def _build_de_emphasis(resume, job, have: set[str]) -> list[str]:
    """What to shorten. Suggestions only - the content stays true, just smaller."""
    from app.services.skills import get_skill

    family_category = _family_category(job.job_family)
    off_topic = _OFF_TOPIC_CATEGORIES.get(family_category, ())
    required = set(job.required_skills or []) | set(job.preferred_skills or [])

    suggestions: list[str] = []
    for slug in sorted(have):
        skill = get_skill(slug)
        if skill and skill.category in off_topic and slug not in required:
            suggestions.append(skill.label)

    text = (resume.raw_text or "").lower()
    if family_category in ("software", "ai") and re.search(
        r"\bcoursework\b|\bgpa\b|\brelevant courses\b", text
    ):
        suggestions.append("Coursework and GPA details")
    if family_category != "intelligence" and "analyst" in text and "intelligence" in text:
        suggestions.append("Generic analyst duties (keep the quantified outcomes)")

    seen: set[str] = set()
    return [s for s in suggestions if not (s in seen or seen.add(s))][:6]


def _family_category(job_family: str | None) -> str:
    family = job_family or ""
    if any(k in family for k in ("cyber", "malware", "vulnerability", "threat", "security")):
        return "cyber"
    if any(k in family for k in ("intelligence", "seta")):
        return "intelligence"
    if any(k in family for k in ("biology", "scientific", "biosecurity")):
        return "science"
    if any(
        k in family
        for k in ("account", "business_development", "solutions_engineer", "gtm", "strategy")
    ):
        return "business"
    if any(k in family for k in ("ai", "ml", "research")):
        return "ai"
    return "software"


def _build_summary(resume, job, matched: list[str], missing: list[str]) -> str:
    """A short, honest positioning line for this résumé against this job."""
    parts = [f"{resume.title} is the closest variant for {job.title or 'this role'}"]
    if matched:
        parts.append("leading with " + ", ".join(label_for(s) for s in matched[:4]))
    if missing:
        parts.append(
            "and addressing "
            + ", ".join(label_for(s) for s in missing[:3])
            + " directly rather than implying experience you do not have"
        )
    return ". ".join([" ".join(parts[:2]), *parts[2:]]).strip() + "."


def rank_resumes(resumes: list, job, job_embedding: list[float] | None = None) -> list[ResumeMatch]:
    """Rank every résumé variant, best first."""
    matches = [score_resume_for_job(r, job, job_embedding) for r in resumes]
    matches.sort(key=lambda m: -m.score)
    return matches


__all__ = [
    "rank_resumes",
    "score_resume_for_job",
    "ResumeMatch",
    "resume_skills",
    "cosine_similarity",
]
