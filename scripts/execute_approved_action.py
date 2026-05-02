#!/usr/bin/env python3
"""
Meta Ads Agent - approval executor.

Called by n8n after Telegram callback approval.
Default mode is DRY RUN because the meta-marketing MCP tools available in this
session are read-only. To execute real changes, configure META_EXECUTION_MODE=graph_api
and META_ACCESS_TOKEN, then extend/verify action-specific Graph API calls.
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

ALLOWED_ACTION_TYPES = {
    "increase_daily_budget",
    "decrease_daily_budget",
    "pause_ad",
    "pause_adset",
    "no_change",
}


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def load_pending(run_id: str, pending_dir: str) -> tuple[Path, Dict[str, Any]]:
    path = Path(pending_dir) / f"{run_id}.json"
    if not path.exists():
        raise RuntimeError(f"Pending action not found: {path}")
    return path, json.loads(path.read_text(encoding="utf-8"))


def validate_action(action: Dict[str, Any]) -> None:
    action_type = action.get("action_type")
    if action_type not in ALLOWED_ACTION_TYPES:
        raise RuntimeError(f"Action type not allowed: {action_type}")
    change = action.get("change") or {}
    percent = float(change.get("percent", 0) or 0)
    if abs(percent) > 20:
        raise RuntimeError("Budget change exceeds 20% safety cap")


def dry_run_execute(action: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "executed": False,
        "mode": "dry_run",
        "message": "已通過審批，但目前處於 dry-run；沒有改動 Meta 廣告。",
        "action": action,
    }


def graph_api_post(object_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    token = os.getenv("META_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN is not set")
    version = os.getenv("META_GRAPH_API_VERSION", "v20.0")
    url = f"https://graph.facebook.com/{version}/{object_id}"
    data = dict(payload)
    data["access_token"] = token
    response = requests.post(url, data=data, timeout=30)
    try:
        body = response.json()
    except Exception:
        body = {"raw": response.text}
    if response.status_code >= 400:
        raise RuntimeError(f"Graph API error {response.status_code}: {body}")
    return body


def graph_api_execute(action: Dict[str, Any]) -> Dict[str, Any]:
    action_type = action.get("action_type")
    entity_type = action.get("entity_type")
    entity_id = action.get("entity_id")

    if action_type == "no_change":
        return {"executed": False, "mode": "graph_api", "message": "Action is no_change."}

    if action_type == "pause_ad" and entity_type == "ad":
        return {"executed": True, "mode": "graph_api", "response": graph_api_post(entity_id, {"status": "PAUSED"})}

    if action_type == "pause_adset" and entity_type == "adset":
        return {"executed": True, "mode": "graph_api", "response": graph_api_post(entity_id, {"status": "PAUSED"})}

    # Budget updates require exact currency minor-unit budget to avoid unsafe guesses.
    if action_type in {"increase_daily_budget", "decrease_daily_budget"}:
        new_budget = action.get("change", {}).get("new_daily_budget_minor_units")
        if new_budget is None:
            raise RuntimeError(
                "Budget action requires change.new_daily_budget_minor_units. "
                "Do not compute budget from percentage unless current budget was fetched and verified."
            )
        if entity_type not in {"campaign", "adset"}:
            raise RuntimeError("Budget action entity_type must be campaign or adset")
        return {
            "executed": True,
            "mode": "graph_api",
            "response": graph_api_post(entity_id, {"daily_budget": int(new_budget)}),
        }

    raise RuntimeError(f"Unsupported action/entity combination: {action_type}/{entity_type}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--decision", choices=["approve", "reject", "details"], required=True)
    parser.add_argument("--pending-dir", default=os.getenv("META_AGENT_PENDING_DIR", "/tmp/meta_ads_agent_pending"))
    parser.add_argument("--approved-by", default=os.getenv("TELEGRAM_APPROVER", "telegram"))
    args = parser.parse_args()

    try:
        path, payload = load_pending(args.run_id, args.pending_dir)
        if payload.get("status") not in {"pending_approval", "details_requested"}:
            raise RuntimeError(f"Run is not pending approval: {payload.get('status')}")

        if args.decision == "details":
            payload["status"] = "details_requested"
            path.write_text(dump(payload), encoding="utf-8")
            print(dump({"ok": True, "decision": "details", "payload": payload}))
            return 0

        if args.decision == "reject":
            payload["status"] = "rejected"
            payload["rejected_at"] = datetime.now(timezone.utc).isoformat()
            payload["rejected_by"] = args.approved_by
            path.write_text(dump(payload), encoding="utf-8")
            print(dump({"ok": True, "decision": "reject", "message": "建議已拒絕，沒有執行任何改動。"}))
            return 0

        actions: List[Dict[str, Any]] = payload.get("analysis", {}).get("recommended_actions", [])
        results: List[Dict[str, Any]] = []
        mode = os.getenv("META_EXECUTION_MODE", "dry_run")

        for action in actions:
            validate_action(action)
            if mode == "graph_api":
                results.append(graph_api_execute(action))
            else:
                results.append(dry_run_execute(action))

        payload["status"] = "approved_executed" if mode == "graph_api" else "approved_dry_run"
        payload["approved_at"] = datetime.now(timezone.utc).isoformat()
        payload["approved_by"] = args.approved_by
        payload["execution_results"] = results
        path.write_text(dump(payload), encoding="utf-8")

        print(dump({"ok": True, "decision": "approve", "mode": mode, "results": results}))
        return 0
    except Exception as error:
        print(dump({"ok": False, "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
