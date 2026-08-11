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

"""ADK Artifact management and before_model_callback utilities."""

import os
import json
import base64
import logging
from typing import Any, Optional
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools import ToolContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

logger = logging.getLogger(__name__)


async def save_files_as_artifacts(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> LlmResponse | None:
    """Inspects the LLM request for user-uploaded files, saves them to ADK ArtifactService,
    writes a local copy for tool parsing, and injects file metadata into state and prompt context."""
    invocation_id = callback_context.invocation_id

    last_user_message = None
    if llm_request.contents and llm_request.contents[-1].role == "user":
        last_user_message = llm_request.contents[-1]

    if not last_user_message or not last_user_message.parts:
        return None

    uploaded_files_info = []

    for i, part in enumerate(last_user_message.parts):
        if isinstance(part, dict):
            try:
                part = types.Part.model_validate(part)
            except Exception:
                continue

        if part.inline_data is None:
            continue

        try:
            display_name = part.inline_data.display_name
            mime_type = part.inline_data.mime_type or "application/octet-stream"

            if not display_name:
                ext = ".bin"
                if "sheet" in mime_type or "excel" in mime_type:
                    ext = ".xlsx"
                elif "csv" in mime_type:
                    ext = ".csv"
                elif "json" in mime_type:
                    ext = ".json"
                display_name = f"uploaded_artifact_{invocation_id}_{i}{ext}"

            # 1. Save artifact into ADK session ArtifactService
            await callback_context.save_artifact(
                filename=display_name,
                artifact=part,
            )
            logger.info(f"Successfully saved ADK artifact: {display_name}")

            # 2. Save local filesystem copy in uploads/ directory for direct parsing tools
            os.makedirs("uploads", exist_ok=True)
            local_path = os.path.join("uploads", display_name)
            data_bytes = part.inline_data.data
            if isinstance(data_bytes, str):
                data_bytes = base64.b64decode(data_bytes)
            with open(local_path, "wb") as f:
                f.write(data_bytes)

            # 3. Store in session state
            if "uploaded_files" not in callback_context.state:
                callback_context.state["uploaded_files"] = []
            if display_name not in callback_context.state["uploaded_files"]:
                callback_context.state["uploaded_files"].append(display_name)
            callback_context.state["latest_uploaded_file"] = display_name
            callback_context.state["latest_uploaded_file_path"] = local_path

            uploaded_files_info.append({
                "filename": display_name,
                "mime_type": mime_type,
                "local_path": local_path,
                "size_bytes": len(data_bytes)
            })

        except Exception as e:
            logger.error(f"Failed to save artifact for upload part {i}: {e}")
            continue

    if uploaded_files_info:
        # Append context hint so LLM knows the exact uploaded filename without asking user
        hints = [f"- '{f['filename']}' (Type: {f['mime_type']}, Size: {f['size_bytes']} bytes, Path: {f['local_path']})" for f in uploaded_files_info]
        system_hint = (
            f"\n\n[System Notice: The user uploaded the following file(s) which have been saved to ADK Artifacts:\n"
            + "\n".join(hints)
            + "\nProceed to parse and analyze the uploaded artifact(s) directly using the available tools without asking the user for the filename.]"
        )
        last_user_message.parts.append(types.Part.from_text(text=system_hint))

    return None


async def save_json_artifact(tool_context: ToolContext, filename: str, data: Any) -> str:
    """Saves a JSON data payload both as a local file and as an ADK session artifact."""
    json_str = json.dumps(data, indent=2)
    json_bytes = json_str.encode("utf-8")

    # 1. Save local file
    os.makedirs("assets", exist_ok=True)
    local_path = os.path.join("assets", filename)
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(json_str)

    # Also save to current working dir if different
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            f.write(json_str)

    # 2. Save into ADK ArtifactService
    try:
        part = types.Part.from_bytes(data=json_bytes, mime_type="application/json")
        await tool_context.save_artifact(filename=filename, artifact=part)
        logger.info(f"Saved artifact '{filename}' into ADK ArtifactService.")
    except Exception as e:
        logger.warning(f"Could not save artifact '{filename}' to ADK ArtifactService: {e}")

    return local_path
