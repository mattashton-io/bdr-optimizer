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

"""Root Coordinator Agent (bdr-coordinator)."""

import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.adk.tools import load_artifacts
from google.genai import types

from .app_utils.artifacts import save_files_as_artifacts

# Import subagent definitions
try:
    # Try importing relative or direct path
    parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    from planner.app.agent import root_agent as planner_agent
    from orchestrator.app.agent import root_agent as orchestrator_agent
except Exception:
    planner_agent = None
    orchestrator_agent = None

MODEL = os.environ.get("MODEL_NAME", "gemini-2.5-flash")


def classify_user_intent(query: str) -> str:
    """Evaluates the user request and determines the optimal BDR subagent routing path.

    Args:
        query: The user's query or instruction string.

    Returns:
        JSON string containing the matched intent rule, target specialist agent, and recommended action.
    """
    q_lower = query.lower()
    
    is_file_sizing = any(kw in q_lower for kw in [
        "rvtools", "csv", "xlsx", "vminfo", "diskinfo", "perfinfo",
        "pre-migration", "on-prem", "sizing", "estimate", "pricing", "cost", "vmware", "hyper-v", "upload"
    ])
    
    is_live_cloud = any(kw in q_lower for kw in [
        "live", "gce", "gcp project", "audit", "vault", "backupplan", "bpa",
        "associate", "bind", "policy", "unprotected", "compliance", "webhook", "chat"
    ])

    if is_file_sizing and is_live_cloud:
        rule = "Rule 3 (Combined Transition Pipeline)"
        target = "bdr-planner (Step 1) -> bdr-orchestrator (Step 2)"
        desc = "Dual-mode reconciliation: Run pre-migration sizing baseline with bdr-planner, then audit live GCE instances with bdr-orchestrator."
    elif is_file_sizing:
        rule = "Rule 1 (Pre-Migration Sizing)"
        target = "bdr-planner"
        desc = "Delegate to bdr-planner for spreadsheet ingestion, protection tier classification, and BDR cost projections."
    elif is_live_cloud:
        rule = "Rule 2 (Live Cloud Governance)"
        target = "bdr-orchestrator"
        desc = "Delegate to bdr-orchestrator for live GCE discovery, Backup Vault management, and BackupPlanAssociation binding."
    else:
        rule = "General Inquiry"
        target = "bdr-coordinator"
        desc = "Provide overview of GCP Backup and DR capabilities, or prompt user to upload asset files or specify a GCP project."

    return json.dumps({
        "matched_rule": rule,
        "recommended_agent": target,
        "description": desc
    }, indent=2)


subagents_list = []
if planner_agent is not None:
    subagents_list.append(planner_agent)
if orchestrator_agent is not None:
    subagents_list.append(orchestrator_agent)

root_agent = Agent(
    name="bdr_coordinator",
    model=Gemini(
        model=MODEL,
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction="""You are the BDR Coordinator Root Agent (bdr-coordinator).
Your purpose is to classify user intent and coordinate GCP Backup and Disaster Recovery (BDR) optimization workflows between specialist subagents.

Routing Directives:
- Rule 1 (Pre-Migration Sizing): If the user uploads a file, refers to inventory files (RVTools .xlsx/.csv, Migration Center .csv), or asks for sizing/costs, delegate execution immediately to 'bdr_planner' without asking for the filename. The file is already registered as an ADK artifact.
- Rule 2 (Live Cloud Governance): If the user asks for active GCP project audits, live resource discovery, Backup Vault creation, or policy binding/associations, delegate execution to 'bdr_orchestrator'.
- Rule 3 (Combined Transition Pipeline): If the user requests both baseline sizing/cost simulation AND live GCP actions/reconciliation, invoke 'bdr_planner' first to establish baseline sizing, followed by 'bdr_orchestrator' for live cloud verification and protection gap reconciliation.

Operating Rules:
1. No silent fallbacks: Always surface clear, developer-friendly error messages if dependencies or configurations are missing.
2. Ensure user confirmation is acquired before mutating any cloud infrastructure or binding policies.
3. Automatically handle user file uploads as ADK artifacts.
""",
    tools=[classify_user_intent, load_artifacts],
    sub_agents=subagents_list,
    before_model_callback=save_files_as_artifacts,
)

app = App(
    root_agent=root_agent,
    name="app",
)


