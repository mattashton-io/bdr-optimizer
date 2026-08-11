# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Specialist Agent for File Sizing & Asset Analysis (bdr-planner)."""

import os
import sys
import json
import csv
from typing import Dict, Any, List, Optional
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

MODEL = os.environ.get("MODEL_NAME", "gemini-2.5-flash")

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


def parse_and_normalize_inventory(source_type: str, file_path: str, vdisk_path: Optional[str] = None) -> str:
    """Parses on-premises spreadsheet inventory (RVTools CSV/XLSX or Migration Center CSV) and normalizes it.

    Args:
        source_type: One of 'vmware-csv', 'vmware-xlsx', or 'migration-center-csv'.
        file_path: Absolute or relative path to the primary inventory file (e.g., vInfo.csv, RVTools.xlsx, vmInfo.csv).
        vdisk_path: Optional path to diskInfo.csv or vDisk.csv for disk size aggregation.

    Returns:
        JSON string summary of normalized workloads and output artifact path.
    """
    if not os.path.exists(file_path):
        return json.dumps({
            "status": "ERROR",
            "error_type": "FILE_NOT_FOUND_ERROR",
            "message": f"Input file not found at path: {file_path}",
            "remediation": "Verify the file path exists and re-run with the correct file location."
        }, indent=2)

    workloads = []

    if source_type in ["vmware-csv", "vmware-xlsx"]:
        if source_type == "vmware-xlsx":
            try:
                import openpyxl
            except ImportError:
                return json.dumps({
                    "status": "ERROR",
                    "error_type": "MISSING_DEPENDENCY_ERROR",
                    "component": "bdr-planner (XLSX Parser)",
                    "cause": "Package 'openpyxl' is required to parse VMware RVTools .xlsx workbooks.",
                    "remediation": "Install openpyxl by running: pip install openpyxl"
                }, indent=2)
            
            wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
            if "vInfo" not in wb.sheetnames:
                return json.dumps({
                    "status": "ERROR",
                    "error_type": "SCHEMA_VALIDATION_ERROR",
                    "component": "bdr-planner (RVTools Parser)",
                    "cause": "Sheet 'vInfo' not found in uploaded workbook.",
                    "remediation": "Ensure the uploaded Excel workbook is an RVTools export containing the 'vInfo' worksheet."
                }, indent=2)
            sheet = wb["vInfo"]
            rows_iter = sheet.iter_rows(values_only=True)
            headers = [str(h).strip() for h in next(rows_iter, []) if h is not None]
            col_map = {h: i for i, h in enumerate(headers)}

            for r in rows_iter:
                if not r or r[0] is None:
                    continue
                vm_name = str(r[col_map.get("VM", 0)] or "unknown-vm")
                cpus = int(r[col_map.get("CPUs", 1)] or 0)
                mem_mib = float(r[col_map.get("Memory", 0)] or 0)
                disk_mib = float(r[col_map.get("Total disk capacity MiB", 0)] or 0)
                uuid = str(r[col_map.get("VM UUID", 0)] or r[col_map.get("VM ID", 0)] or vm_name)
                os_name = str(r[col_map.get("OS according to the configuration file", 0)] or "unknown-os")

                workloads.append({
                    "source_id": uuid,
                    "name": vm_name,
                    "cpus": cpus,
                    "memory_gib": round(mem_mib / 1024.0, 2),
                    "total_disk_gib": round(disk_mib / 1024.0, 2),
                    "os_name": os_name,
                    "hypervisor": "VMware"
                })

        else: # vmware-csv
            with open(file_path, mode='r', encoding='utf-8-sig') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    vm_name = row.get("VM") or "unknown-vm"
                    try:
                        disk_mib = float(row.get("Total disk capacity MiB", 0) or row.get("Provisioned MiB", 0))
                        total_disk_gib = disk_mib / 1024.0
                    except (ValueError, TypeError):
                        total_disk_gib = 0.0
                    try:
                        mem_mib = float(row.get("Memory", 0))
                        mem_gib = mem_mib / 1024.0
                    except (ValueError, TypeError):
                        mem_gib = 0.0
                    try:
                        cpus = int(row.get("CPUs", 0))
                    except (ValueError, TypeError):
                        cpus = 0

                    workloads.append({
                        "source_id": row.get("VM UUID") or row.get("VM ID") or vm_name,
                        "name": vm_name,
                        "cpus": cpus,
                        "memory_gib": round(mem_gib, 2),
                        "total_disk_gib": round(total_disk_gib, 2),
                        "os_name": row.get("OS according to the configuration file") or "unknown-os",
                        "hypervisor": "VMware"
                    })

    elif source_type == "migration-center-csv":
        disk_totals = {}
        if vdisk_path and os.path.exists(vdisk_path):
            with open(vdisk_path, mode='r', encoding='utf-8-sig') as f:
                d_reader = csv.DictReader(f)
                for d_row in d_reader:
                    mid = d_row.get("MachineId")
                    try:
                        size_gib = float(d_row.get("SizeInGib", 0))
                    except (ValueError, TypeError):
                        size_gib = 0.0
                    disk_totals[mid] = disk_totals.get(mid, 0.0) + size_gib

        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                mid = row.get("MachineId") or "unknown-id"
                try:
                    cpus = int(row.get("AllocatedProcessorCoreCount", 0))
                except (ValueError, TypeError):
                    cpus = 0
                try:
                    mem_gib = float(row.get("MemoryGiB", 0))
                except (ValueError, TypeError):
                    mem_gib = 0.0
                try:
                    allocated_disk = float(row.get("TotalDiskAllocatedGiB", 0))
                except (ValueError, TypeError):
                    allocated_disk = 0.0
                
                total_disk_gib = disk_totals.get(mid, allocated_disk)
                is_physical = str(row.get("IsPhysical", "false")).lower() == "true"
                hypervisor = "Physical" if is_physical else "Hyper-V"

                workloads.append({
                    "source_id": mid,
                    "name": row.get("MachineName") or "unknown-machine",
                    "cpus": cpus,
                    "memory_gib": round(mem_gib, 2),
                    "total_disk_gib": round(total_disk_gib, 2),
                    "os_name": row.get("OsName") or "unknown-os",
                    "hypervisor": hypervisor
                })
    else:
        return json.dumps({
            "status": "ERROR",
            "error_type": "UNSUPPORTED_SOURCE_TYPE",
            "message": f"Unsupported source_type '{source_type}'. Supported: vmware-csv, vmware-xlsx, migration-center-csv.",
            "remediation": "Provide one of the supported source types: 'vmware-csv', 'vmware-xlsx', or 'migration-center-csv'."
        }, indent=2)

    output_path = "normalized_workloads.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"source_type": source_type, "workloads": workloads}, f, indent=2)

    total_storage = sum(w["total_disk_gib"] for w in workloads)
    return json.dumps({
        "status": "SUCCESS",
        "workloads_parsed_count": len(workloads),
        "total_storage_gib": round(total_storage, 2),
        "output_artifact": output_path
    }, indent=2)


def get_regional_rates(region: str) -> str:
    """Fetches GCP Backup & DR unit pricing rates for a specific region.

    Args:
        region: Target GCP region name (e.g., us-central1, us-east1, europe-west3, asia-east1).

    Returns:
        JSON string containing regional storage, egress, and management licensing rates.
    """
    clean_region = region.lower().strip()
    if clean_region not in REGIONAL_RATES:
        supported = list(REGIONAL_RATES.keys())
        return json.dumps({
            "status": "ERROR",
            "error_type": "UNSUPPORTED_REGION_ERROR",
            "message": f"Region '{region}' is not currently in the regional pricing table.",
            "supported_regions": supported,
            "remediation": f"Select one of the supported regions: {', '.join(supported)}."
        }, indent=2)

    return json.dumps({
        "status": "SUCCESS",
        "region": clean_region,
        "rates": REGIONAL_RATES[clean_region]
    }, indent=2)


def estimate_bdr_costs(size_gib: float, region: str = "us-central1") -> str:
    """Calculates multi-tier BDR storage and licensing costs across 30-Day, 90-Day, and 365-Day retention windows.

    Args:
        size_gib: Total front-end backup workload size in GiB.
        region: GCP region name (defaults to us-central1).

    Returns:
        JSON string with comparative cost estimates for 30-day, 90-day, and 365-day retention.
    """
    clean_region = region.lower().strip()
    if clean_region not in REGIONAL_RATES:
        rates = REGIONAL_RATES["us-central1"]
        region_note = f"Region '{region}' defaulted to us-central1 benchmark rates."
    else:
        rates = REGIONAL_RATES[clean_region]
        region_note = f"Rates applied for region: {clean_region}"

    storage_rate = rates["storage_rate_per_gb"]
    mgt_rate = rates["management_fee_per_gb"]

    monthly_storage_30 = size_gib * storage_rate
    monthly_management = size_gib * mgt_rate
    monthly_total_30 = monthly_storage_30 + monthly_management

    accum_90 = size_gib * (1.0 + (0.02 * 90))
    monthly_storage_90 = accum_90 * storage_rate
    monthly_total_90 = monthly_storage_90 + monthly_management

    accum_365 = size_gib * (1.0 + (0.02 * 365))
    monthly_storage_365 = accum_365 * storage_rate
    monthly_total_365 = monthly_storage_365 + monthly_management

    report = {
        "scope": "Pre-Migration Sizing Estimation",
        "region": clean_region,
        "region_note": region_note,
        "base_workload_size_gib": size_gib,
        "retention_scenarios": {
            "30_day_retention": {
                "effective_storage_gib": round(size_gib, 2),
                "monthly_storage_cost": round(monthly_storage_30, 2),
                "monthly_license_cost": round(monthly_management, 2),
                "monthly_total": round(monthly_total_30, 2),
                "projected_annual_total": round(monthly_total_30 * 12, 2)
            },
            "90_day_retention": {
                "effective_storage_gib": round(accum_90, 2),
                "monthly_storage_cost": round(monthly_storage_90, 2),
                "monthly_license_cost": round(monthly_management, 2),
                "monthly_total": round(monthly_total_90, 2),
                "projected_annual_total": round(monthly_total_90 * 12, 2)
            },
            "365_day_retention": {
                "effective_storage_gib": round(accum_365, 2),
                "monthly_storage_cost": round(monthly_storage_365, 2),
                "monthly_license_cost": round(monthly_management, 2),
                "monthly_total": round(monthly_total_365, 2),
                "projected_annual_total": round(monthly_total_365 * 12, 2)
            }
        }
    }

    with open("cost_estimate_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return json.dumps(report, indent=2)


def calculate_retention_delta(baseline_gib: float, current_days: int, proposed_days: int, region: str = "us-central1") -> str:
    """Computes the cost differential when expanding or reducing snapshot retention lifespans.

    Args:
        baseline_gib: Workload data size in GiB.
        current_days: Current retention period in days.
        proposed_days: Target/proposed retention period in days.
        region: GCP Region name (defaults to us-central1).

    Returns:
        JSON string detailing monthly and annual savings or cost increases.
    """
    clean_region = region.lower().strip()
    rates = REGIONAL_RATES.get(clean_region, REGIONAL_RATES["us-central1"])
    storage_rate = rates["storage_rate_per_gb"]

    current_effective = baseline_gib * (1.0 + (0.02 * current_days))
    proposed_effective = baseline_gib * (1.0 + (0.02 * proposed_days))

    current_cost = current_effective * storage_rate
    proposed_cost = proposed_effective * storage_rate
    monthly_delta = proposed_cost - current_cost

    direction = "INCREASE" if monthly_delta >= 0 else "SAVINGS (REDUCTION)"
    return json.dumps({
        "direction": direction,
        "monthly_delta_usd": round(abs(monthly_delta), 2),
        "annual_delta_usd": round(abs(monthly_delta * 12), 2),
        "current_monthly_storage_usd": round(current_cost, 2),
        "proposed_monthly_storage_usd": round(proposed_cost, 2)
    }, indent=2)


root_agent = Agent(
    name="bdr_planner",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the BDR Planner Specialist Agent (bdr-planner).
Your purpose is to parse on-premises asset inventory spreadsheets (RVTools, Migration Center), classify workloads into BDR Protection Tiers (Tier 1 Gold, Tier 2 Silver, Tier 3 Bronze), and calculate accurate pre-migration Backup & DR cost estimations.

Follow these strict operating rules:
1. Parse uploaded inventory files using the parse_and_normalize_inventory tool.
2. In case of missing dependencies or file schema errors, surface clear, developer-friendly error messages with remediation instructions.
3. Compute BDR storage, licensing, and retention projections using estimate_bdr_costs and calculate_retention_delta.
4. Always generate structured markdown comparison tables for 30-Day, 90-Day, and 365-Day retention windows in your responses.
""",
    tools=[
        parse_and_normalize_inventory,
        get_regional_rates,
        estimate_bdr_costs,
        calculate_retention_delta
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)

