# Copyright 2026 Google LLC
"""Unit tests for BDR Root Coordinator Agent."""

import json
import pytest
from agents.root.app.agent import root_agent, classify_user_intent


def test_root_agent_initialization() -> None:
    """Verifies that bdr_coordinator agent initializes with required specialist subagents and tools."""
    assert root_agent.name == "bdr_coordinator"
    subagent_names = [s.name for s in root_agent.sub_agents]
    assert "bdr_planner" in subagent_names, "bdr_planner subagent must be attached to coordinator"
    assert "bdr_orchestrator" in subagent_names, "bdr_orchestrator subagent must be attached to coordinator"

    tool_names = [getattr(t, "__name__", getattr(t, "name", type(t).__name__)) for t in root_agent.tools]
    assert "classify_user_intent" in tool_names
    assert any("artifact" in name.lower() for name in tool_names)


@pytest.mark.parametrize(
    "query,expected_rule,expected_agent",
    [
        (
            "Here is our rvtools export spreadsheet to size backup storage costs.",
            "Rule 1 (Pre-Migration Sizing)",
            "bdr-planner"
        ),
        (
            "Please parse vmware vinfo.csv and calculate pricing estimates.",
            "Rule 1 (Pre-Migration Sizing)",
            "bdr-planner"
        ),
        (
            "Audit my live gcp project and find all unprotected compute instances.",
            "Rule 2 (Live Cloud Governance)",
            "bdr-orchestrator"
        ),
        (
            "Create a new backup vault and associate backup plan bpa-prod-db.",
            "Rule 2 (Live Cloud Governance)",
            "bdr-orchestrator"
        ),
        (
            "Upload rvtools xlsx for baseline sizing, then reconcile against live gce instances in our gcp project.",
            "Rule 3 (Combined Transition Pipeline)",
            "bdr-planner (Step 1) -> bdr-orchestrator (Step 2)"
        ),
        (
            "What is GCP Backup and DR service?",
            "General Inquiry",
            "bdr-coordinator"
        )
    ]
)
def test_classify_user_intent(query: str, expected_rule: str, expected_agent: str) -> None:
    """Tests intent classification logic according to spec.md routing rules."""
    result_raw = classify_user_intent(query)
    data = json.loads(result_raw)
    assert data["matched_rule"] == expected_rule
    assert data["recommended_agent"] == expected_agent
