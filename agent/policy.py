"""Bound investigation recommendations. No production payment actions."""

from __future__ import annotations

from agent.schema import (
    ALLOWED_ACTIONS,
    ALLOWED_VERDICTS,
    FORBIDDEN_ACTIONS,
    InvestigationReport,
)


def enforce_report_policy(report: InvestigationReport) -> InvestigationReport:
    if report.verdict not in ALLOWED_VERDICTS:
        report.verdict = "inconclusive"
        report.summary = "Verdict was outside the allowed contract and was set to inconclusive."
    if report.recommended_action.type in FORBIDDEN_ACTIONS:
        raise ValueError("Unrestricted payment or blocking actions are not allowed")
    if report.recommended_action.type not in ALLOWED_ACTIONS:
        report.recommended_action.type = "review"
        report.recommended_action.scope = "this spike window only"
        report.recommended_action.reason = "Action was reset to a bounded analyst review."
    report.human_approval_required = True
    report.confidence = min(max(float(report.confidence), 0.0), 1.0)
    return report
