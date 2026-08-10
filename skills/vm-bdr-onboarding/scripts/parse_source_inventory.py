#!/usr/bin/env python3
"""
parse_source_inventory.py

Ingests heterogeneous asset inventories (VMware RVTools CSV/XLSX or Migration Center CSVs),
validates exact column schemas, and outputs a normalized JSON artifact 'normalized_workloads.json'.
"""

import os
import sys
import json
import csv
import argparse

# Column Definitions for Validation
VINFO_COLS = [
    "VM", "Powerstate", "Template", "Config status", "DNS Name", "Connection state",
    "Guest state", "CPUs", "Memory", "Active Memory", "NICs", "Disks",
    "Total disk capacity MiB", "Provisioned MiB", "In Use MiB", "Primary IP Address",
    "Network #1", "Datacenter", "Cluster", "Host", "Folder",
    "OS according to the configuration file", "OS according to the VMware Tools",
    "VM ID", "VM UUID", "VI SDK Server", "VI SDK API Version"
]

VCPU_COLS = [
    "VM", "Powerstate", "CPUs", "Sockets", "Cores p/s", "Cluster", "Host",
    "OS according to the configuration file", "OS according to the VMware Tools",
    "VM ID", "VM UUID", "VI SDK Server"
]

VMEMORY_COLS = [
    "VM", "Powerstate", "Size MiB", "Consumed", "Cluster", "Host",
    "OS according to the configuration file", "VM ID", "VM UUID", "VI SDK Server"
]

VDISK_COLS = [
    "VM", "Powerstate", "Disk", "Disk Key", "Capacity MiB", "Disk Mode", "Thin",
    "Controller", "Disk Path", "Raw Comp. Mode", "Datacenter", "Cluster", "Host",
    "OS according to the configuration file", "OS according to the VMware Tools",
    "VM ID", "VM UUID", "VI SDK Server"
]

MC_VM_INFO_COLS = [
    "MachineId", "MachineName", "PrimaryIPAddress(optional)", "PrimaryMACAddress(optional)",
    "PublicIPAddress(optional)", "IpAddressListSemiColonDelimited(optional)",
    "TotalDiskAllocatedGiB", "TotalDiskUsedGiB", "MachineTypeLabel(optional)",
    "AllocatedProcessorCoreCount", "MemoryGiB", "HostingLocation(optional)",
    "OsType(optional)", "OsPublisher(optional)", "OsName", "OsVersion(optional)",
    "MachineStatus(optional)", "ProvisioningState(optional)", "CreateDate(optional)",
    "IsPhysical"
]

MC_DISK_INFO_COLS = [
    "MachineId", "DiskLabel", "SizeInGib", "UsedInGib", "StorageTypeLabel"
]

MC_PERF_INFO_COLS = [
    "MachineId", "TimeStamp", "CpuUtilizationPercentage",
    "MemoryUtilizationPercentage(optional)", "AvailableMemoryBytes",
    "DiskReadOperationsPerSec", "DiskWriteOperationsPerSec",
    "NetworkBytesPerSecSent", "NetworkBytesPerSecReceived"
]


def validate_headers(headers, expected, file_label):
    """
    Validates that all expected columns exist in the headers.
    """
    headers_set = set(h.strip() for h in headers if h)
    expected_set = set(expected)
    missing = expected_set - headers_set
    if missing:
        print(f"Error: Missing columns in {file_label}: {sorted(list(missing))}", file=sys.stderr)
        print(f"Expected: {expected}", file=sys.stderr)
        print(f"Found: {headers}", file=sys.stderr)
        sys.exit(1)
    print(f"Successfully validated schema for {file_label}.")


def parse_csv_headers_and_rows(file_path):
    """
    Reads CSV file headers and returns both headers and rows as dictionaries.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        sys.exit(1)
        
    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        try:
            headers = next(reader)
        except StopIteration:
            print(f"Error: File {file_path} is empty", file=sys.stderr)
            sys.exit(1)
            
    # Open again to read rows as DictReader to preserve encoding-sig handling
    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        dict_reader = csv.DictReader(f)
        rows = list(dict_reader)
        
    return [h.strip() for h in headers if h], rows


def handle_vmware_csv(vinfo_path, vcpu_path=None, vmemory_path=None, vdisk_path=None):
    """
    Parses and processes VMware RVTools exported CSVs.
    """
    print(f"Processing VMware RVTools CSV: {vinfo_path}")
    vinfo_headers, vinfo_rows = parse_csv_headers_and_rows(vinfo_path)
    validate_headers(vinfo_headers, VINFO_COLS, "vInfo.csv")
    
    # Optional sub-tab parsing
    if vcpu_path:
        vcpu_headers, _ = parse_csv_headers_and_rows(vcpu_path)
        validate_headers(vcpu_headers, VCPU_COLS, "vCPU.csv")
    if vmemory_path:
        vmem_headers, _ = parse_csv_headers_and_rows(vmemory_path)
        validate_headers(vmem_headers, VMEMORY_COLS, "vMemory.csv")
    if vdisk_path:
        vdisk_headers, _ = parse_csv_headers_and_rows(vdisk_path)
        validate_headers(vdisk_headers, VDISK_COLS, "vDisk.csv")
        
    normalized_workloads = []
    
    for row in vinfo_rows:
        # Convert capacities
        try:
            total_disk_mib = float(row.get("Total disk capacity MiB", 0))
            total_disk_gib = total_disk_mib / 1024.0
        except ValueError:
            total_disk_gib = 0.0
            
        try:
            mem_mib = float(row.get("Memory", 0))
            memory_gib = mem_mib / 1024.0
        except ValueError:
            memory_gib = 0.0
            
        try:
            cpus = int(row.get("CPUs", 0))
        except ValueError:
            cpus = 0
            
        normalized_workloads.append({
            "source_id": row.get("VM UUID") or row.get("VM ID") or "unknown-uuid",
            "name": row.get("VM") or "unknown-vm",
            "cpus": cpus,
            "memory_gib": round(memory_gib, 2),
            "total_disk_gib": round(total_disk_gib, 2),
            "os_name": row.get("OS according to the configuration file") or "unknown-os",
            "hypervisor": "VMware"
        })
        
    return normalized_workloads


def handle_migration_center_csv(vminfo_path, diskinfo_path, perfinfo_path=None):
    """
    Parses and processes Migration Center compliant CSVs.
    """
    print(f"Processing Migration Center CSV: {vminfo_path}")
    vm_headers, vm_rows = parse_csv_headers_and_rows(vminfo_path)
    validate_headers(vm_headers, MC_VM_INFO_COLS, "vmInfo.csv")
    
    disk_headers, disk_rows = parse_csv_headers_and_rows(diskinfo_path)
    validate_headers(disk_headers, MC_DISK_INFO_COLS, "diskInfo.csv")
    
    if perfinfo_path:
        perf_headers, _ = parse_csv_headers_and_rows(perfinfo_path)
        validate_headers(perf_headers, MC_PERF_INFO_COLS, "perfInfo.csv")
        
    # Build disk mapping per machine ID
    disk_totals = {}
    for row in disk_rows:
        mid = row.get("MachineId")
        try:
            size_gib = float(row.get("SizeInGib", 0))
        except ValueError:
            size_gib = 0.0
        disk_totals[mid] = disk_totals.get(mid, 0.0) + size_gib
        
    normalized_workloads = []
    
    for row in vm_rows:
        mid = row.get("MachineId")
        
        try:
            cpus = int(row.get("AllocatedProcessorCoreCount", 0))
        except ValueError:
            cpus = 0
            
        try:
            mem_gib = float(row.get("MemoryGiB", 0))
        except ValueError:
            mem_gib = 0.0
            
        # Total disk can come from disk totals or fallback to TotalDiskAllocatedGiB
        try:
            allocated_disk = float(row.get("TotalDiskAllocatedGiB", 0))
        except ValueError:
            allocated_disk = 0.0
            
        total_disk_gib = disk_totals.get(mid, allocated_disk)
        
        is_physical_str = str(row.get("IsPhysical", "false")).lower()
        hypervisor = "Other" if is_physical_str == "true" else "Hyper-V"
        
        normalized_workloads.append({
            "source_id": mid,
            "name": row.get("MachineName") or "unknown-machine",
            "cpus": cpus,
            "memory_gib": round(mem_gib, 2),
            "total_disk_gib": round(total_disk_gib, 2),
            "os_name": row.get("OsName") or "unknown-os",
            "hypervisor": hypervisor
        })
        
    return normalized_workloads


def handle_vmware_xlsx(xlsx_path):
    """
    Parses VMware RVTools XLSX using openpyxl or pandas if available.
    """
    print(f"Processing VMware RVTools XLSX: {xlsx_path}")
    try:
        import openpyxl
    except ImportError:
        print("Error: 'openpyxl' library is required to parse XLSX files.", file=sys.stderr)
        print("Please run: pip install openpyxl", file=sys.stderr)
        sys.exit(1)
        
    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    if "vInfo" not in wb.sheetnames:
        print("Error: XLSX file must contain a 'vInfo' sheet.", file=sys.stderr)
        sys.exit(1)
        
    sheet = wb["vInfo"]
    rows_iter = sheet.iter_rows(values_only=True)
    try:
        headers = next(rows_iter)
    except StopIteration:
        print("Error: 'vInfo' sheet is empty.", file=sys.stderr)
        sys.exit(1)
        
    headers = [str(h).strip() for h in headers if h is not None]
    validate_headers(headers, VINFO_COLS, "vInfo (XLSX)")
    
    # Map headers to column indices
    col_map = {h: i for i, h in enumerate(headers)}
    
    normalized_workloads = []
    for r in rows_iter:
        if not r or r[0] is None:
            continue
            
        def get_val(col_name, default=""):
            idx = col_map.get(col_name)
            if idx is not None and idx < len(r):
                val = r[idx]
                return default if val is None else val
            return default
            
        try:
            total_disk_mib = float(get_val("Total disk capacity MiB", 0))
            total_disk_gib = total_disk_mib / 1024.0
        except ValueError:
            total_disk_gib = 0.0
            
        try:
            mem_mib = float(get_val("Memory", 0))
            memory_gib = mem_mib / 1024.0
        except ValueError:
            memory_gib = 0.0
            
        try:
            cpus = int(get_val("CPUs", 0))
        except ValueError:
            cpus = 0
            
        normalized_workloads.append({
            "source_id": get_val("VM UUID") or get_val("VM ID") or "unknown-uuid",
            "name": get_val("VM") or "unknown-vm",
            "cpus": cpus,
            "memory_gib": round(memory_gib, 2),
            "total_disk_gib": round(total_disk_gib, 2),
            "os_name": get_val("OS according to the configuration file") or "unknown-os",
            "hypervisor": "VMware"
        })
        
    return normalized_workloads


def main():
    parser = argparse.ArgumentParser(description="Heterogeneous Source Asset Ingestion and Normalization.")
    parser.add_argument("--source-type", choices=["vmware-csv", "vmware-xlsx", "migration-center-csv"], required=True,
                        help="Type of input source to ingest.")
    parser.add_argument("--output", default="normalized_workloads.json", help="Path to write the normalized output JSON.")
    
    # VMware CSV Options
    parser.add_argument("--vinfo", help="Path to vInfo.csv")
    parser.add_argument("--vcpu", help="Path to vCPU.csv")
    parser.add_argument("--vmemory", help="Path to vMemory.csv")
    parser.add_argument("--vdisk", help="Path to vDisk.csv")
    
    # VMware XLSX Options
    parser.add_argument("--xlsx", help="Path to RVTools XLSX file")
    
    # Migration Center Options
    parser.add_argument("--vminfo", help="Path to vmInfo.csv")
    parser.add_argument("--diskinfo", help="Path to diskInfo.csv")
    parser.add_argument("--perfinfo", help="Path to perfInfo.csv")
    
    args = parser.parse_args()
    
    workloads = []
    
    if args.source_type == "vmware-csv":
        if not args.vinfo:
            print("Error: --vinfo is required for source-type vmware-csv", file=sys.stderr)
            sys.exit(1)
        workloads = handle_vmware_csv(args.vinfo, args.vcpu, args.vmemory, args.vdisk)
        
    elif args.source_type == "vmware-xlsx":
        if not args.xlsx:
            print("Error: --xlsx is required for source-type vmware-xlsx", file=sys.stderr)
            sys.exit(1)
        workloads = handle_vmware_xlsx(args.xlsx)
        
    elif args.source_type == "migration-center-csv":
        if not args.vminfo or not args.diskinfo:
            print("Error: Both --vminfo and --diskinfo are required for source-type migration-center-csv", file=sys.stderr)
            sys.exit(1)
        workloads = handle_migration_center_csv(args.vminfo, args.diskinfo, args.perfinfo)
        
    # Output Normalized Workloads
    payload = {
        "workloads": workloads
    }
    
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        
    print(f"Successfully normalized {len(workloads)} workloads.")
    print(f"Output saved to: {args.output}")


if __name__ == "__main__":
    main()
