# **Application Development Spec Sheet: GCP Backup & Disaster Recovery (BDR) Optimizer**

## **1. Core Libraries & Dependencies**

* **Generative AI SDK:**
  * **REQUIREMENT:** Use `google.genai` instead of the deprecated `google-generativeai` package.
  * **Reasoning:** The older library is deprecated, and newer Gemini models (Gemini 3 series) are optimized for the new SDK.
* **Google Cloud SDKs & Client Libraries:**
  * **REQUIREMENT:** Use official Google Cloud client libraries (`google-cloud-compute`, `google-auth`, `google-cloud-secret-manager`).
  * **NO SILENT FALLBACKS (Zero-Tolerance Policy):**
    * **DO NOT** silently catch `ImportError` or `ModuleNotFoundError` to fall back to dummy mock classes, stubbed implementations, or silent no-ops (e.g., mock FastMCP classes or simulated auth tokens).
    * When a required package is not installed, the application/tool **MUST** fail immediately with a clear, developer-friendly error message indicating:
      1. The exact missing package name.
      2. Which component/feature requires it.
      3. The exact command to install the dependency (e.g., `pip install google-cloud-compute` or `pip install "mcp[cli]"`).
      4. The recommended virtual environment context.
* **Virtual Environment & Package Management:**
  * **REQUIREMENT:** Standardize on Python 3.11+ (recommended `python:3.13-slim` for container builds).
  * **Environment Isolation:** Use a dedicated virtual environment (e.g., `env-bdr/` or active virtualenv). Never assume packages are globally available.
  * **Required Dependencies Inventory:**
    * `mcp` / `fastmcp`: For Model Context Protocol tool servers.
    * `google-cloud-compute`: For live GCE instance discovery and disk metadata scanning.
    * `google-auth`: For authenticated GCP OAuth2/ADC token generation.
    * `pandas` & `openpyxl`: For on-premises spreadsheet parsing (RVTools `.xlsx`/`.csv` and Migration Center CSVs).
    * `python-dotenv`: For loading local reference environment variables.

---

## **2. Error Handling & Developer-Friendly Messaging Standards**

* **Elimination of Silent Fallbacks:**
  * **No Silent Mock Degradation:** Do NOT automatically fall back to dry-run or mock simulation mode when live execution fails or credentials are missing, unless `--dry-run` or simulation mode was explicitly requested by the user.
  * **No Silent Default Fallbacks:** If an unrecognized region, missing column, unsupported hypervisor, or unknown configuration is passed, do NOT silently fall back to default values without logging an explicit warning or raising a structured error.
  * **Fail-Fast with Actionable Remediation:** All error messages must be actionable, explaining **what failed**, **why it failed**, and **the exact step required to fix it**.

* **Standard Error Message Template:**
  ```
  ================================================================================
  [BDR-OPTIMIZER ERROR] <ERROR_TYPE>: <BRIEF_DESCRIPTION>
  ================================================================================
  Component:   <Module/Script/MCP Tool Name>
  Cause:       <Detailed root cause>
  Impact:      <What operation was blocked>
  
  Remediation:
    1. <Actionable fix step 1, e.g. Run: pip install <package>>
    2. <Actionable fix step 2, e.g. Authenticate: gcloud auth application-default login>
    3. <Actionable fix step 3, e.g. Verify environment variable: export GCP_PROJECT_ID="your-project">
  ================================================================================
  ```

* **Error Category Specifications:**
  * **Missing Dependency (`MISSING_DEPENDENCY_ERROR`):**
    * *Example:* "Package 'google-cloud-compute' is not installed. Live GCE discovery requires this library. Run `pip install google-cloud-compute`."
  * **Authentication & IAM (`AUTH_CREDENTIALS_ERROR` / `PERMISSION_DENIED_ERROR`):**
    * *Example:* "GCP API Error 403: Caller lacks 'backupdr.backupVaults.create' permission on project 'my-project'. Ensure the service account or user has the 'roles/backupdr.admin' role."
  * **Schema Validation Failure (`SCHEMA_VALIDATION_ERROR`):**
    * *Example:* "Missing required columns in 'vInfo.csv': ['VM UUID', 'Provisioned MiB']. Expected 27 columns matching RVTools vInfo schema. Please re-export from RVTools with all standard columns enabled."
  * **Configuration & Environment (`CONFIG_ERROR`):**
    * *Example:* "Environment variable 'WEBHOOK_URL' is missing or invalid. Set 'WEBHOOK_URL=https://chat.googleapis.com/...' or pass '--webhook-url'."

---

## **3. Architecture & Multi-Agent Delegation Flow**

* **Multi-Agent Hierarchy:**
  * **`bdr-coordinator` (Root Agent - `agents/root/agent.toml`):**
    * Evaluates incoming user queries and routes them to specialist subagents according to strict intent matching rules.
    * *Rule 1 (Pre-Migration Sizing):* Route to `bdr-planner` when input contains on-prem asset files (RVTools, Migration Center CSVs).
    * *Rule 2 (Live Cloud Governance):* Route to `bdr-orchestrator` when input requests active GCP project audits or live policy associations.
    * *Rule 3 (Combined Pipeline):* Sequential execution (`bdr-planner` first for baseline, followed by `bdr-orchestrator` for live reconciliation).
  * **`bdr-planner` (Specialist Agent - `agents/planner/agent.toml`):**
    * Specializes in file sizing, hypervisor parsing, protection tier classification, and pre-migration cost estimation.
    * Uses `skills/vm-bdr-onboarding`, `skills/bdr-cost-estimator`, and `mcp_servers/pricing_mcp.py`.
  * **`bdr-orchestrator` (Specialist Agent - `agents/orchestrator/agent.toml`):**
    * Specializes in GCP infrastructure discovery, live Backup Vault management, BackupPlanAssociation (BPA) binding, and chat alerting.
    * Uses `skills/vault-orchestration`, `skills/chat-notifier`, `mcp_servers/backupdr_mcp.py`, and `mcp_servers/chat_mcp.py`.

* **Dual-Mode Execution & Reconciliation:**
  * **Mode A (Simulation Pre-Migration):** Parses on-premises inventory without requiring live GCP credentials. Generates `normalized_workloads.json` and `cost_estimate_report.json`.
  * **Mode B (Live Cloud Governance):** Connects to Google Cloud Compute and Backup-DR APIs. Generates `assets/live_cloud_inventory.json` and `bdr_association_report.json`.
  * **Dual Reporting:** When both modes are active, compile a unified two-part report (Section A: On-Premises Baseline vs. Section B: Live Cloud State). Never halt execution solely because on-prem VM names do not match live GCE instance names.

---

## **4. MCP (Model Context Protocol) Server Specifications**

* **Tool Bindings & FastMCP Implementation:**
  * Use `FastMCP` from `mcp.server.fastmcp` across all custom MCP servers:
    * `mcp_servers/backupdr_mcp.py`: GCP Backup & DR REST API tools (`list_backup_vaults`, `create_backup_vault`, `list_backup_plans`, `create_plan_association`).
    * `mcp_servers/pricing_mcp.py`: Sizing and cost calculation tools (`get_regional_bdr_rates`, `estimate_vault_storage_cost`, `calculate_retention_spend_delta`).
    * `mcp_servers/chat_mcp.py`: Messaging and notification tools (`send_bdr_summary_card`, `post_bdr_alert`).
* **Tool Documentation & Contracts:**
  * **Docstrings:** Every MCP tool function **MUST** provide clear, typed docstrings detailing `Args`, `Returns`, and behavioral expectations. AI agents rely on docstrings for tool selection and argument generation.
  * **Transport:** Support standard streamable transports (stdio / StreamableHTTPTransport) with clean JSON string outputs.
* **Explicit Error Returns in MCP Tools:**
  * MCP tools must return structured JSON error payloads containing descriptive messages and remediation guidance instead of throwing unhandled crashes or silently returning empty lists `{}`.
  * *Example MCP Error Payload:*
    ```json
    {
      "status": "ERROR",
      "error_type": "AUTHENTICATION_FAILED",
      "message": "Unable to acquire Google OAuth2 access token. google.auth.default() failed.",
      "remediation": "Run 'gcloud auth application-default login' or set the GOOGLE_APPLICATION_CREDENTIALS environment variable."
    }
    ```

---

## **5. Security, Authentication & Secrets Management**

* **Secrets Management:**
  * **REQUIREMENT:** **DO NOT** hardcode API keys, service account private keys, or passwords in source code, configuration files, or local `.env` files committed to git.
  * **Production Credential Retrieval:** Use **Google Secret Manager** (`google-cloud-secret-manager`) or Google Application Default Credentials (ADC) for all authentication in production environments.
  * **Environment Variable References:** Local `.env` files may only contain non-sensitive variable references or resource paths (e.g., `GCP_PROJECT_ID=my-project`, `GCP_REGION=us-central1`, `WEBHOOK_URL=...`).
* **Git Security:**
  * **REQUIREMENT:** Maintain a strict `.gitignore` that excludes:
    * `env*`, `.venv`, `venv/`
    * `.env`, `.env.*`
    * `*.json` (credentials, service accounts, tokens like `token.json`, `credentials.json`, `*key*.json`)
    * `__pycache__/`, `*.pyc`
    * `assets/live_cloud_inventory.json` (if containing sensitive internal hostnames/IPs)

---

## **6. Data Ingestion & Strict Schema Validation**

* **Dynamic Parsing via Code Interpreter:**
  * Do NOT use rigid, unvalidated parsers. Pass uploaded spreadsheets to `google/skills/code-interpreter` running pandas to validate headers and structure.
* **Strict Header Contracts:**
  * **VMware RVTools (`vInfo`):** `VM`, `Powerstate`, `CPUs`, `Memory`, `Active Memory`, `Disks`, `Provisioned MiB`, `In Use MiB`, `OS according to the configuration file`, `VM UUID`.
  * **VMware RVTools (`vDisk`):** `VM`, `Powerstate`, `Disk`, `Capacity MiB`, `Disk Mode`.
  * **Migration Center (`vmInfo.csv`):** `MachineId`, `MachineName`, `TotalDiskAllocatedGiB`, `TotalDiskUsedGiB`, `AllocatedProcessorCoreCount`, `MemoryGiB`, `OsName`.
  * **Migration Center (`diskInfo.csv`):** `MachineId`, `DiskLabel`, `SizeInGib`, `UsedInGib`.
  * **Migration Center (`perfInfo.csv`):** `MachineId`, `TimeStamp`, `CpuUtilizationPercentage`, `MemoryUtilizationPercentage(optional)`.
* **Validation Failure Handling:**
  * If mandatory columns are missing, immediately return a `SCHEMA_VALIDATION_ERROR` specifying exactly which columns were missing, which were detected, and the required schema template.
* **Standardized Output Artifact:**
  * Ingestion must output an artifact strictly adhering to the `normalized_workloads.json` schema (`source_type`, `workloads` array with `source_id`, `name`, `cpus`, `memory_gib`, `total_disk_gib`, `os_name`, `hypervisor`).

---

## **7. Protection Tier Classification & Cost Sizing Engine**

* **Protection Tier Rules:**
  * **Tier 1 (Gold - RPO: 15 min / RTO: 1 hr):** VM name or role contains `db`, `oracle`, `sap`, `sql`, OR CPUs $\ge 16$ and Disk $\ge 1024$ GB. (Default: Immutable, Cross-Region Vault).
  * **Tier 2 (Silver - RPO: 4 hrs / RTO: 4 hrs):** VM name or folder contains `prod`, `prd`, `staging`, `stg`. (Default: Daily, Cross-Zone Vault).
  * **Tier 3 (Bronze - RPO: 24 hrs / RTO: 24 hrs):** VM name contains `dev`, `tst`, `sandbox`, or has label `bdr-opt-out=true`. (Default: Daily, Local-only Vault).
* **Cost Calculation Mathematics:**
  * **Monthly Base Cost:** $\text{Monthly Total} = (\text{Total Disk GiB} \times \text{Storage Rate}) + (\text{Total Disk GiB} \times \text{Management Fee Rate})$.
  * **Retention Accumulation Factor:** Calculate projected data growth across standard retention tiers (30-Day, 90-Day, 365-Day) using daily change rates (default 2%/day).
  * **Regional Pricing Table:**
    * `us-central1`: Storage $\$0.0260/\text{GB}$, Management $\$0.010/\text{GB}$, Egress $\$0.120/\text{GB}$.
    * `us-east1`: Storage $\$0.0270/\text{GB}$, Management $\$0.010/\text{GB}$, Egress $\$0.120/\text{GB}$.
    * `europe-west3`: Storage $\$0.0320/\text{GB}$, Management $\$0.012/\text{GB}$, Egress $\$0.150/\text{GB}$.
    * `asia-east1`: Storage $\$0.0310/\text{GB}$, Management $\$0.011/\text{GB}$, Egress $\$0.140/\text{GB}$.
  * **Region Validation:** If an unsupported region is requested, report available regions and default pricing clearly with an informative notice.
* **Output Artifacts:**
  * Save structured calculation results to `cost_estimate_report.json`.
  * Render a comparative markdown table in chat with 30-Day, 90-Day, and 365-Day scenarios.

---

## **8. Live Governance & Mutation Safeguards**

* **Protection Gap Audit:**
  * Cross-reference discovered live GCE instances against existing BackupPlanAssociations (BPAs).
  * Explicitly flag instances missing active backup policies as **Unprotected**.
* **Mutation Confirmation Guard (Mandatory):**
  * **NEVER** execute state-changing GCP API calls (`create_backup_vault`, `create_plan_association`) without obtaining explicit user confirmation in chat.
  * Confirmation prompts must detail: Target VM name, zone, target Backup Plan ID, Vault ID, and enforced immutable retention duration.
* **Audit Logging:**
  * Append all mutation outcomes to `execution_summary.json` and `bdr_association_report.json`.

---

## **9. Notification & Chat Alerting System**

* **Multi-Platform Webhook Dispatch:**
  * Support rich formatted payloads for both **Google Chat Cards v2** and **Slack Blocks** based on webhook URL structure.
* **Severity Levels:**
  * `INFO` (Blue): General status updates and scoping reports.
  * `SUCCESS` (Green): Successful policy associations and milestone summaries.
  * `WARNING` (Yellow): Partial associations, missing GCE matches, or unprotected workloads.
  * `ERROR` (Red): API failures, permission errors, or quota exceptions.
* **Webhook Failure Handling:**
  * If webhook delivery fails (e.g. 404, 401, network timeout), output a developer-friendly error message indicating the HTTP status code, response body, and verification steps for the webhook URL.

---

## **10. ADK Artifacts & File Ingestion Architecture**

* **ADK Artifacts Standard (`https://adk.dev/artifacts/`):**
  * **User Upload Ingestion (`before_model_callback=save_files_as_artifacts`):**
    * When a user uploads a spreadsheet (e.g. `RVTools_export.xlsx`, `vInfo.csv`, `vmInfo.csv`) via the ADK UI/Playground, `save_files_as_artifacts` automatically intercepts the user message parts.
    * Calls `callback_context.save_artifact(filename, artifact=part)` so the file is stored in the session's ADK `ArtifactService` and becomes immediately visible in the **Artifacts** tab.
    * Saves a local copy in `uploads/<filename>` for direct parser tools and records metadata in `callback_context.state`.
    * Injects prompt metadata so agents proceed with automated ingestion without redundantly asking the user for the file name or hypervisor format.
  * **Artifact Inspection Tool (`load_artifacts`):**
    * All agents (`bdr-coordinator`, `bdr-planner`, `bdr-orchestrator`) must include `load_artifacts` from `google.adk.tools` in their registered toolsets.
  * **Generated Output Artifacts:**
    * `normalized_workloads.json`: Saved to ADK Artifacts by `bdr-planner` after parsing spreadsheets.
    * `cost_estimate_report.json`: Saved to ADK Artifacts by `bdr-planner` after computing 30/90/365-day retention projections.
    * `live_cloud_inventory.json`: Saved to ADK Artifacts by `bdr-orchestrator` after scanning live GCE instances.
    * `bdr_association_report.json`: Saved to ADK Artifacts by `bdr-orchestrator` upon binding BackupPlanAssociations.

