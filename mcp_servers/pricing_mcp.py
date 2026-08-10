#!/usr/bin/env python3
"""
pricing_mcp.py

Custom FastMCP Python server to compute sizing recommendations,
regional billing rates, and cost estimation reports for GCP Backup and DR.
"""

import os
import sys
import json

# Try importing FastMCP from mcp.server.fastmcp
try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Safe mock class if running in an environment without mcp installed
    print("Warning: 'mcp' SDK not found. Running in mock-server standby mode.", file=sys.stderr)
    class FastMCP:
        def __init__(self, name):
            self.name = name
        def tool(self):
            return lambda func: func


# Initialize FastMCP Server
mcp = FastMCP("pricing_mcp")

# Regional Pricing Directory
REGIONAL_RATES = {
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

DEFAULT_RATES = {
    "storage_rate_per_gb": 0.0280,
    "egress_rate_per_gb": 0.130,
    "management_fee_per_gb": 0.010,
    "currency": "USD"
}


def get_rates_for_region(region: str) -> dict:
    """
    Helper to look up rates for a region with standard default fallback.
    """
    clean_region = region.lower().strip()
    return REGIONAL_RATES.get(clean_region, DEFAULT_RATES)


# --- FASTMCP TOOL BINDINGS ---

@mcp.tool()
def get_regional_bdr_rates(region: str) -> str:
    """
    Retrieves the unit pricing tables for GCP Backup & DR in the specified region.
    
    Args:
        region: The GCP region name (e.g., us-central1, europe-west3).
        
    Returns:
        JSON string containing BDR storage, replication egress, and management rates.
    """
    rates = get_rates_for_region(region)
    payload = {
        "region": region,
        "rates": rates,
        "note": "Unit rates are charged monthly per GB of protected front-end capacity or back-end storage."
    }
    return json.dumps(payload, indent=2)


@mcp.tool()
def estimate_vault_storage_cost(size_gib: float, retention_days: int, region: str) -> str:
    """
    Estimates the monthly and annual spend for a Backup Vault based on workload size.
    
    Args:
        size_gib: Front-end backup workload size in GiB.
        retention_days: Active backup retention lifespan in days.
        region: GCP region name (e.g., us-central1).
        
    Returns:
        JSON string summarizing estimated storage costs, license fees, and total spend.
    """
    rates = get_rates_for_region(region)
    
    storage_rate = rates["storage_rate_per_gb"]
    mgt_rate = rates["management_fee_per_gb"]
    
    # Simple pricing projection formula:
    # Monthly Cost = (size_gib * storage_rate) + (size_gib * mgt_rate)
    monthly_storage = size_gib * storage_rate
    monthly_management = size_gib * mgt_rate
    monthly_total = monthly_storage + monthly_management
    
    # Cumulative calculation factor if data accumulates over the retention cycle
    # Assuming standard daily change rate of 2% added to storage over retention
    accumulated_storage_gib = size_gib * (1.0 + (0.02 * min(retention_days, 365)))
    accumulated_monthly_storage = accumulated_storage_gib * storage_rate
    accumulated_monthly_total = accumulated_monthly_storage + monthly_management
    
    payload = {
        "parameters": {
            "size_gib": size_gib,
            "retention_days": retention_days,
            "region": region,
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
    rates = get_rates_for_region(region)
    storage_rate = rates["storage_rate_per_gb"]
    
    # Calculate effective cumulative storage sizes based on daily 2% change rate
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
        "parameters": {
            "baseline_gib": baseline_gib,
            "current_retention_days": current_retention_days,
            "proposed_retention_days": proposed_retention_days,
            "region": region,
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
    if "FastMCP" in globals() and hasattr(mcp, "run"):
        mcp.run()
    else:
        # CLI Standby evaluation test
        print("FastMCP pricing execution interface currently mocked.", file=sys.stderr)
        print(get_regional_bdr_rates("us-central1"))
        print(estimate_vault_storage_cost(10240, 30, "us-central1"))
        print(calculate_retention_spend_delta(10240, 30, 90, "us-central1"))
