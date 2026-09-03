"""Investigation reasoning over Phase 2A deterministic evidence."""

from agent.actions import approve_action, execute_action, propose_from_report
from agent.investigate import investigate_report, investigate_spike
from agent.providers.deterministic import DeterministicReasoner
from agent.providers.llm import LLMInvestigationProvider
from agent.schema import InvestigationReport

__all__ = [
    "DeterministicReasoner",
    "InvestigationReport",
    "LLMInvestigationProvider",
    "approve_action",
    "execute_action",
    "investigate_report",
    "investigate_spike",
    "propose_from_report",
]
