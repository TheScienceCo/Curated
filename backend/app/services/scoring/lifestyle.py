"""E. Lifestyle Score.

Explicitly does *not* assume "startup = bad lifestyle" (§6E). Only stated
facts move the number: hours, remote posture, travel, on-call, shift work,
relocation and commute.
"""

from __future__ import annotations

from app.core.enums import RemotePreference, RemoteStatus
from app.services.scoring.base import DimensionScore, Reason, clamp
from app.services.scoring.config import ScoringConfig

BASE_SCORE = 70.0


def _remote_alignment(job, candidate) -> tuple[float, Reason | None]:
    status = job.remote_status or RemoteStatus.UNSPECIFIED.value
    preference = candidate.remote_preference or RemotePreference.NO_PREFERENCE.value

    if status == RemoteStatus.UNSPECIFIED.value:
        return 0.0, Reason("Remote / hybrid / onsite posture not stated.", kind="missing")

    matrix: dict[tuple[str, str], tuple[float, str]] = {
        (RemotePreference.REMOTE_ONLY.value, RemoteStatus.REMOTE.value): (
            15,
            "Fully remote, matching your remote-only preference.",
        ),
        (RemotePreference.REMOTE_ONLY.value, RemoteStatus.HYBRID.value): (
            -25,
            "Hybrid conflicts with your remote-only preference.",
        ),
        (RemotePreference.REMOTE_ONLY.value, RemoteStatus.ONSITE.value): (
            -35,
            "Onsite conflicts with your remote-only preference.",
        ),
        (RemotePreference.REMOTE_PREFERRED.value, RemoteStatus.REMOTE.value): (
            15,
            "Fully remote, matching your preference.",
        ),
        (RemotePreference.REMOTE_PREFERRED.value, RemoteStatus.HYBRID.value): (
            -8,
            "Hybrid, where you would prefer remote.",
        ),
        (RemotePreference.REMOTE_PREFERRED.value, RemoteStatus.ONSITE.value): (
            -18,
            "Fully onsite, where you would prefer remote.",
        ),
        (RemotePreference.HYBRID_OK.value, RemoteStatus.REMOTE.value): (12, "Fully remote."),
        (RemotePreference.HYBRID_OK.value, RemoteStatus.HYBRID.value): (
            6,
            "Hybrid, which you have said works.",
        ),
        (RemotePreference.HYBRID_OK.value, RemoteStatus.ONSITE.value): (
            -12,
            "Fully onsite, beyond your hybrid preference.",
        ),
        (RemotePreference.ONSITE_OK.value, RemoteStatus.REMOTE.value): (8, "Fully remote."),
        (RemotePreference.ONSITE_OK.value, RemoteStatus.HYBRID.value): (5, "Hybrid."),
        (RemotePreference.ONSITE_OK.value, RemoteStatus.ONSITE.value): (
            0,
            "Onsite, which you have said works.",
        ),
    }
    if preference == RemotePreference.NO_PREFERENCE.value:
        delta = {
            RemoteStatus.REMOTE.value: 8,
            RemoteStatus.HYBRID.value: 2,
            RemoteStatus.ONSITE.value: -4,
        }.get(status, 0)
        return delta, Reason(f"{status.title()} working arrangement.", impact=delta, kind="neutral")

    delta, text = matrix.get((preference, status), (0.0, f"{status.title()} working arrangement."))
    return delta, Reason(
        text, impact=delta, kind="positive" if delta > 0 else "negative" if delta < 0 else "neutral"
    )


def score_lifestyle(job, candidate, config: ScoringConfig) -> DimensionScore:
    reasons: list[Reason] = []
    score = BASE_SCORE

    delta, reason = _remote_alignment(job, candidate)
    score += delta
    if reason:
        reasons.append(reason)

    # --- weekly hours ------------------------------------------------------
    hours = job.hours
    preferred_hours = candidate.preferred_weekly_hours
    if hours is None:
        reasons.append(
            Reason("Expected weekly hours not stated - ask before committing.", kind="missing")
        )
        score -= 3
    elif preferred_hours:
        overage = hours - preferred_hours
        if overage <= 0:
            score += 10
            reasons.append(
                Reason(
                    f"{hours}h/week is at or under your {preferred_hours}h preference.",
                    impact=10,
                    kind="positive",
                )
            )
        else:
            penalty = min(30.0, overage * 1.8)
            score -= penalty
            reasons.append(
                Reason(
                    f"{hours}h/week is {overage}h over your {preferred_hours}h preference.",
                    impact=-penalty,
                    kind="negative",
                )
            )
    elif hours > 50:
        score -= min(25.0, (hours - 50) * 1.5)
        reasons.append(
            Reason(
                f"{hours}h/week is a demanding schedule.",
                impact=-(hours - 50) * 1.5,
                kind="negative",
            )
        )

    # --- travel ------------------------------------------------------------
    travel = job.travel
    tolerance = candidate.willingness_to_travel
    if travel is None:
        reasons.append(Reason("Travel expectations not stated.", kind="missing"))
        score -= 3
    elif tolerance is not None:
        if travel <= tolerance:
            score += 6
            reasons.append(
                Reason(
                    f"{travel}% travel is within your {tolerance}% tolerance.",
                    impact=6,
                    kind="positive",
                )
            )
        else:
            penalty = min(25.0, (travel - tolerance) * 0.8)
            score -= penalty
            reasons.append(
                Reason(
                    f"{travel}% travel exceeds your {tolerance}% tolerance.",
                    impact=-penalty,
                    kind="negative",
                )
            )

    # --- on-call, nights, shifts ------------------------------------------
    if job.on_call:
        score -= 8
        reasons.append(Reason("On-call rotation.", impact=-8, kind="negative"))
    if job.nights_weekends:
        score -= 10
        reasons.append(Reason("Nights and weekends expected.", impact=-10, kind="negative"))
    if job.shift_work:
        score -= 15
        reasons.append(Reason("Shift work.", impact=-15, kind="negative"))

    # --- relocation --------------------------------------------------------
    if job.relocation_required:
        score -= 12
        reasons.append(Reason("Relocation required.", impact=-12, kind="negative"))
    elif job.relocation_required is False:
        score += 3
        reasons.append(Reason("No relocation required.", impact=3, kind="positive"))

    # --- explicit preferences from the profile ----------------------------
    prefs = candidate.lifestyle_preferences or {}
    if prefs.get("no_shift_work") and job.shift_work:
        score -= 10
        reasons.append(Reason("You have ruled out shift work.", impact=-10, kind="negative"))
    if prefs.get("max_commute_minutes") and job.remote_status == RemoteStatus.ONSITE.value:
        reasons.append(
            Reason(
                f"Onsite role - check the commute against your "
                f"{prefs['max_commute_minutes']}-minute limit.",
                kind="neutral",
            )
        )

    return DimensionScore(
        name="Lifestyle",
        score=clamp(score),
        reasons=reasons,
        details={
            "hours": hours,
            "travel": travel,
            "remote_status": job.remote_status,
        },
    )


__all__ = ["score_lifestyle"]
