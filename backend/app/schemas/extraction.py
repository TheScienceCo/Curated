"""The strict structured schema produced by the extraction pipeline.

This is the contract between "unstructured text" and "everything else". Both
the rule-based extractor and the LLM extractor must produce one of these, and
scoring only ever reads from here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import (
    ClearanceLevel,
    CompanyStage,
    Confidence,
    EmploymentType,
    JobFamily,
    PolygraphType,
    RemoteStatus,
    SourceType,
)


class CompensationExtract(BaseModel):
    salary_min: int | None = None
    salary_max: int | None = None
    salary_currency: str = "USD"
    bonus: str | None = None
    commission_ote: int | None = None
    equity: bool | None = None
    equity_percent_min: float | None = None
    equity_percent_max: float | None = None
    equity_notes: str | None = None

    @property
    def specified(self) -> bool:
        return self.salary_min is not None or self.salary_max is not None


class LifestyleExtract(BaseModel):
    remote_status: RemoteStatus = RemoteStatus.UNSPECIFIED
    location: str | None = None
    relocation_required: bool | None = None
    travel_percent: int | None = Field(default=None, ge=0, le=100)
    weekly_hours: int | None = Field(default=None, ge=1, le=120)
    on_call: bool | None = None
    nights_weekends: bool | None = None
    shift_work: bool | None = None


class RequirementsExtract(BaseModel):
    #: Canonical skill slugs (see app.services.skills).
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    #: Requirement phrases that did not map to the ontology, kept verbatim so
    #: nothing is silently dropped.
    unmapped_requirements: list[str] = Field(default_factory=list)
    required_years_experience: float | None = None
    preferred_years_experience: float | None = None
    education_requirements: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    citizenship_requirement: str | None = None
    security_clearance: ClearanceLevel = ClearanceLevel.UNSPECIFIED
    polygraph_requirement: PolygraphType = PolygraphType.UNKNOWN
    management_responsibility: bool | None = None


class CharacteristicsExtract(BaseModel):
    company_stage: CompanyStage | None = None
    estimated_company_size: str | None = None
    industry: str | None = None
    customer_type: str | None = None
    government_or_commercial: str | None = None
    revenue_responsibility: bool | None = None
    customer_facing_intensity: str | None = None  # low | medium | high
    technical_depth: str | None = None
    research_intensity: str | None = None
    ownership_level: str | None = None  # low | medium | high
    job_family: JobFamily = JobFamily.OTHER


class ExtractionResult(BaseModel):
    """Everything the pipeline knows about one opportunity."""

    model_config = ConfigDict(use_enum_values=False)

    company: str | None = None
    title: str | None = None
    employment_type: EmploymentType = EmploymentType.UNSPECIFIED
    recruiter_name: str | None = None
    recruiter_contact: str | None = None
    source_type: SourceType = SourceType.MANUAL
    source_url: str | None = None
    job_description: str | None = None

    compensation: CompensationExtract = Field(default_factory=CompensationExtract)
    lifestyle: LifestyleExtract = Field(default_factory=LifestyleExtract)
    requirements: RequirementsExtract = Field(default_factory=RequirementsExtract)
    characteristics: CharacteristicsExtract = Field(default_factory=CharacteristicsExtract)

    #: field name -> Confidence. Fields absent from the map were not extracted.
    confidence: dict[str, Confidence] = Field(default_factory=dict)
    #: "rules", "llm" or "llm+rules".
    extraction_method: str = "rules"
    #: Anything the extractor wants the user to know (parse warnings etc).
    notes: list[str] = Field(default_factory=list)

    @field_validator("company", "title", "recruiter_name", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


__all__ = [
    "ExtractionResult",
    "CompensationExtract",
    "LifestyleExtract",
    "RequirementsExtract",
    "CharacteristicsExtract",
]
