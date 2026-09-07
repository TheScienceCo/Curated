"""§5 - detect the information a recruiter did not give you.

Ordered by the spec's priority list. Each detected gap carries the question
to ask, which the response generator then assembles into one message rather
than a scattergun list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.enums import ClearanceLevel, PolygraphType, RemoteStatus


@dataclass
class MissingField:
    field: str
    label: str
    #: 1 = ask first. Follows the §5 priority ordering.
    priority: int
    question: str
    #: Why this matters, shown in the UI next to the field.
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "label": self.label,
            "priority": self.priority,
            "question": self.question,
            "rationale": self.rationale,
        }


def detect_missing_information(job) -> list[MissingField]:
    """Return the missing fields, most important first."""
    missing: list[MissingField] = []

    # 1. Compensation
    if job.salary_min is None and job.salary_max is None:
        missing.append(
            MissingField(
                field="compensation",
                label="Compensation range",
                priority=1,
                question="the base salary range for the role",
                rationale="Without a range you cannot tell whether the role clears your floor.",
            )
        )

    # 2. Weekly hours / schedule
    if job.hours is None:
        missing.append(
            MissingField(
                field="hours",
                label="Expected weekly hours / schedule",
                priority=2,
                question="the expected weekly hours and work schedule",
                rationale="Two roles at the same salary can differ by 20 hours a week.",
            )
        )

    # 3. Remote / hybrid / onsite
    if (job.remote_status or RemoteStatus.UNSPECIFIED.value) == RemoteStatus.UNSPECIFIED.value:
        missing.append(
            MissingField(
                field="remote_status",
                label="Remote / hybrid / onsite",
                priority=3,
                question="whether the role is remote, hybrid, or on-site",
                rationale="Determines whether the job is viable from where you live.",
            )
        )

    # 4. Location
    if not job.location and (job.remote_status or "") != RemoteStatus.REMOTE.value:
        missing.append(
            MissingField(
                field="location",
                label="Location",
                priority=4,
                question="the work location",
                rationale="Needed to assess commute, relocation and cost of living.",
            )
        )

    # 5. Travel
    if job.travel is None:
        missing.append(
            MissingField(
                field="travel",
                label="Travel expectations",
                priority=5,
                question="expected travel",
                rationale="Travel percentage materially changes the lifestyle calculus.",
            )
        )

    # 6/7. Clearance and polygraph
    clearance = job.security_clearance or ClearanceLevel.UNSPECIFIED.value
    polygraph = job.polygraph_requirement or PolygraphType.UNKNOWN.value

    if clearance == ClearanceLevel.UNSPECIFIED.value:
        missing.append(
            MissingField(
                field="security_clearance",
                label="Clearance requirement",
                priority=6,
                question="whether the position requires a security clearance, and at what level",
                rationale="Determines eligibility and how long onboarding takes.",
            )
        )

    if polygraph == PolygraphType.UNSPECIFIED_POLYGRAPH.value:
        missing.append(
            MissingField(
                field="polygraph_requirement",
                label="Specific polygraph type",
                priority=7,
                question=(
                    "which polygraph is required - counterintelligence (CI) scope, or full "
                    "scope / expanded scope"
                ),
                rationale=(
                    "A CI polygraph and a full scope polygraph are different requirements with "
                    "very different timelines. Never assume they are interchangeable."
                ),
            )
        )
    elif polygraph == PolygraphType.UNKNOWN.value and clearance in (
        ClearanceLevel.TS_SCI.value,
        ClearanceLevel.TOP_SECRET.value,
    ):
        missing.append(
            MissingField(
                field="polygraph_requirement",
                label="Polygraph requirement",
                priority=7,
                question="whether a polygraph is required and, if so, which scope",
                rationale=(
                    "Cleared roles frequently add a polygraph requirement that is not in the "
                    "initial pitch."
                ),
            )
        )

    # 8. Equity
    if job.equity is None:
        missing.append(
            MissingField(
                field="equity",
                label="Equity",
                priority=8,
                question="whether equity is part of the package",
                rationale="Equity is often the largest component of total value at a startup.",
            )
        )
    elif job.equity and job.equity_percent_min is None:
        missing.append(
            MissingField(
                field="equity_percent",
                label="Equity percentage",
                priority=8,
                question=(
                    "the equity grant size (percentage or share count, plus current valuation)"
                ),
                rationale="'Equity included' is not a number. Without one it cannot be valued.",
            )
        )

    # 9. Bonus / commission
    if job.bonus is None and job.commission_ote is None:
        missing.append(
            MissingField(
                field="bonus",
                label="Bonus / commission",
                priority=9,
                question="any bonus or commission structure",
                rationale="Variable compensation can be a large share of total cash.",
            )
        )

    # 10. Interview process - never extracted, always worth asking.
    missing.append(
        MissingField(
            field="interview_process",
            label="Interview process",
            priority=10,
            question="what the interview process looks like and the expected timeline",
            rationale="Tells you how much of your time this opportunity will consume.",
        )
    )

    missing.sort(key=lambda m: m.priority)
    return missing


#: Fields above this priority are considered blocking: it is not reasonable to
#: schedule a call without them.
BLOCKING_PRIORITY = 5


def blocking_missing_fields(missing: list[MissingField]) -> list[MissingField]:
    return [m for m in missing if m.priority <= BLOCKING_PRIORITY]


__all__ = [
    "detect_missing_information",
    "MissingField",
    "blocking_missing_fields",
    "BLOCKING_PRIORITY",
]
