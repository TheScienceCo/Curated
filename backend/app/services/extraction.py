"""The structured extraction pipeline.

Two extractors, one contract:

1. ``rule_extract`` - regex + ontology. Fast, free, fully deterministic,
   always runs. It is the source of truth for money, clearance, polygraph,
   hours and travel, because those have exactly one right answer and a
   hallucinated salary is worse than no salary.
2. ``llm_extract`` - optional. Better at the fuzzy fields: company name,
   seniority, customer type, ownership level, research intensity, and
   requirement phrases written in prose.

``extract`` runs both and merges them under a fixed precedence rule
(deterministic wins on the numeric/eligibility fields), then records a
per-field confidence map so the UI can show what was inferred versus read.
"""

from __future__ import annotations

import re
from typing import Any

from app.core.enums import (
    ClearanceLevel,
    CompanyStage,
    Confidence,
    JobFamily,
    PolygraphType,
    RemoteStatus,
    SourceType,
)
from app.core.logging import get_logger
from app.llm.base import LlmProvider, LlmRequest
from app.schemas.extraction import (
    CharacteristicsExtract,
    CompensationExtract,
    ExtractionResult,
    LifestyleExtract,
    RequirementsExtract,
)
from app.services import normalize as nz
from app.services.clearance import parse_clearance, parse_polygraph
from app.services.job_families import classify_job_family
from app.services.skills import extract_skills_from_text, normalize_skills

logger = get_logger(__name__)

# --------------------------------------------------------------------------
# Rule-based extraction
# --------------------------------------------------------------------------

#: Job titles are the single most useful field, and recruiters phrase the
#: introduction a handful of predictable ways. `[^\S\n]` is "whitespace but
#: not a newline", which stops a title from swallowing the next line.
_H = r"[^\S\n]"
# `(?-i:...)` keeps the leading capital significant even inside a pattern
# compiled with re.IGNORECASE - otherwise "looking for a founding engineer"
# captures the lowercase prose instead of the real title.
_TITLE_CORE = rf"(?-i:[A-Z][\w/&+\-]*(?:{_H}+[\w/&+\-]+){{0,5}})"
_TITLE_STOP = (
    r"(?=\s+(?:role|position|opening|opportunity|at|supporting|to|who|that|which|with|on|"
    r"for|and|in)\b|[.,;\n]|$)"
)

_TITLE_PATTERNS = [
    re.compile(rf"^{_H}*(?:job{_H}+)?title{_H}*[:\-]{_H}*(?P<title>[^\n]+?){_H}*$", re.I | re.M),
    re.compile(rf"^{_H}*(?:role|position){_H}*[:\-]{_H}*(?P<title>[^\n]+?){_H}*$", re.I | re.M),
    re.compile(
        rf"(?:recruiting|hiring|reaching out|reached out|looking|searching)"
        rf"{_H}+(?:for|to fill)?{_H}*(?:an?{_H}+)?(?P<title>{_TITLE_CORE}){_TITLE_STOP}",
        re.I,
    ),
    re.compile(
        rf"\b(?:opening|opportunity){_H}+for{_H}+(?:an?{_H}+)?(?P<title>{_TITLE_CORE}){_TITLE_STOP}",
        re.I,
    ),
    re.compile(
        rf"\bwe(?:'re| are){_H}+hiring{_H}+(?:an?{_H}+)?(?P<title>{_TITLE_CORE}){_TITLE_STOP}", re.I
    ),
    re.compile(rf"\b(?P<title>{_TITLE_CORE}){_H}+(?:role|position){_H}+at\b"),
    re.compile(rf"^{_H}*(?:re|subject){_H}*[:\-]{_H}*(?P<title>[^\n]+?){_H}*$", re.I | re.M),
]

#: Company names are the noisiest field here, so this stays conservative:
#: a wrong company is worse than a blank one, and the user can type it in.
_COMPANY_CORE = (
    rf"(?-i:[A-Z][\w&.\-]*(?:{_H}+(?:[A-Z][\w&.\-]*|Labs?|Systems?|Technologies|"
    rf"Bio|AI|Inc\.?|LLC)){{0,3}})"
)

_COMPANY_PATTERNS = [
    re.compile(rf"^{_H}*company{_H}*[:\-]{_H}*(?P<company>[^\n]+?){_H}*$", re.I | re.M),
    re.compile(
        rf"\b(?:here{_H}+at|I(?:'m| am){_H}+with|on{_H}+behalf{_H}+of|joining)"
        rf"{_H}+(?P<company>{_COMPANY_CORE})\b"
    ),
    re.compile(rf"\bat{_H}+(?P<company>{_COMPANY_CORE}){_H}*(?:[,.(]|{_H}where\b|{_H}we\b|\n|$)"),
    # "recruiting for a Forward Deployed Engineer at Nightingale Systems supporting..."
    # - the company follows the title, and the sentence continues afterwards.
    re.compile(
        rf"\b(?:recruiting|hiring|opening|opportunity|role|position)[^.\n]{{0,80}}?"
        rf"\bat{_H}+(?P<company>{_COMPANY_CORE})\b",
        re.I,
    ),
]

_RECRUITER_PATTERNS = [
    re.compile(
        r"^\s*(?:from|sender|recruiter)\s*[:\-]\s*(?P<name>[^<\n]+?)\s*(?:<|$)", re.I | re.M
    ),
    re.compile(
        r"\b(?:I'?m|I am|This is)\s+(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"
        r"\s*(?:,|\.|\s+(?:and|from|with|a\s+recruiter))"
    ),
    re.compile(
        r"(?:Best|Thanks|Regards|Cheers|Sincerely|Best regards)[,!]?\s*\n+\s*"
        r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\s*$",
        re.M,
    ),
]

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_URL_RE = re.compile(r"https?://[^\s<>\"')]+")

#: Titles are noisy; reject obvious false positives.
_TITLE_STOPWORDS = {"you", "your", "the", "this", "that", "our", "a", "an", "we", "i"}

_EDUCATION_RE = re.compile(
    r"\b(?:bachelor'?s?|b\.?s\.?|b\.?a\.?|master'?s?|m\.?s\.?|mba|ph\.?d\.?|doctorate|"
    r"degree\s+in|advanced\s+degree)\b[^.\n;]{0,60}",
    re.I,
)
_CERT_RE = re.compile(
    r"\b(?:security\+|sec\+|cissp|ceh|oscp|gcih|gcia|gsec|pmp|aws\s+certified|"
    r"azure\s+certified|ccna|comptia\s+\w+)\b",
    re.I,
)
_CITIZENSHIP_RE = re.compile(
    r"\b(?:u\.?s\.?\s+citizen(?:ship)?(?:\s+required)?|must\s+be\s+a\s+u\.?s\.?\s+citizen|"
    r"green\s+card|permanent\s+resident|no\s+sponsorship|sponsorship\s+(?:is\s+)?(?:not\s+)?available|"
    r"authorized\s+to\s+work)\b[^.\n]{0,40}",
    re.I,
)

_PREFERRED_CONTEXT = re.compile(
    r"\b(?:preferred|nice[\s\-]to[\s\-]have|bonus\s+points?|plus(?:es)?\b|ideally|"
    r"desired|a\s+plus|would\s+be\s+great)\b",
    re.I,
)

_STAGE_PATTERNS: list[tuple[re.Pattern[str], CompanyStage]] = [
    (re.compile(r"\bpre[\s\-]?seed\b", re.I), CompanyStage.PRE_SEED),
    (
        re.compile(r"\bseed[\s\-]stage\b|\bseed\s+round\b|\bseed[\s\-]funded\b", re.I),
        CompanyStage.SEED,
    ),
    (re.compile(r"\bseries\s+a\b", re.I), CompanyStage.SERIES_A),
    (re.compile(r"\bseries\s+b\b", re.I), CompanyStage.SERIES_B),
    (re.compile(r"\bseries\s+[cd]\b", re.I), CompanyStage.SERIES_C),
    (re.compile(r"\bgrowth[\s\-]stage\b|\bseries\s+[efg]\b", re.I), CompanyStage.GROWTH),
    (re.compile(r"\blate[\s\-]stage\b|\bpre[\s\-]ipo\b", re.I), CompanyStage.LATE_STAGE),
    (
        re.compile(r"\bpublicly\s+traded\b|\bnasdaq\b|\bnyse\b|\bfortune\s+500\b", re.I),
        CompanyStage.PUBLIC,
    ),
    (
        re.compile(r"\bfederal\s+agency\b|\bgovernment\s+agency\b|\bdirect\s+government\b", re.I),
        CompanyStage.GOVERNMENT,
    ),
    (re.compile(r"\bnon[\s\-]?profit\b|\bffrdc\b", re.I), CompanyStage.NONPROFIT),
]

_SIZE_RE = re.compile(
    r"(?:team|company|we(?:'re| are))\s+(?:of\s+)?(?:about\s+|~\s*)?(?P<n>\d{1,6})\s*(?:\+)?\s*"
    r"(?:people|employees|engineers|person)|\b(?P<n2>\d{1,4})\s*-\s*(?P<n3>\d{1,6})\s*employees\b",
    re.I,
)

_GOVERNMENT_RE = re.compile(
    r"\bnational\s+security\b|\bdefense\b|\bdod\b|\bintelligence\s+community\b|\bic\b|"
    r"\bfederal\b|\bgovernment\s+customers?\b|\bmission\s+partners?\b|\bwarfighter\b|"
    r"\bnsa\b|\bcia\b|\bdia\b|\bnro\b|\bnga\b|\bfbi\b|\bdhs\b",
    re.I,
)
_ENTERPRISE_RE = re.compile(r"\benterprise\s+customers?\b|\bfortune\s+\d+\b|\bb2b\b", re.I)
_CONSUMER_RE = re.compile(r"\bconsumer\b|\bb2c\b|\bend\s+users?\b", re.I)

_CUSTOMER_FACING_HIGH = re.compile(
    r"\bforward\s+deployed\b|\bcustomer[\s\-]facing\b|\bclient[\s\-]facing\b|\bon[\s\-]site\s+with\s+customers?\b|"
    r"\bembedded\s+with\s+(?:the\s+)?(?:customer|user|mission)\b|\bsolutions?\s+engineer\b|"
    r"\bsales\s+engineer\b|\baccount\s+executive\b",
    re.I,
)
_RESEARCH_RE = re.compile(
    r"\bpublish(?:ing|ed)?\b|\bresearch\s+(?:scientist|engineer|agenda)\b|\bnovel\s+methods?\b|"
    r"\bstate[\s\-]of[\s\-]the[\s\-]art\b|\bpapers?\b|\bneurips\b|\bicml\b|\biclr\b",
    re.I,
)
_OWNERSHIP_HIGH = re.compile(
    r"\bown(?:ership)?\s+(?:of\s+)?(?:the\s+)?(?:product|roadmap|end[\s\-]to[\s\-]end|outcome)\b|"
    r"\bzero\s+to\s+one\b|\b0\s*->?\s*1\b|\bambiguity\b|\bautonomy\b|\bfirst\s+(?:engineer|hire)\b|"
    r"\bfounding\b|\bgreenfield\b|\bwear\s+many\s+hats\b|\bhigh[\s\-]agency\b",
    re.I,
)
_REVENUE_RE = re.compile(
    r"\bquota\b|\brevenue\s+(?:target|responsibility|ownership)\b|\bbook\s+of\s+business\b|"
    r"\bclose\s+deals?\b|\bpipeline\b|\bcommission\b|\bote\b",
    re.I,
)
_MANAGEMENT_RE = re.compile(
    r"\bmanage\s+a\s+team\b|\bdirect\s+reports?\b|\bpeople\s+management\b|\bhiring\s+and\s+"
    r"(?:developing|mentoring)\b|\bteam\s+of\s+\d+\s+engineers?\b",
    re.I,
)

_CHANNEL_HINTS: list[tuple[re.Pattern[str], SourceType]] = [
    (re.compile(r"\blinkedin\b", re.I), SourceType.LINKEDIN_MESSAGE),
    (re.compile(r"^\s*(?:from|to|subject|sent)\s*:", re.I | re.M), SourceType.RECRUITER_EMAIL),
    (
        re.compile(r"\bapply\s+(?:now|here)\b|\bjob\s+description\b|\bresponsibilities\s*:", re.I),
        SourceType.JOB_POSTING,
    ),
    (re.compile(r"\breferred\s+by\b|\breferral\b", re.I), SourceType.REFERRAL),
]


#: Leading noise that recruiters put in subject lines.
_SUBJECT_NOISE = re.compile(
    r"^(?:re|fwd?|fw)\s*:\s*|^(?:new\s+)?(?:role|opportunity|opening|job)\s*[:\-]\s*", re.I
)


def _first_match(patterns: list[re.Pattern[str]], text: str, group: str) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match:
            value = (match.group(group) or "").strip(" .,:;-\t")
            if value and value.lower() not in _TITLE_STOPWORDS and len(value) < 120:
                return value
    return None


def _clean_title(title: str | None) -> str | None:
    """Trim a captured title down to the role itself.

    Subject lines routinely read "Founding Engineer at Halcyon Bio"; the
    company belongs in its own field, not glued to the title.
    """
    if not title:
        return None
    cleaned = _SUBJECT_NOISE.sub("", title).strip()
    cleaned = re.split(r"\s+\bat\b\s+|\s+[-|]\s+|\s*\(", cleaned)[0].strip(" .,:;-")
    if not cleaned or cleaned.lower() in _TITLE_STOPWORDS or len(cleaned) > 90:
        return None
    return cleaned


def _split_required_preferred(text: str) -> tuple[list[str], list[str]]:
    """Partition mined skills into required vs preferred by local context.

    Sentence-level: a skill mentioned in a "nice to have" sentence is
    preferred, everything else is required.
    """
    required: list[str] = []
    preferred: list[str] = []
    for sentence in re.split(r"(?<=[.;:\n])\s+", text):
        target = preferred if _PREFERRED_CONTEXT.search(sentence) else required
        for slug in extract_skills_from_text(sentence):
            if slug not in required and slug not in preferred:
                target.append(slug)
    return required, preferred


def _detect_company_size(text: str) -> str | None:
    match = _SIZE_RE.search(text)
    if not match:
        return None
    if match.group("n"):
        return f"~{match.group('n')} employees"
    if match.group("n2") and match.group("n3"):
        return f"{match.group('n2')}-{match.group('n3')} employees"
    return None


def _intensity(pattern: re.Pattern[str], text: str, *, high_hits: int = 2) -> str | None:
    hits = len(pattern.findall(text))
    if hits == 0:
        return None
    return "high" if hits >= high_hits else "medium"


def rule_extract(
    text: str,
    *,
    source_url: str | None = None,
    known_company: str | None = None,
    known_title: str | None = None,
) -> ExtractionResult:
    """Deterministic extraction. Never raises; unknown fields stay None."""
    text = text or ""
    conf: dict[str, Confidence] = {}

    # --- identity ---------------------------------------------------------
    title = known_title or _clean_title(_first_match(_TITLE_PATTERNS, text, "title"))
    company = known_company or _first_match(_COMPANY_PATTERNS, text, "company")
    if company:
        company = company.strip(" .,:;-\n")
    recruiter = _first_match(_RECRUITER_PATTERNS, text, "name")
    email_match = _EMAIL_RE.search(text)
    url_match = _URL_RE.search(text)

    if title:
        conf["title"] = Confidence.HIGH if known_title else Confidence.MEDIUM
    if company:
        conf["company"] = Confidence.HIGH if known_company else Confidence.LOW

    source_type = SourceType.MANUAL
    for pattern, hint in _CHANNEL_HINTS:
        if pattern.search(text):
            source_type = hint
            break

    # --- compensation -----------------------------------------------------
    salary = nz.parse_salary(text)
    equity = nz.parse_equity(text)
    comp = CompensationExtract(
        salary_min=salary.minimum,
        salary_max=salary.maximum,
        salary_currency=salary.currency,
        equity=equity.offered,
        equity_percent_min=equity.percent_min,
        equity_percent_max=equity.percent_max,
        equity_notes=equity.notes,
        commission_ote=nz.parse_ote(text),
    )
    bonus_match = re.search(r"[^.\n]{0,60}\bbonus\b[^.\n]{0,60}", text, re.I)
    if bonus_match:
        comp.bonus = bonus_match.group(0).strip()
        conf["bonus"] = Confidence.MEDIUM
    if salary.specified:
        # A verbatim range in the source text is as certain as extraction gets.
        conf["salary_min"] = Confidence.HIGH if salary.minimum else Confidence.ABSENT
        conf["salary_max"] = Confidence.HIGH if salary.maximum else Confidence.ABSENT
    else:
        conf["salary_min"] = Confidence.ABSENT
        conf["salary_max"] = Confidence.ABSENT
    conf["equity"] = Confidence.HIGH if equity.offered is not None else Confidence.ABSENT

    # --- lifestyle --------------------------------------------------------
    remote = nz.parse_remote_status(text)
    travel = nz.parse_travel(text)
    hours = nz.parse_weekly_hours(text)
    lifestyle = LifestyleExtract(
        remote_status=remote,
        location=nz.parse_location(text),
        relocation_required=nz.parse_relocation(text),
        travel_percent=travel,
        weekly_hours=hours,
        on_call=nz.parse_oncall(text),
        nights_weekends=nz.parse_nights_weekends(text),
        shift_work=nz.parse_shift_work(text),
    )
    conf["remote_status"] = (
        Confidence.HIGH if remote != RemoteStatus.UNSPECIFIED else Confidence.ABSENT
    )
    conf["travel"] = Confidence.HIGH if travel is not None else Confidence.ABSENT
    conf["hours"] = Confidence.HIGH if hours is not None else Confidence.ABSENT
    conf["location"] = Confidence.MEDIUM if lifestyle.location else Confidence.ABSENT

    # --- requirements -----------------------------------------------------
    required_skills, preferred_skills = _split_required_preferred(text)
    required_yoe, preferred_yoe = nz.parse_years_experience(text)
    clearance = parse_clearance(text)
    polygraph = parse_polygraph(text)
    education = [m.group(0).strip() for m in _EDUCATION_RE.finditer(text)][:5]
    certs = sorted({m.group(0).strip() for m in _CERT_RE.finditer(text)})
    citizenship = None
    cit_match = _CITIZENSHIP_RE.search(text)
    if cit_match:
        citizenship = cit_match.group(0).strip()

    requirements = RequirementsExtract(
        required_skills=required_skills,
        preferred_skills=preferred_skills,
        required_years_experience=required_yoe,
        preferred_years_experience=preferred_yoe,
        education_requirements=education,
        certifications=certs,
        citizenship_requirement=citizenship,
        security_clearance=clearance,
        polygraph_requirement=polygraph,
        management_responsibility=True if _MANAGEMENT_RE.search(text) else None,
    )
    conf["security_clearance"] = (
        Confidence.HIGH if clearance != ClearanceLevel.UNSPECIFIED else Confidence.ABSENT
    )
    conf["polygraph_requirement"] = (
        Confidence.HIGH if polygraph != PolygraphType.UNKNOWN else Confidence.ABSENT
    )
    conf["required_skills"] = Confidence.HIGH if required_skills else Confidence.ABSENT
    conf["required_years_experience"] = (
        Confidence.HIGH if required_yoe is not None else Confidence.ABSENT
    )

    # --- characteristics --------------------------------------------------
    stage: CompanyStage | None = None
    for pattern, value in _STAGE_PATTERNS:
        if pattern.search(text):
            stage = value
            break

    gov_hits = len(_GOVERNMENT_RE.findall(text))
    if gov_hits:
        gov_or_com = "government"
    elif _ENTERPRISE_RE.search(text) or _CONSUMER_RE.search(text):
        gov_or_com = "commercial"
    else:
        gov_or_com = None

    if _ENTERPRISE_RE.search(text):
        customer_type = "enterprise"
    elif gov_hits:
        customer_type = "government"
    elif _CONSUMER_RE.search(text):
        customer_type = "consumer"
    else:
        customer_type = None

    family_match = classify_job_family(title, text)
    characteristics = CharacteristicsExtract(
        company_stage=stage,
        estimated_company_size=_detect_company_size(text),
        industry="national security" if gov_hits else None,
        customer_type=customer_type,
        government_or_commercial=gov_or_com,
        revenue_responsibility=True if _REVENUE_RE.search(text) else None,
        customer_facing_intensity=_intensity(_CUSTOMER_FACING_HIGH, text, high_hits=2),
        technical_depth=_technical_depth(required_skills, preferred_skills),
        research_intensity=_intensity(_RESEARCH_RE, text, high_hits=2),
        ownership_level=_intensity(_OWNERSHIP_HIGH, text, high_hits=2),
        job_family=family_match.family,
    )
    conf["job_family"] = Confidence.HIGH if family_match.score >= 8 else Confidence.LOW
    conf["company_stage"] = Confidence.MEDIUM if stage else Confidence.ABSENT

    return ExtractionResult(
        company=company,
        title=title,
        employment_type=nz.parse_employment_type(text),
        recruiter_name=recruiter,
        recruiter_contact=email_match.group(0) if email_match else None,
        source_type=source_type,
        source_url=source_url or (url_match.group(0) if url_match else None),
        job_description=text,
        compensation=comp,
        lifestyle=lifestyle,
        requirements=requirements,
        characteristics=characteristics,
        confidence=conf,
        extraction_method="rules",
    )


def _technical_depth(required: list[str], preferred: list[str]) -> str | None:
    from app.services.skills import CATEGORY_AI, CATEGORY_CYBER, CATEGORY_SOFTWARE, get_skill

    technical = {CATEGORY_SOFTWARE, CATEGORY_AI, CATEGORY_CYBER}
    count = sum(
        1
        for slug in [*required, *preferred]
        if (skill := get_skill(slug)) and skill.category in technical
    )
    if count == 0:
        return None
    if count >= 5:
        return "high"
    return "medium" if count >= 2 else "low"


# --------------------------------------------------------------------------
# LLM extraction
# --------------------------------------------------------------------------

LLM_SYSTEM_PROMPT = """\
You extract structured data from recruiter messages and job descriptions.

Rules you must follow:
- Only report what the text actually says. Never infer a salary, clearance, \
polygraph, or travel figure that is not stated.
- If something is not stated, omit the field or use null. "Not mentioned" is a \
valid and useful answer.
- Never treat a counterintelligence (CI) polygraph as equivalent to a full \
scope / expanded scope polygraph. They are different requirements.
- Skills should be short canonical names ("TypeScript", not "5+ years of \
TypeScript experience").
- Put requirement phrases you cannot reduce to a skill name into \
unmapped_requirements verbatim.
"""

#: A trimmed schema: we only ask the model for the fields where language
#: understanding beats a regex. Money and clearance stay with the rules.
LLM_EXTRACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "company": {"type": ["string", "null"]},
        "title": {"type": ["string", "null"]},
        "recruiter_name": {"type": ["string", "null"]},
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "preferred_skills": {"type": "array", "items": {"type": "string"}},
        "unmapped_requirements": {"type": "array", "items": {"type": "string"}},
        "education_requirements": {"type": "array", "items": {"type": "string"}},
        "certifications": {"type": "array", "items": {"type": "string"}},
        "citizenship_requirement": {"type": ["string", "null"]},
        "industry": {"type": ["string", "null"]},
        "customer_type": {
            "type": ["string", "null"],
            "enum": ["government", "enterprise", "consumer", "mixed", None],
        },
        "company_stage": {
            "type": ["string", "null"],
            "enum": [s.value for s in CompanyStage] + [None],
        },
        "estimated_company_size": {"type": ["string", "null"]},
        "customer_facing_intensity": {
            "type": ["string", "null"],
            "enum": ["low", "medium", "high", None],
        },
        "technical_depth": {"type": ["string", "null"], "enum": ["low", "medium", "high", None]},
        "research_intensity": {"type": ["string", "null"], "enum": ["low", "medium", "high", None]},
        "ownership_level": {"type": ["string", "null"], "enum": ["low", "medium", "high", None]},
        "revenue_responsibility": {"type": ["boolean", "null"]},
        "management_responsibility": {"type": ["boolean", "null"]},
        "bonus": {"type": ["string", "null"]},
        "notes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["required_skills", "preferred_skills"],
}


def llm_extract(text: str, provider: LlmProvider) -> dict[str, Any] | None:
    """Ask the model for the fuzzy fields. Returns None on any failure."""
    if not provider.available:
        return None
    request = LlmRequest(
        system=LLM_SYSTEM_PROMPT,
        user=f"Extract structured data from the following text.\n\n---\n{text}\n---",
        schema=LLM_EXTRACTION_SCHEMA,
        schema_name="job_extraction",
        max_tokens=2048,
        temperature=0.0,
    )
    try:
        return provider.complete_json(request)
    except Exception as exc:  # noqa: BLE001 - degrade, never fail the request
        logger.warning("LLM extraction unavailable, using rules only: %s", exc)
        return None


# --------------------------------------------------------------------------
# Merge
# --------------------------------------------------------------------------

#: Fields the deterministic extractor always wins. These are the ones where a
#: confident-but-wrong model answer would be most damaging.
DETERMINISTIC_FIELDS = frozenset(
    {
        "salary_min",
        "salary_max",
        "salary_currency",
        "equity_percent_min",
        "equity_percent_max",
        "security_clearance",
        "polygraph_requirement",
        "travel_percent",
        "weekly_hours",
        "remote_status",
        "required_years_experience",
        "preferred_years_experience",
    }
)


def merge_extractions(rules: ExtractionResult, llm: dict[str, Any] | None) -> ExtractionResult:
    """Overlay LLM output on the deterministic result.

    Precedence:
      * fields in DETERMINISTIC_FIELDS: rules always win, LLM ignored
      * everything else: LLM fills gaps the rules left empty, and *adds* to
        list fields rather than replacing them
    """
    if not llm:
        return rules

    merged = rules.model_copy(deep=True)
    merged.extraction_method = "llm+rules"

    def fill(current: Any, proposed: Any) -> Any:
        return proposed if current in (None, "", []) and proposed not in (None, "", []) else current

    merged.company = fill(merged.company, _clean_str(llm.get("company")))
    merged.title = fill(merged.title, _clean_str(llm.get("title")))
    merged.recruiter_name = fill(merged.recruiter_name, _clean_str(llm.get("recruiter_name")))
    merged.compensation.bonus = fill(merged.compensation.bonus, _clean_str(llm.get("bonus")))

    # Skills: union, normalised through the ontology so the LLM cannot invent
    # a new spelling of an existing skill.
    for key, target in (
        ("required_skills", merged.requirements.required_skills),
        ("preferred_skills", merged.requirements.preferred_skills),
    ):
        proposed = llm.get(key) or []
        if isinstance(proposed, list):
            for slug in normalize_skills([str(s) for s in proposed]):
                if (
                    slug not in merged.requirements.required_skills
                    and slug not in merged.requirements.preferred_skills
                ):
                    target.append(slug)

    unmapped = llm.get("unmapped_requirements") or []
    if isinstance(unmapped, list):
        merged.requirements.unmapped_requirements = [
            str(u).strip() for u in unmapped if str(u).strip()
        ][:20]

    for key in ("education_requirements", "certifications"):
        proposed = llm.get(key) or []
        if isinstance(proposed, list) and not getattr(merged.requirements, key):
            setattr(
                merged.requirements, key, [str(p).strip() for p in proposed if str(p).strip()][:10]
            )

    merged.requirements.citizenship_requirement = fill(
        merged.requirements.citizenship_requirement, _clean_str(llm.get("citizenship_requirement"))
    )
    if merged.requirements.management_responsibility is None:
        merged.requirements.management_responsibility = _clean_bool(
            llm.get("management_responsibility")
        )

    ch = merged.characteristics
    ch.industry = fill(ch.industry, _clean_str(llm.get("industry")))
    ch.customer_type = fill(ch.customer_type, _clean_str(llm.get("customer_type")))
    ch.estimated_company_size = fill(
        ch.estimated_company_size, _clean_str(llm.get("estimated_company_size"))
    )
    for key in (
        "customer_facing_intensity",
        "technical_depth",
        "research_intensity",
        "ownership_level",
    ):
        if getattr(ch, key) is None:
            setattr(ch, key, _clean_str(llm.get(key)))
    if ch.revenue_responsibility is None:
        ch.revenue_responsibility = _clean_bool(llm.get("revenue_responsibility"))
    if ch.company_stage is None:
        stage = _clean_str(llm.get("company_stage"))
        if stage:
            try:
                ch.company_stage = CompanyStage(stage)
            except ValueError:
                logger.debug("LLM proposed unknown company stage: %s", stage)

    # If the LLM supplied a better title, re-run the deterministic family
    # classifier rather than trusting a model guess about the family.
    if merged.title and merged.characteristics.job_family == JobFamily.OTHER:
        rematch = classify_job_family(merged.title, merged.job_description or "")
        merged.characteristics.job_family = rematch.family
        merged.confidence["job_family"] = (
            Confidence.MEDIUM if rematch.score >= 8 else Confidence.LOW
        )

    # LLM-sourced values are never marked HIGH confidence.
    for field_name in ("company", "title", "industry", "customer_type"):
        if merged.confidence.get(field_name) in (None, Confidence.ABSENT):
            value = getattr(merged, field_name, None) or getattr(
                merged.characteristics, field_name, None
            )
            if value:
                merged.confidence[field_name] = Confidence.MEDIUM

    notes = llm.get("notes") or []
    if isinstance(notes, list):
        merged.notes.extend(str(n).strip() for n in notes if str(n).strip())

    return merged


def _clean_str(value: Any) -> str | None:
    if (
        isinstance(value, str)
        and value.strip()
        and value.strip().lower() not in ("null", "none", "n/a")
    ):
        return value.strip()
    return None


def _clean_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def extract(
    text: str,
    *,
    provider: LlmProvider | None = None,
    source_url: str | None = None,
    known_company: str | None = None,
    known_title: str | None = None,
    use_llm: bool = True,
) -> ExtractionResult:
    """Full pipeline: rules always, LLM when available, merged deterministically."""
    rules = rule_extract(
        text, source_url=source_url, known_company=known_company, known_title=known_title
    )
    if not use_llm or provider is None or not provider.available:
        return rules
    return merge_extractions(rules, llm_extract(text, provider))


__all__ = [
    "extract",
    "rule_extract",
    "llm_extract",
    "merge_extractions",
    "DETERMINISTIC_FIELDS",
    "LLM_EXTRACTION_SCHEMA",
]
