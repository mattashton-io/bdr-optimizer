# Copyright 2026 Google LLC
"""Unit tests for BDR Planner Specialist Agent."""

import os
import json
import asyncio
import pytest
from agents.planner.app.agent import (
    root_agent,
    parse_and_normalize_inventory,
    get_regional_rates,
    estimate_bdr_costs,
    calculate_retention_delta,
)


def test_planner_agent_initialization() -> None:
    """Verifies that bdr_planner agent initializes with required sizing tools."""
    assert root_agent.name == "bdr_planner"
    tool_names = [getattr(t, "__name__", getattr(t, "name", type(t).__name__)) for t in root_agent.tools]
    assert "parse_and_normalize_inventory" in tool_names
    assert "get_regional_rates" in tool_names
    assert "estimate_bdr_costs" in tool_names
    assert "calculate_retention_delta" in tool_names


def test_parse_rvtools_excel() -> None:
    """Tests parsing VMware RVTools XLSX spreadsheet export."""
    excel_path = "agents/root/uploads/RVTools_export_demo-100.xlsx"
    if not os.path.exists(excel_path):
        pytest.skip(f"Test asset {excel_path} not found")

    result_raw = asyncio.run(parse_and_normalize_inventory(file_path=excel_path))
    data = json.loads(result_raw)

    assert data["status"] == "SUCCESS"
    assert data["source_type"] == "vmware-xlsx"
    assert data["workloads_parsed_count"] == 100
    assert data["total_storage_gib"] > 0
    assert os.path.exists("normalized_workloads.json")

    with open("normalized_workloads.json", "r", encoding="utf-8") as f:
        artifact = json.load(f)
    assert artifact["source_type"] == "vmware-xlsx"
    assert len(artifact["workloads"]) == 100
    first_vm = artifact["workloads"][0]
    assert "source_id" in first_vm
    assert "name" in first_vm
    assert "cpus" in first_vm
    assert "total_disk_gib" in first_vm


def test_parse_nonexistent_file() -> None:
    """Tests proper error handling when provided spreadsheet does not exist."""
    result_raw = asyncio.run(parse_and_normalize_inventory(file_path="nonexistent/file.xlsx"))
    data = json.loads(result_raw)
    assert data["status"] == "ERROR"
    assert data["error_type"] == "FILE_NOT_FOUND_ERROR"


def test_get_regional_rates_valid_and_invalid() -> None:
    """Tests fetching regional BDR unit rates with fail-fast validation."""
    valid_raw = get_regional_rates("us-central1")
    valid_data = json.loads(valid_raw)
    assert valid_data["status"] == "SUCCESS"
    assert valid_data["region"] == "us-central1"
    assert valid_data["rates"]["storage_rate_per_gb"] == 0.0260

    invalid_raw = get_regional_rates("unsupported-region-xyz")
    invalid_data = json.loads(invalid_raw)
    assert invalid_data["status"] == "ERROR"
    assert invalid_data["error_type"] == "UNSUPPORTED_REGION_ERROR"
    assert "supported_regions" in invalid_data


def test_estimate_bdr_costs_calculation() -> None:
    """Tests multi-tier BDR storage and retention cost calculations."""
    size_gib = 1000.0  # 1000 GiB
    result_raw = asyncio.run(estimate_bdr_costs(size_gib=size_gib, region="us-central1"))
    data = json.loads(result_raw)

    assert data["status"] == "SUCCESS"
    assert data["region"] == "us-central1"
    scenarios = data["retention_scenarios"]

    # 30-day: 1000 * 0.026 = $26.00 storage + 1000 * 0.010 = $10.00 license = $36.00 total
    assert scenarios["30_day_retention"]["monthly_storage_cost"] == 26.00
    assert scenarios["30_day_retention"]["monthly_license_cost"] == 10.00
    assert scenarios["30_day_retention"]["monthly_total"] == 36.00

    # 90-day: effective storage = 1000 * (1 + 0.02 * 90) = 2800 GiB
    # monthly storage = 2800 * 0.026 = $72.80 + $10.00 = $82.80
    assert scenarios["90_day_retention"]["effective_storage_gib"] == 2800.0
    assert scenarios["90_day_retention"]["monthly_storage_cost"] == 72.80
    assert scenarios["90_day_retention"]["monthly_total"] == 82.80


def test_estimate_bdr_costs_invalid_region() -> None:
    """Verifies fail-fast error when an invalid region is provided to cost estimation."""
    result_raw = asyncio.run(estimate_bdr_costs(size_gib=1000.0, region="mars-central1"))
    data = json.loads(result_raw)
    assert data["status"] == "ERROR"
    assert data["error_type"] == "UNSUPPORTED_REGION_ERROR"


def test_calculate_retention_delta() -> None:
    """Tests retention differential calculation (increase vs savings)."""
    # Increase: 30 days to 90 days
    inc_raw = calculate_retention_delta(baseline_gib=1000.0, current_days=30, proposed_days=90, region="us-central1")
    inc_data = json.loads(inc_raw)
    assert inc_data["status"] == "SUCCESS"
    assert inc_data["direction"] == "INCREASE"
    assert inc_data["monthly_delta_usd"] > 0

    # Savings: 90 days to 30 days
    dec_raw = calculate_retention_delta(baseline_gib=1000.0, current_days=90, proposed_days=30, region="us-central1")
    dec_data = json.loads(dec_raw)
    assert dec_data["status"] == "SUCCESS"
    assert dec_data["direction"] == "SAVINGS (REDUCTION)"
    assert dec_data["monthly_delta_usd"] > 0
