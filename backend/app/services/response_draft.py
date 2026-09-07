"""§12 - recruiter response drafting.

Every draft is generated deterministically from a template first. The LLM is
used only to *polish* prose when a provider is configured, and its output is
discarded if it drops the substance (the questions that must be asked).

Nothing here sends anything. Drafts are stored for human approval; that is a
product requirement, not an implementation detail (§1: "Do not autonomously
send recruiter messages").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.core.enums import (
    ClearanceLevel,
    DraftIntent,
    DraftTone,
    PolygraphType,
    RecommendedAction,
)
from app.core.logging import get_logger
from app.llm.base import LlmProvider, LlmRequest
from app.services.missing_info import MissingField, blocking_missing_fields

logger = get_logger(__name__)


@dataclass
class ResponseDraft:
    intent: DraftIntent
    tone: DraftTone
    subject: str
    body: str
    #: The questions this draft actually asks, so the UI can show what would
    #: still be unknown if the recruiter answers it.
    questions_asked: list[str]
    generated_by: str = "template"

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent": self.intent.value,
            "tone": self.tone.value,
            "subject": self.subject,
            "body": self.body,
            "questions_asked": self.questions_asked,
            "generated_by": self.generated_by,
        }


_GREETINGS = {
    DraftTone.PROFESSIONAL: "Hi {name},",
    DraftTone.WARM: "Hi {name},",
    DraftTone.DIRECT: "{name},",
    DraftTone.HUMOROUS: "Hey {name},",
}

_OPENERS = {
    DraftIntent.REQUEST_MISSING_INFO: {
        DraftTone.PROFESSIONAL: "Thanks for reaching out. The role sounds potentially interesting.",
        DraftTone.WARM: (
            "Thanks for getting in touch - this sounds like it could be a good fit, and I "
            "appreciate you thinking of me."
        ),
        DraftTone.DIRECT: (
            "Thanks for reaching out. Before we schedule anything, I need a few details."
        ),
        DraftTone.HUMOROUS: (
            "Thanks for reaching out! Before I get excited, let's talk brass tacks."
        ),
    },
    DraftIntent.ENTHUSIASTIC_SCHEDULE: {
        DraftTone.PROFESSIONAL: (
            "Thanks for reaching out. This is squarely the kind of role I'm looking for and I'd "
            "like to move forward."
        ),
        DraftTone.WARM: (
            "Thanks for reaching out - this is genuinely exciting, and it lines up well with what "
            "I'm looking for."
        ),
        DraftTone.DIRECT: "This is a strong fit. I'd like to move forward.",
        DraftTone.HUMOROUS: "You had me at the job title. This one's a strong fit.",
    },
    DraftIntent.POLITE_DECLINE: {
        DraftTone.PROFESSIONAL: "Thanks for reaching out, and for the detail you shared.",
        DraftTone.WARM: (
            "Thanks so much for thinking of me, and for laying out the details up front."
        ),
        DraftTone.DIRECT: "Thanks for the detail.",
        DraftTone.HUMOROUS: (
            "Thanks for reaching out - and for actually including numbers, which is rarer than it "
            "should be."
        ),
    },
    DraftIntent.CLEARANCE_CLARIFICATION: {
        DraftTone.PROFESSIONAL: (
            "Thanks for reaching out. Before we go further I want to confirm the eligibility "
            "requirements."
        ),
        DraftTone.WARM: (
            "Thanks for reaching out - this looks interesting, and I want to make sure I'm "
            "actually eligible before we both invest time."
        ),
        DraftTone.DIRECT: (
            "Thanks for reaching out. I need to confirm the clearance requirements first."
        ),
        DraftTone.HUMOROUS: (
            "Thanks for reaching out! Let's sort out the paperwork question before "
            "anything else."
        ),
    },
}

_CLOSINGS = {
    DraftTone.PROFESSIONAL: "Best,\n{candidate}",
    DraftTone.WARM: "Thanks again,\n{candidate}",
    DraftTone.DIRECT: "Thanks,\n{candidate}",
    DraftTone.HUMOROUS: "Cheers,\n{candidate}",
}


def _join_questions(questions: list[str]) -> str:
    """Join question fragments into one readable sentence."""
    if not questions:
        return ""
    if len(questions) == 1:
        return questions[0]
    return ", ".join(questions[:-1]) + ", and " + questions[-1]


def _recruiter_name(job) -> str:
    name = (getattr(job, "recruiter_name", None) or "").strip()
    if not name:
        return "there"
    return name.split()[0]


def _role_phrase(job) -> str:
    title = (getattr(job, "title", None) or "").strip()
    company = (getattr(job, "company", None) or "").strip()
    if title and company:
        return f"the {title} role at {company}"
    if title:
        return f"the {title} role"
    if company:
        return f"the role at {company}"
    return "the role"


def draft_missing_info_response(
    job,
    missing: list[MissingField],
    *,
    tone: DraftTone = DraftTone.PROFESSIONAL,
    candidate_name: str = "",
) -> ResponseDraft:
    """The workhorse draft: ask for what's missing, concisely, in one message."""
    # Ask for the blocking items plus the clearance/polygraph clarification if
    # present. Asking twelve questions gets you zero answers.
    blocking = blocking_missing_fields(missing)
    eligibility = [m for m in missing if m.field in ("security_clearance", "polygraph_requirement")]
    extras = [m for m in missing if m.field in ("equity", "equity_percent") and m not in blocking]
    selected = blocking + [m for m in extras if m not in blocking]

    questions = [m.question for m in selected]
    body_lines = [
        _GREETINGS[tone].format(name=_recruiter_name(job)),
        "",
        _OPENERS[DraftIntent.REQUEST_MISSING_INFO][tone],
        "",
    ]

    if questions:
        body_lines.append(
            f"Before we schedule time, could you send me {_join_questions(questions)}?"
        )
    else:
        body_lines.append("Before we schedule time, could you send over a few more details?")

    if eligibility:
        body_lines.append("")
        poly = [m for m in eligibility if m.field == "polygraph_requirement"]
        if poly:
            body_lines.append(
                "If the position requires a clearance or polygraph, please also let me know the "
                "specific requirement - in particular whether it is a CI scope or a full scope / "
                "expanded scope polygraph, since those are quite different."
            )
            questions.append(poly[0].question)
        else:
            body_lines.append(
                "If the position requires a clearance, please also let me know the specific level."
            )
            questions.append(eligibility[0].question)

    body_lines += [
        "",
        "Happy to find time once I have those.",
        "",
        _CLOSINGS[tone].format(candidate=candidate_name or ""),
    ]

    return ResponseDraft(
        intent=DraftIntent.REQUEST_MISSING_INFO,
        tone=tone,
        subject=f"Re: {(getattr(job, 'title', None) or 'your note')}",
        body="\n".join(body_lines).rstrip(),
        questions_asked=questions,
    )


def draft_enthusiastic_response(
    job,
    missing: list[MissingField],
    *,
    tone: DraftTone = DraftTone.PROFESSIONAL,
    candidate_name: str = "",
) -> ResponseDraft:
    """Strong opportunity: say yes, and still close the remaining gaps."""
    blocking = blocking_missing_fields(missing)
    questions = [m.question for m in blocking[:3]]

    body_lines = [
        _GREETINGS[tone].format(name=_recruiter_name(job)),
        "",
        _OPENERS[DraftIntent.ENTHUSIASTIC_SCHEDULE][tone],
        "",
        f"{_role_phrase(job).capitalize()} lines up well with what I'm targeting, and I'd be glad "
        "to find time this week or next.",
    ]
    if questions:
        body_lines += [
            "",
            f"So I come prepared, could you also confirm {_join_questions(questions)}?",
        ]
    body_lines += [
        "",
        "What does your calendar look like?",
        "",
        _CLOSINGS[tone].format(candidate=candidate_name or ""),
    ]

    return ResponseDraft(
        intent=DraftIntent.ENTHUSIASTIC_SCHEDULE,
        tone=tone,
        subject=f"Re: {(getattr(job, 'title', None) or 'your note')} - happy to talk",
        body="\n".join(body_lines).rstrip(),
        questions_asked=questions,
    )


def draft_decline_response(
    job, reason: str, *, tone: DraftTone = DraftTone.PROFESSIONAL, candidate_name: str = ""
) -> ResponseDraft:
    """Polite decline that leaves the door open without wasting anyone's time."""
    body_lines = [
        _GREETINGS[tone].format(name=_recruiter_name(job)),
        "",
        _OPENERS[DraftIntent.POLITE_DECLINE][tone],
        "",
        f"I'm going to pass on {_role_phrase(job)}. {reason}",
        "",
        "If something opens up that fits better, I'd be glad to hear about it - "
        "happy to stay in touch.",
        "",
        _CLOSINGS[tone].format(candidate=candidate_name or ""),
    ]
    return ResponseDraft(
        intent=DraftIntent.POLITE_DECLINE,
        tone=tone,
        subject=f"Re: {(getattr(job, 'title', None) or 'your note')}",
        body="\n".join(body_lines).rstrip(),
        questions_asked=[],
    )


def draft_clearance_clarification(
    job, *, tone: DraftTone = DraftTone.PROFESSIONAL, candidate_name: str = ""
) -> ResponseDraft:
    """Ask the four clearance questions that actually determine eligibility."""
    questions = [
        "whether the role requires TS/SCI",
        "whether a CI polygraph is required",
        "whether a full scope / expanded scope polygraph is required",
        "whether the employer can sponsor an upgrade if the current scope is insufficient",
    ]
    body_lines = [
        _GREETINGS[tone].format(name=_recruiter_name(job)),
        "",
        _OPENERS[DraftIntent.CLEARANCE_CLARIFICATION][tone],
        "",
        "Could you confirm the specific requirements? Specifically: "
        + _join_questions(questions)
        + ".",
        "",
        "I ask because a CI polygraph and a full scope polygraph are different requirements, and "
        "the answer changes whether this is a fit today or something that needs sponsorship.",
        "",
        _CLOSINGS[tone].format(candidate=candidate_name or ""),
    ]
    return ResponseDraft(
        intent=DraftIntent.CLEARANCE_CLARIFICATION,
        tone=tone,
        subject=f"Re: {(getattr(job, 'title', None) or 'your note')} - clearance requirements",
        body="\n".join(body_lines).rstrip(),
        questions_asked=questions,
    )


def choose_intent(job, scoring_result, missing: list[MissingField]) -> DraftIntent:
    """Pick the right kind of reply from the score and what's missing.

    Ordering matters: an ambiguous polygraph requirement outranks everything,
    because it determines whether the conversation is worth having at all.
    """
    polygraph = getattr(job, "polygraph_requirement", None)
    clearance = getattr(job, "security_clearance", None)
    if polygraph == PolygraphType.UNSPECIFIED_POLYGRAPH.value or (
        clearance == ClearanceLevel.UNSPECIFIED.value
        and any(m.field == "security_clearance" for m in missing)
        and scoring_result.hard_gates
    ):
        return DraftIntent.CLEARANCE_CLARIFICATION

    action = scoring_result.recommended_action
    if action in (RecommendedAction.REJECT, RecommendedAction.LOW_PRIORITY):
        return DraftIntent.POLITE_DECLINE
    if action in (
        RecommendedAction.STRONGLY_PURSUE,
        RecommendedAction.PURSUE,
    ) and not blocking_missing_fields(missing):
        return DraftIntent.ENTHUSIASTIC_SCHEDULE
    return DraftIntent.REQUEST_MISSING_INFO


def _decline_reason(job, scoring_result) -> str:
    if scoring_result.hard_gates:
        gate = scoring_result.hard_gates[0]
        return (
            f"Based on what you've shared, {gate.requirement.lower()} is a requirement I don't "
            "currently meet, and it isn't something I can close on a useful timeline."
        )
    if scoring_result.compensation.score < 40 and scoring_result.compensation.details.get(
        "specified"
    ):
        return "The compensation range is below what I'm targeting for my next move."
    if scoring_result.career_capital.score < 40:
        return "The scope isn't a step forward relative to what I'm focused on right now."
    return "It isn't the right fit for what I'm focused on at the moment."


def generate_response_draft(
    job,
    scoring_result,
    missing: list[MissingField],
    *,
    tone: DraftTone = DraftTone.PROFESSIONAL,
    candidate_name: str = "",
    intent: DraftIntent | None = None,
    provider: LlmProvider | None = None,
    polish: bool = True,
) -> ResponseDraft:
    """Generate the draft, optionally polished by an LLM.

    The template is always produced first and is the fallback. If polishing
    drops a required question, the polished version is rejected - the model
    does not get to quietly decide you shouldn't ask about salary.
    """
    intent = intent or choose_intent(job, scoring_result, missing)

    if intent is DraftIntent.POLITE_DECLINE:
        draft = draft_decline_response(
            job, _decline_reason(job, scoring_result), tone=tone, candidate_name=candidate_name
        )
    elif intent is DraftIntent.ENTHUSIASTIC_SCHEDULE:
        draft = draft_enthusiastic_response(job, missing, tone=tone, candidate_name=candidate_name)
    elif intent is DraftIntent.CLEARANCE_CLARIFICATION:
        draft = draft_clearance_clarification(job, tone=tone, candidate_name=candidate_name)
    else:
        draft = draft_missing_info_response(job, missing, tone=tone, candidate_name=candidate_name)

    if polish and provider is not None and provider.available:
        polished = _polish(draft, provider, tone)
        if polished is not None:
            return polished
    return draft


_POLISH_SYSTEM = """\
You are editing a short reply a job candidate will send to a recruiter.

Rules:
- Keep every question the draft asks. Do not drop, soften, or merge away any request \
for information.
- Keep it under 150 words. Recruiters do not read long replies.
- Do not invent facts about the candidate, the company, or the role.
- Do not add flattery, buzzwords, or exclamation marks unless the requested tone is humorous.
- Return only the message body. No subject line, no commentary.
"""


def _polish(draft: ResponseDraft, provider: LlmProvider, tone: DraftTone) -> ResponseDraft | None:
    """Ask the model to tighten the prose. Returns None if it degrades the draft."""
    request = LlmRequest(
        system=_POLISH_SYSTEM,
        user=(
            f"Requested tone: {tone.value}.\n"
            f"Questions that MUST still be asked: {'; '.join(draft.questions_asked) or 'none'}\n\n"
            f"Draft:\n{draft.body}"
        ),
        max_tokens=800,
        temperature=0.3,
    )
    try:
        text = provider.complete_text(request).strip()
    except Exception as exc:  # noqa: BLE001 - the template is always a valid answer
        logger.warning("Draft polishing failed, keeping the template draft: %s", exc)
        return None

    if not text or len(text) < 40:
        return None
    # Verify the substance survived: every question must still be recognisable.
    lowered = text.lower()
    for question in draft.questions_asked:
        keywords = [w for w in question.lower().split() if len(w) > 4][:3]
        if keywords and not any(k in lowered for k in keywords):
            logger.info("Polished draft dropped a required question; keeping the template.")
            return None

    return ResponseDraft(
        intent=draft.intent,
        tone=draft.tone,
        subject=draft.subject,
        body=text,
        questions_asked=draft.questions_asked,
        generated_by="llm-polished",
    )


__all__ = [
    "generate_response_draft",
    "ResponseDraft",
    "choose_intent",
    "draft_missing_info_response",
    "draft_enthusiastic_response",
    "draft_decline_response",
    "draft_clearance_clarification",
]
