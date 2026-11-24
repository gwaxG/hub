from dataclasses import dataclass
from typing import Literal

Verdict = Literal["GREEN", "YELLOW", "RED"]

RATE_YELLOW = 1.5
RATE_RED = 3.0


@dataclass(frozen=True)
class TickEvidence:
    new_sentry_issues: int
    sentry_error_level_issues: int
    error_count: int
    baseline_error_count: float | None
    smoke_failures: int
    unavailable_sources: list[str]


def evaluate(evidence: TickEvidence, history: list[Verdict]) -> Verdict:
    if _is_blind(evidence):
        return "YELLOW"
    flagged_before = bool(history) and history[-1] != "GREEN"
    if evidence.sentry_error_level_issues:
        return "RED" if flagged_before else "YELLOW"
    return _rate_or_other_verdict(evidence, flagged_before)


def _is_blind(evidence: TickEvidence) -> bool:
    no_baseline = evidence.baseline_error_count is None
    return (
        no_baseline
        or bool(evidence.unavailable_sources)
        or _zero_baseline_with_errors(evidence)
    )


def _zero_baseline_with_errors(evidence: TickEvidence) -> bool:
    return evidence.baseline_error_count == 0 and evidence.error_count > 0


def _ratio(evidence: TickEvidence) -> float:
    if not evidence.baseline_error_count:
        return 0.0
    return evidence.error_count / evidence.baseline_error_count


def _rate_or_other_verdict(evidence: TickEvidence, flagged_before: bool) -> Verdict:
    ratio = _ratio(evidence)
    if ratio > RATE_RED and flagged_before:
        return "RED"
    if ratio > RATE_YELLOW or evidence.new_sentry_issues or evidence.smoke_failures:
        return "YELLOW"
    return "GREEN"
