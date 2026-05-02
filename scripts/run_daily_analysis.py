#!/usr/bin/env python3
"""
Meta Ads Daily Agent - data retrieval and AI diagnosis.

This script is intended to be called by an n8n Execute Command node.
It retrieves Meta Ads data through the meta-marketing MCP connector, asks an
OpenAI-compatible model to generate structured recommendations, saves a pending
action payload, and prints JSON to stdout for n8n.

Security model:
- This script performs read-only Meta MCP calls.
- Any write/optimization action must be approved separately through Telegram.
- The current meta-marketing MCP connector exposed in this session is read-only;
  execution requires either a future write-enabled MCP tool or Meta Graph API
  credentials configured separately.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import textwrap
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

try:
    from openai import OpenAI  # type: ignore
except Exception:  # pragma: no cover
    OpenAI = None


DEFAULT_METRICS = [
    "reach",
    "impressions",
    "spend",
    "cpm",
    "cpc",
    "ctr",
    "actions",
    "cost_per_action_type",
    "purchase_roas",
]

ALLOWED_ACTION_TYPES = {
    "increase_daily_budget",
    "decrease_daily_budget",
    "pause_ad",
    "pause_adset",
    "no_change",
}


class AgentError(RuntimeError):
    pass


def _json_dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def call_mcp(tool_name: str, payload: Dict[str, Any], *, server: str = "meta-marketing") -> Dict[str, Any]:
    """Call manus-mcp-cli and return the saved JSON result."""
    cli = os.getenv("MANUS_MCP_CLI", "manus-mcp-cli")
    cmd = [
        cli,
        "tool",
        "call",
        tool_name,
        "--server",
        server,
        "--input",
        json.dumps(payload, ensure_ascii=False),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    combined = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if proc.returncode != 0:
        raise AgentError(f"MCP tool call failed: {tool_name}\n{combined}")

    match = re.search(r"(/tmp/manus-mcp/[^\s]+\.json)", combined)
    if not match:
        raise AgentError(f"Could not find MCP result JSON path in output for {tool_name}:\n{combined}")

    result_path = Path(match.group(1))
    if not result_path.exists():
        raise AgentError(f"MCP result file does not exist: {result_path}")

    return json.loads(result_path.read_text(encoding="utf-8"))


def fetch_meta_context(ad_account_id: str, date_preset: str, limit: int) -> Dict[str, Any]:
    """Fetch insights, recommendations, and metric definitions."""
    campaign_insights = call_mcp(
        "meta_marketing_get_insights",
        {
            "object_type": "ad_account",
            "object_id": ad_account_id,
            "level": "campaign",
            "date_preset": date_preset,
            "limit": limit,
        },
    )

    adset_insights = call_mcp(
        "meta_marketing_get_insights",
        {
            "object_type": "ad_account",
            "object_id": ad_account_id,
            "level": "adset",
            "date_preset": date_preset,
            "limit": limit,
        },
    )

    recommendations = call_mcp(
        "meta_marketing_get_recommendations",
        {"ad_account_id": ad_account_id},
    )

    metric_definitions = call_mcp(
        "meta_marketing_get_metric_definition",
        {"metrics": DEFAULT_METRICS[:20]},
    )

    return {
        "campaign_insights": campaign_insights,
        "adset_insights": adset_insights,
        "recommendations": recommendations,
        "metric_definitions": metric_definitions,
    }


def build_prompt(ad_account_id: str, date_preset: str, context: Dict[str, Any], max_actions: int) -> str:
    return textwrap.dedent(
        f"""
        你是一個 Meta Ads performance strategist。請根據以下 Meta MCP JSON 數據，輸出嚴格 JSON，不要輸出 Markdown。

        任務：為 ad account {ad_account_id} 產生每日綜合診斷與最多 {max_actions} 個可審批的廣告調整建議。日期範圍：{date_preset}。

        必須遵守：
        1. 只能使用 metric_definitions 中的標準指標名稱，不要自行改名。
        2. 不要使用模糊的「clicks」；必須區分 Link clicks 或 Clicks (all)。
        3. 涉及 Reach 的受眾描述時，使用 Accounts Center accounts。
        4. 跨不同 objective 彙總時，Results 與 Cost per result 必須為 "N/A"，不可自行計算。
        5. 不要只因單一平均 Cost per result、CPM 或短期波動就建議 pause 或降預算。
        6. 每個建議都要有 evidence、reason、risk、expected_observation_window_hours。
        7. 只能使用以下 action_type：{sorted(ALLOWED_ACTION_TYPES)}。
        8. 預算調整單次建議不得超過 20%。
        9. 若證據不足，action_type 必須是 "no_change"。

        輸出 JSON schema：
        {{
          "summary": "string",
          "confidence": "low|medium|high",
          "data_quality_notes": ["string"],
          "diagnostics": [
            {{
              "entity_type": "account|campaign|adset|ad",
              "entity_id": "string",
              "finding": "string",
              "evidence": ["string"],
              "interpretation": "string"
            }}
          ],
          "recommended_actions": [
            {{
              "action_id": "string",
              "action_type": "increase_daily_budget|decrease_daily_budget|pause_ad|pause_adset|no_change",
              "entity_type": "campaign|adset|ad|account",
              "entity_id": "string",
              "change": {{"percent": 0}},
              "reason": "string",
              "risk": "string",
              "expected_observation_window_hours": 48,
              "requires_approval": true
            }}
          ],
          "telegram_summary": "string"
        }}

        Meta MCP context:
        {json.dumps(context, ensure_ascii=False)}
        """
    ).strip()


def fallback_analysis(context: Dict[str, Any]) -> Dict[str, Any]:
    """Safe fallback if LLM is not configured."""
    return {
        "summary": "已成功取得 Meta MCP 數據，但目前未配置 OpenAI-compatible LLM，因此只產生保守診斷。",
        "confidence": "low",
        "data_quality_notes": [
            "LLM 未配置或呼叫失敗，未生成自動調整建議。",
            "建議先人工檢查 campaign 與 ad set 層級趨勢。",
        ],
        "diagnostics": [],
        "recommended_actions": [
            {
                "action_id": "no_change_001",
                "action_type": "no_change",
                "entity_type": "account",
                "entity_id": "N/A",
                "change": {"percent": 0},
                "reason": "沒有足夠 AI 診斷信心，不建議自動調整。",
                "risk": "無執行風險，因為不會改動廣告。",
                "expected_observation_window_hours": 24,
                "requires_approval": True,
            }
        ],
        "telegram_summary": "已取得 Meta MCP 數據，但 AI 診斷未啟用；建議今日不作自動調整。",
    }


def run_llm(prompt: str, model: str) -> Dict[str, Any]:
    if OpenAI is None:
        raise AgentError("openai package is not installed. Install with: pip install openai")
    if not os.getenv("OPENAI_API_KEY"):
        raise AgentError("OPENAI_API_KEY is not set")

    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "你輸出嚴格 JSON。你是嚴謹的 Meta Ads 分析師，必須保守、可審計、避免幻覺。",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def normalize_actions(analysis: Dict[str, Any], max_actions: int) -> Dict[str, Any]:
    actions = analysis.get("recommended_actions") or []
    safe_actions: List[Dict[str, Any]] = []
    for idx, action in enumerate(actions[:max_actions], start=1):
        action_type = action.get("action_type", "no_change")
        if action_type not in ALLOWED_ACTION_TYPES:
            action_type = "no_change"
        change = action.get("change") or {"percent": 0}
        percent = change.get("percent", 0)
        try:
            percent = float(percent)
        except Exception:
            percent = 0
        if abs(percent) > 20:
            percent = 20 if percent > 0 else -20
        action["action_type"] = action_type
        action["change"] = {"percent": percent}
        action["requires_approval"] = True
        action.setdefault("action_id", f"action_{idx:03d}")
        safe_actions.append(action)
    if not safe_actions:
        safe_actions.append(fallback_analysis({})["recommended_actions"][0])
    analysis["recommended_actions"] = safe_actions
    return analysis


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ad-account-id", required=True, help="Meta ad account id, with or without act_ prefix")
    parser.add_argument("--date-preset", default=os.getenv("META_AGENT_DATE_PRESET", "last_7d"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("META_AGENT_LIMIT", "100")))
    parser.add_argument("--model", default=os.getenv("META_AGENT_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--max-actions", type=int, default=int(os.getenv("META_AGENT_MAX_ACTIONS", "3")))
    parser.add_argument("--pending-dir", default=os.getenv("META_AGENT_PENDING_DIR", "/tmp/meta_ads_agent_pending"))
    args = parser.parse_args()

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    pending_dir = Path(args.pending_dir)
    pending_dir.mkdir(parents=True, exist_ok=True)

    try:
        context = fetch_meta_context(args.ad_account_id, args.date_preset, args.limit)
        prompt = build_prompt(args.ad_account_id, args.date_preset, context, args.max_actions)
        try:
            analysis = run_llm(prompt, args.model)
        except Exception as llm_error:
            analysis = fallback_analysis(context)
            analysis["data_quality_notes"].append(f"LLM error: {str(llm_error)}")
        analysis = normalize_actions(analysis, args.max_actions)

        pending_payload = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ad_account_id": args.ad_account_id,
            "date_preset": args.date_preset,
            "status": "pending_approval",
            "analysis": analysis,
            "context": context,
        }
        pending_file = pending_dir / f"{run_id}.json"
        pending_file.write_text(_json_dump(pending_payload), encoding="utf-8")

        output = {
            "ok": True,
            "run_id": run_id,
            "pending_file": str(pending_file),
            "telegram_summary": analysis.get("telegram_summary") or analysis.get("summary"),
            "analysis": analysis,
        }
        print(_json_dump(output))
        return 0
    except Exception as error:
        print(_json_dump({"ok": False, "run_id": run_id, "error": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
