import os
import sys
import json
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import mcp_servers.pricing_mcp as pricing_mcp
import mcp_servers.chat_mcp as chat_mcp
import mcp_servers.backupdr_mcp as backupdr_mcp


def test_pricing_mcp_regional_rates() -> None:
    """Verifies that pricing_mcp returns rates for supported regions and errors for unsupported."""
    res_raw = pricing_mcp.get_regional_bdr_rates("us-central1")
    data = json.loads(res_raw)
    assert data["status"] == "SUCCESS"
    assert data["region"] == "us-central1"
    assert data["rates"]["storage_rate_per_gb"] == 0.0260

    err_raw = pricing_mcp.get_regional_bdr_rates("antarctica-1")
    err_data = json.loads(err_raw)
    assert err_data["status"] == "ERROR"
    assert err_data["error_type"] == "UNSUPPORTED_REGION_ERROR"


def test_pricing_mcp_estimate_vault_storage() -> None:
    """Verifies that pricing_mcp estimates storage and retention accumulation."""
    res_raw = pricing_mcp.estimate_vault_storage_cost(size_gib=1000.0, retention_days=30, region="us-central1")
    data = json.loads(res_raw)
    assert data["status"] == "SUCCESS"
    assert data["base_cost_estimate"]["monthly_total"] == 36.00
    assert data["adjusted_retention_accumulation_estimate"]["total_effective_storage_gib"] == 1600.0


def test_chat_mcp_missing_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that chat_mcp returns structured CONFIG_ERROR when webhook URL is missing."""
    monkeypatch.delenv("WEBHOOK_URL", raising=False)
    monkeypatch.delenv("BDR_CHAT_WEBHOOK_URL", raising=False)

    res_raw = chat_mcp.send_bdr_summary_card("Title", 1, 100.0, 50.0)
    data = json.loads(res_raw)
    assert data["status"] == "ERROR"
    assert data["error_type"] == "CONFIG_ERROR"


def test_backupdr_mcp_safeguard() -> None:
    """Verifies mutation safeguards on backupdr_mcp server tools."""
    res_raw = backupdr_mcp.create_backup_vault(
        project_id="test-proj",
        location="us-central1",
        vault_id="v1",
        retention_days=30,
        user_confirmed=False
    )
    data = json.loads(res_raw)
    assert data["status"] == "MUTATION_CONFIRMATION_REQUIRED"

    bpa_raw = backupdr_mcp.create_plan_association(
        project_id="test-proj",
        location="us-central1",
        plan_id="p1",
        resource_uri="projects/test-proj/zones/us-central1-a/instances/i1",
        user_confirmed=False
    )
    bpa_data = json.loads(bpa_raw)
    assert bpa_data["status"] == "MUTATION_CONFIRMATION_REQUIRED"
