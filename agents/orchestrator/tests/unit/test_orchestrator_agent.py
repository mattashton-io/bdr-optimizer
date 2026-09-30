# Copyright 2026 Google LLC
"""Unit tests for BDR Orchestrator Specialist Agent."""

import json
import asyncio
import pytest
from agents.orchestrator.app.agent import (
    root_agent,
    create_gcp_backup_vault,
    create_gcp_plan_association,
    send_chat_summary,
)


def test_orchestrator_agent_initialization() -> None:
    """Verifies that bdr_orchestrator agent initializes with required governance tools."""
    assert root_agent.name == "bdr_orchestrator"
    tool_names = [getattr(t, "__name__", getattr(t, "name", type(t).__name__)) for t in root_agent.tools]
    assert "scan_live_gce_instances" in tool_names
    assert "list_gcp_backup_vaults" in tool_names
    assert "list_gcp_backup_plans" in tool_names
    assert "create_gcp_backup_vault" in tool_names
    assert "create_gcp_plan_association" in tool_names
    assert "send_chat_summary" in tool_names


def test_create_backup_vault_mutation_safeguard() -> None:
    """Verifies that create_gcp_backup_vault blocks execution if user confirmation is missing."""
    result_raw = create_gcp_backup_vault(
        project_id="test-proj",
        location="us-central1",
        vault_id="vault-prod-gold",
        retention_days=30,
        user_confirmed=False
    )
    data = json.loads(result_raw)
    assert data["status"] == "MUTATION_CONFIRMATION_REQUIRED"
    assert "mutation_details" in data
    assert data["mutation_details"]["action"] == "CREATE_BACKUP_VAULT"
    assert data["mutation_details"]["vault_id"] == "vault-prod-gold"


def test_create_plan_association_mutation_safeguard() -> None:
    """Verifies that create_gcp_plan_association blocks execution if user confirmation is missing."""
    result_raw = asyncio.run(create_gcp_plan_association(
        project_id="test-proj",
        location="us-central1",
        plan_id="gold-db-policy",
        instance_name="prod-db-01",
        instance_self_link="https://www.googleapis.com/compute/v1/projects/test-proj/zones/us-central1-a/instances/prod-db-01",
        user_confirmed=False
    ))
    data = json.loads(result_raw)
    assert data["status"] == "MUTATION_CONFIRMATION_REQUIRED"
    assert "mutation_details" in data
    assert data["mutation_details"]["action"] == "CREATE_BACKUP_PLAN_ASSOCIATION"
    assert data["mutation_details"]["instance_name"] == "prod-db-01"


def test_send_chat_summary_missing_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that send_chat_summary returns structured CONFIG_ERROR when WEBHOOK_URL is not set."""
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.delenv("BDR_CHAT_WEBHOOK_URL", raising=False)

    result_raw = send_chat_summary(
        title="BDR Summary",
        protected_vms_count=5,
        total_storage_gib=2500.0,
        monthly_cost=85.0
    )
    data = json.loads(result_raw)
    assert data["status"] == "ERROR"
    assert data["error_type"] == "CONFIG_ERROR"
    assert "remediation" in data
