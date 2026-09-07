"""Classify a job title (plus supporting text) into a target job family.

Deterministic keyword scoring rather than an LLM call: titles are short,
the taxonomy is fixed, and a wrong-but-confident LLM guess here would quietly
distort résumé matching and career-capital scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.enums import JobFamily

#: Human-facing grouping used by the UI.
FAMILY_GROUPS: dict[str, list[JobFamily]] = {
    "AI / Engineering": [
        JobFamily.FORWARD_DEPLOYED_ENGINEER,
        JobFamily.AI_ENGINEER,
        JobFamily.ML_ENGINEER,
        JobFamily.RESEARCH_ENGINEER,
        JobFamily.MEMBER_OF_TECHNICAL_STAFF,
        JobFamily.SOLUTIONS_ARCHITECT,
    ],
    "National Security / Defense": [
        JobFamily.CLEARED_SOFTWARE_ENGINEER,
        JobFamily.AI_MISSION_ENGINEER,
        JobFamily.TECHNICAL_INTELLIGENCE_ANALYST,
        JobFamily.TECHNICAL_PROGRAM_SETA,
    ],
    "Cyber": [
        JobFamily.MALWARE_REVERSE_ENGINEER,
        JobFamily.VULNERABILITY_RESEARCHER,
        JobFamily.CYBER_THREAT_INTELLIGENCE,
        JobFamily.AI_SECURITY_ENGINEER,
    ],
    "Bio / Scientific AI": [
        JobFamily.SCIENTIFIC_ML_ENGINEER,
        JobFamily.COMPUTATIONAL_BIOLOGY_ML,
        JobFamily.BIOSECURITY_SCIENTIST,
    ],
    "Customer / Revenue": [
        JobFamily.SOLUTIONS_ENGINEER,
        JobFamily.TECHNICAL_ACCOUNT_EXECUTIVE,
        JobFamily.TECHNICAL_BUSINESS_DEVELOPMENT,
        JobFamily.GTM_ENGINEER,
    ],
    "Generalist / Multidisciplinary": [
        JobFamily.CHIEF_OF_STAFF,
        JobFamily.FOUNDERS_OFFICE,
        JobFamily.SPECIAL_PROJECTS,
        JobFamily.STRATEGY_AND_OPERATIONS,
        JobFamily.ENTREPRENEUR_IN_RESIDENCE,
    ],
}

FAMILY_LABELS: dict[JobFamily, str] = {
    JobFamily.FORWARD_DEPLOYED_ENGINEER: "Forward Deployed Engineer",
    JobFamily.AI_ENGINEER: "AI / Applied AI Engineer",
    JobFamily.ML_ENGINEER: "ML Engineer",
    JobFamily.RESEARCH_ENGINEER: "Research Engineer",
    JobFamily.MEMBER_OF_TECHNICAL_STAFF: "Member of Technical Staff",
    JobFamily.SOLUTIONS_ARCHITECT: "Solutions Architect",
    JobFamily.CLEARED_SOFTWARE_ENGINEER: "Cleared Software Engineer",
    JobFamily.AI_MISSION_ENGINEER: "AI Mission Engineer",
    JobFamily.TECHNICAL_INTELLIGENCE_ANALYST: "Technical Intelligence Analyst",
    JobFamily.TECHNICAL_PROGRAM_SETA: "Technical Program / SETA",
    JobFamily.MALWARE_REVERSE_ENGINEER: "Malware / Reverse Engineer",
    JobFamily.VULNERABILITY_RESEARCHER: "Vulnerability Researcher",
    JobFamily.CYBER_THREAT_INTELLIGENCE: "Cyber Threat Intelligence",
    JobFamily.AI_SECURITY_ENGINEER: "AI Security Engineer",
    JobFamily.SCIENTIFIC_ML_ENGINEER: "Scientific ML Engineer",
    JobFamily.COMPUTATIONAL_BIOLOGY_ML: "Computational Biology ML Scientist",
    JobFamily.BIOSECURITY_SCIENTIST: "Biosecurity Scientist",
    JobFamily.SOLUTIONS_ENGINEER: "Solutions / Sales Engineer",
    JobFamily.TECHNICAL_ACCOUNT_EXECUTIVE: "Technical Account Executive",
    JobFamily.TECHNICAL_BUSINESS_DEVELOPMENT: "Technical Business Development",
    JobFamily.GTM_ENGINEER: "GTM Engineer",
    JobFamily.CHIEF_OF_STAFF: "Chief of Staff",
    JobFamily.FOUNDERS_OFFICE: "Founder's Office / Founder's Associate",
    JobFamily.SPECIAL_PROJECTS: "Special Projects",
    JobFamily.STRATEGY_AND_OPERATIONS: "Strategy & Operations",
    JobFamily.ENTREPRENEUR_IN_RESIDENCE: "Entrepreneur in Residence",
    JobFamily.OTHER: "Other",
}

#: (family, weight, phrases). Phrases are matched against the title first and
#: the body text second (at a discount), because titles are far more reliable.
_RULES: list[tuple[JobFamily, float, tuple[str, ...]]] = [
    (
        JobFamily.FORWARD_DEPLOYED_ENGINEER,
        10,
        (
            "forward deployed engineer",
            "forward-deployed engineer",
            "forward deployed ai engineer",
            "forward deployed software engineer",
            "fde",
            "mission engineer",
            "field engineer",
            "deployment engineer",
            "deployment strategist",
        ),
    ),
    (
        JobFamily.AI_MISSION_ENGINEER,
        11,
        (
            "ai mission engineer",
            "mission ai engineer",
            "defense ai engineer",
        ),
    ),
    (
        JobFamily.AI_ENGINEER,
        9,
        (
            "ai engineer",
            "applied ai engineer",
            "applied ai",
            "genai engineer",
            "generative ai engineer",
            "llm engineer",
            "ai software engineer",
            "agent engineer",
        ),
    ),
    (
        JobFamily.ML_ENGINEER,
        9,
        (
            "ml engineer",
            "machine learning engineer",
            "mlops engineer",
            "ml infrastructure",
        ),
    ),
    (
        JobFamily.RESEARCH_ENGINEER,
        9,
        (
            "research engineer",
            "research scientist",
            "member of research",
        ),
    ),
    (
        JobFamily.MEMBER_OF_TECHNICAL_STAFF,
        9,
        (
            "member of technical staff",
            "mts",
            "technical staff",
        ),
    ),
    (
        JobFamily.SOLUTIONS_ARCHITECT,
        8,
        (
            "solutions architect",
            "solution architect",
            "principal architect",
        ),
    ),
    (
        JobFamily.CLEARED_SOFTWARE_ENGINEER,
        8,
        (
            "cleared software engineer",
            "cleared engineer",
            "software engineer - ts/sci",
            "backend engineer - cleared",
        ),
    ),
    (
        JobFamily.TECHNICAL_INTELLIGENCE_ANALYST,
        9,
        (
            "intelligence analyst",
            "technical intelligence",
            "all-source analyst",
            "all source analyst",
            "targeting analyst",
            "intelligence technology sme",
        ),
    ),
    (
        JobFamily.TECHNICAL_PROGRAM_SETA,
        8,
        (
            "seta",
            "systems engineering and technical assistance",
            "technical program manager",
            "program manager",
            "technical advisor",
        ),
    ),
    (
        JobFamily.MALWARE_REVERSE_ENGINEER,
        10,
        (
            "malware analyst",
            "malware reverse engineer",
            "reverse engineer",
            "malware researcher",
            "binary analyst",
        ),
    ),
    (
        JobFamily.VULNERABILITY_RESEARCHER,
        10,
        (
            "vulnerability researcher",
            "vulnerability research",
            "security researcher",
            "exploit developer",
            "offensive security engineer",
        ),
    ),
    (
        JobFamily.CYBER_THREAT_INTELLIGENCE,
        9,
        (
            "threat intelligence analyst",
            "cyber threat intelligence",
            "threat researcher",
            "nation-state threat",
            "nation state threat",
            "threat hunter",
        ),
    ),
    (
        JobFamily.AI_SECURITY_ENGINEER,
        10,
        (
            "ai security engineer",
            "ai security",
            "ml security",
            "model security engineer",
            "ai red team",
            "adversarial ml",
        ),
    ),
    (
        JobFamily.SCIENTIFIC_ML_ENGINEER,
        10,
        (
            "scientific ml",
            "scientific ai engineer",
            "ai scientist",
            "science ml engineer",
            "research engineer - biology",
        ),
    ),
    (
        JobFamily.COMPUTATIONAL_BIOLOGY_ML,
        10,
        (
            "computational biology",
            "computational biologist",
            "bioinformatics scientist",
            "ai drug discovery",
            "drug discovery scientist",
            "ml scientist - biology",
        ),
    ),
    (
        JobFamily.BIOSECURITY_SCIENTIST,
        10,
        (
            "biosecurity",
            "biodefense scientist",
        ),
    ),
    (
        JobFamily.SOLUTIONS_ENGINEER,
        9,
        (
            "solutions engineer",
            "sales engineer",
            "federal solutions engineer",
            "enterprise solutions engineer",
            "pre-sales engineer",
            "presales engineer",
            "national security solutions engineer",
        ),
    ),
    (
        JobFamily.TECHNICAL_ACCOUNT_EXECUTIVE,
        9,
        (
            "account executive",
            "technical account executive",
            "enterprise account executive",
            "account manager",
        ),
    ),
    (
        JobFamily.TECHNICAL_BUSINESS_DEVELOPMENT,
        9,
        (
            "business development",
            "strategic partnerships",
            "partnerships lead",
            "capture manager",
            "technical business development",
        ),
    ),
    (
        JobFamily.GTM_ENGINEER,
        10,
        (
            "gtm engineer",
            "go-to-market engineer",
            "growth engineer",
        ),
    ),
    (
        JobFamily.CHIEF_OF_STAFF,
        11,
        (
            "chief of staff",
            "technical chief of staff",
        ),
    ),
    (
        JobFamily.FOUNDERS_OFFICE,
        11,
        (
            "founder's associate",
            "founders associate",
            "founder's office",
            "founders office",
            "founding engineer",
        ),
    ),
    (
        JobFamily.SPECIAL_PROJECTS,
        10,
        (
            "special projects",
            "head of special projects",
            "strategic initiatives",
            "skunkworks",
        ),
    ),
    (
        JobFamily.STRATEGY_AND_OPERATIONS,
        9,
        (
            "strategy & operations",
            "strategy and operations",
            "biz ops",
            "business operations",
            "technical strategy",
        ),
    ),
    (
        JobFamily.ENTREPRENEUR_IN_RESIDENCE,
        11,
        (
            "entrepreneur in residence",
            "eir",
        ),
    ),
]


@dataclass
class FamilyMatch:
    family: JobFamily
    label: str
    score: float
    matched_phrases: list[str]


def _phrase_pattern(phrase: str) -> re.Pattern[str]:
    """Compile a phrase so spaces also match hyphens ("forward-deployed")."""
    escaped = re.escape(phrase)
    escaped = escaped.replace("\\ ", "[\\s\\-]+").replace(" ", "[\\s\\-]+")
    return re.compile("(?<![\\w])" + escaped + "(?![\\w])", re.I)


_COMPILED: list[tuple[JobFamily, float, tuple[tuple[str, re.Pattern[str]], ...]]] = [
    (family, weight, tuple((p, _phrase_pattern(p)) for p in phrases))
    for family, weight, phrases in _RULES
]


def classify_job_family(title: str | None, body: str | None = None) -> FamilyMatch:
    """Pick the best-matching job family.

    Title matches are worth full weight; body matches a quarter, so a JD that
    merely mentions "reverse engineering" does not outrank a title that says
    "AI Engineer".
    """
    title_text = title or ""
    body_text = body or ""
    best: FamilyMatch | None = None

    for family, weight, phrases in _COMPILED:
        score = 0.0
        matched: list[str] = []
        for phrase, pattern in phrases:
            if title_text and pattern.search(title_text):
                score += weight
                matched.append(phrase)
            elif body_text and pattern.search(body_text):
                score += weight * 0.25
                matched.append(phrase)
        if score > 0 and (best is None or score > best.score):
            best = FamilyMatch(family, FAMILY_LABELS[family], score, matched)

    if best is None:
        return FamilyMatch(JobFamily.OTHER, FAMILY_LABELS[JobFamily.OTHER], 0.0, [])
    return best


def family_label(value: str | None) -> str:
    if not value:
        return "Unclassified"
    try:
        return FAMILY_LABELS[JobFamily(value)]
    except ValueError:
        return value.replace("_", " ").title()


def group_for(family: str | None) -> str | None:
    if not family:
        return None
    for group, members in FAMILY_GROUPS.items():
        if any(m.value == family for m in members):
            return group
    return None


__all__ = [
    "classify_job_family",
    "FamilyMatch",
    "FAMILY_LABELS",
    "FAMILY_GROUPS",
    "family_label",
    "group_for",
]
