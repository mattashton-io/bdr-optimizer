#!/usr/bin/env python3
"""
pricing_mcp.py

FastMCP Python server exposing sizing recommendations, regional billing rates,
and cost estimation calculations for GCP Backup and DR.
Adheres strictly to spec.md (No silent defaults, fail-fast regional validation).
"""

import os
import sys
import json
from typing import Dict, Any

# Strict Dependency Check: FastMCP / MCPServer (MCP 1.x & 2.x compatible)
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise ImportError(
            "\n================================================================================\n"
            "[BDR-OPTIMIZER ERROR] MISSING_DEPENDENCY_ERROR: 'mcp' package is not installed.\n"
            "================================================================================\n"
            "Component:   pricing_mcp (FastMCP Server)\n"
            "Cause:       ModuleNotFoundError: No module named 'mcp'\n"
            "Impact:      Cannot initialize FastMCP pricing tool server.\n\n"
            "Remediation:\n"
            "  1. Install the mcp package: pip install \"mcp>=1.0.0\"\n"
            "  2. Ensure the active virtual environment (.venv-bdr) is activated.\n"
            "================================================================================\n"
        ) from exc


# Initialize FastMCP Server
mcp = FastMCP("pricing_mcp")

# Regional Pricing Directory according to spec.md Section 7
REGIONAL_RATES: Dict[str, Dict[str, Any]] = {
    "us-central1": {
        "storage_rate_per_gb": 0.0260,
        "egress_rate_per_gb": 0.120,
        "management_fee_per_gb": 0.010,
        "currency": "USD"
    },
    "us-east1": {
        "storage_rate_per_gb": 0.0270,
        "egress_rate_per_gb": 0.120,
        "management_fee_per_gb": 0.010,
        "currency": "USD"
    },
    "europe-west3": {
        "storage_rate_per_gb": 0.0320,
        "egress_rate_per_gb": 0.150,
        "management_fee_per_gb": 0.0120,
        "currency": "USD"
    },
    "asia-east1": {
        "storage_rate_per_gb": 0.0310,
        "egress_rate_per_gb": 0.140,
        "management_fee_per_gb": 0.0110,
        "currency": "USD"
    }
}


def _validate_region(region: str) -> tuple[bool, Dict[str, Any] | str]:
    """Validates if region exists in the catalog without silent defaults."""
    clean_region = region.lower().strip()
    if clean_region not in REGIONAL_RATES:
        supported = list(REGIONAL_RATES.keys())
        return False, {
            "status": "ERROR",
            "error_type": "UNSUPPORTED_REGION_ERROR",
            "component": "pricing_mcp",
            "message": f"Region '{region}' is not currently in the regional pricing table.",
            "supported_regions": supported,
            "remediation": f"Select one of the supported GCP regions: {', '.join(supported)}."
        }
    return True, clean_region


# --- FASTMCP TOOL BINDINGS ---

@mcp.tool()
def get_regional_bdr_rates(region: str) -> str:
    """
    Retrieves the unit pricing tables for GCP Backup & DR in the specified region.

    Args:
        region: The GCP region name (e.g., us-central1, us-east1, europe-west3, asia-east1).

    Returns:
        JSON string containing BDR storage, replication egress, and management rates.
    """
    valid, res = _validate_region(region)
    if not valid:
        return json.dumps(res, indent=2)

    clean_region = str(res)
    rates = REGIONAL_RATES[clean_region]
    payload = {
        "status": "SUCCESS",
        "region": clean_region,
        "rates": rates,
        "note": "Unit rates are charged monthly per GB of protected front-end capacity or back-end storage."
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def estimate_vault_storage_cost(size_gib: float, retention_days: int, region: str = "us-central1") -> str:
    """
    Estimates monthly and annual spend for a Backup Vault based on workload size and retention.
    Computes baseline vs retention accumulation projections (assuming 2%/day daily change rate).

    Args:
        size_gib: Front-end backup workload size in GiB.
        retention_days: Active backup retention lifespan in days.
        region: GCP region name (defaults to us-central1).

    Returns:
        JSON string summarizing estimated storage costs, license fees, and total spend.
    """
    valid, res = _validate_region(region)
    if not valid:
        return json.dumps(res, indent=2)

    clean_region = str(res)
    rates = REGIONAL_RATES[clean_region]

    storage_rate = rates["storage_rate_per_gb"]
    mgt_rate = rates["management_fee_per_gb"]

    monthly_storage = size_gib * storage_rate
    monthly_management = size_gib * mgt_rate
    monthly_total = monthly_storage + monthly_management

    # Accumulation across retention using standard daily change rate of 2%
    accumulated_storage_gib = size_gib * (1.0 + (0.02 * retention_days))
    accumulated_monthly_storage = accumulated_storage_gib * storage_rate
    accumulated_monthly_total = accumulated_monthly_storage + monthly_management

    payload = {
        "status": "SUCCESS",
        "parameters": {
            "size_gib": size_gib,
            "retention_days": retention_days,
            "region": clean_region,
            "currency": rates["currency"]
        },
        "rates": {
            "storage_rate_per_gb": storage_rate,
            "management_rate_per_gb": mgt_rate
        },
        "base_cost_estimate": {
            "monthly_storage_only": round(monthly_storage, 2),
            "monthly_licensing_only": round(monthly_management, 2),
            "monthly_total": round(monthly_total, 2),
            "annual_total": round(monthly_total * 12, 2)
        },
        "adjusted_retention_accumulation_estimate": {
            "total_effective_storage_gib": round(accumulated_storage_gib, 2),
            "monthly_total_with_change_rate": round(accumulated_monthly_total, 2),
            "annual_total_with_change_rate": round(accumulated_monthly_total * 12, 2),
            "assumed_daily_change_rate": "2.0%"
        }
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def calculate_retention_spend_delta(baseline_gib: float, current_retention_days: int, proposed_retention_days: int, region: str = "us-central1") -> str:
    """
    Computes the financial cost delta when extending or reducing snapshot retention windows.

    Args:
        baseline_gib: Workload data footprint in GiB.
        current_retention_days: Existing retention window in days.
        proposed_retention_days: Proposed/Target retention window in days.
        region: GCP Region name (defaults to us-central1).

    Returns:
        JSON string indicating the increase or savings in monthly and annual costs.
    """
    valid, res = _validate_region(region)
    if not valid:
        return json.dumps(res, indent=2)

    clean_region = str(res)
    rates = REGIONAL_RATES[clean_region]
    storage_rate = rates["storage_rate_per_gb"]

    current_multiplier = 1.0 + (0.02 * current_retention_days)
    proposed_multiplier = 1.0 + (0.02 * proposed_retention_days)

    current_effective_gib = baseline_gib * current_multiplier
    proposed_effective_gib = baseline_gib * proposed_multiplier

    current_cost = current_effective_gib * storage_rate
    proposed_cost = proposed_effective_gib * storage_rate

    monthly_delta = proposed_cost - current_cost
    annual_delta = monthly_delta * 12

    direction = "INCREASE" if monthly_delta >= 0 else "SAVINGS (REDUCTION)"

    payload = {
        "status": "SUCCESS",
        "parameters": {
            "baseline_gib": baseline_gib,
            "current_retention_days": current_retention_days,
            "proposed_retention_days": proposed_retention_days,
            "region": clean_region,
            "currency": rates["currency"]
        },
        "effective_storage_analysis": {
            "current_effective_gib": round(current_effective_gib, 2),
            "proposed_effective_gib": round(proposed_effective_gib, 2),
            "current_monthly_storage_cost": round(current_cost, 2),
            "proposed_monthly_storage_cost": round(proposed_cost, 2)
        },
        "financial_delta": {
            "direction": direction,
            "monthly_delta": round(abs(monthly_delta), 2),
            "annual_delta": round(abs(annual_delta), 2)
        }
    }
    return json.dumps(payload, indent=2)


if __name__ == "__main__":
    mcp.run()
