#!/usr/bin/env python3
"""
Zeabur-friendly Meta Ads Daily Agent.

This version does NOT depend on manus-mcp-cli, because Zeabur n8n cannot access
Manus session MCP connectors directly. It uses Meta Graph Marketing API over HTTP,
then asks an OpenAI-compatible model for a conservative structured diagnosis.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests
from openai import OpenAI

FIELDS = "campaign_id,campaign_name,objective,impressions,reach,spend,cpm,cpc,ctr,actions,cost_per_action_type,purchase_roas"


def dump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def graph_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    token = os.getenv("META_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("META_ACCESS_TOKEN is not set")
    version = os.getenv("META_GRAPH_API_VERSION", "v20.0")
    url = f"https://graph.facebook.com/{version}/{path.lstrip('/')}"
    params = dict(params)
    params["access_token"] = token
    res = requests.get(url, params=params, timeout=45)
    try:
        body = res.json()
    except Exception:
        body = {"raw": res.text}
    if res.status_code >= 400:
        raise RuntimeError(f"Meta Graph API error {res.status_code}: {body}")
    return body


def fetch_all_insights(ad_account_id: str, date_preset: str, level: str, limit: int) -> List[Dict[str, Any]]:
    data: List[Dict[str, Any]] = []
    body = graph_get(
        f"{ad_account_id}/insights",
        {
            "level": level,
            "date_preset": date_preset,
            "fields": FIELDS,
            "limit": limit,
        },
    )
    data.extend(body.get("data", []))
    # Keep MVP cheap and predictable: one page only by default.
    return data


def run_ai(ad_account_id: str, date_preset: str, campaign_data: List[Dict[str, Any]], model: str) -> Dict[str, Any]:
    client = OpenAI()
    prompt = f"""
你是嚴謹的 Meta Ads performance strategist。請根據以下 Meta Marketing API 數據，輸出嚴格 JSON，不要 Markdown。

Ad account: {ad_account_id}
日期範圍: {date_preset}

必須遵守：
1. 不要使用模糊的 clicks；如需提及，請使用 Link clicks 或 Clicks (all)。
2. 涉及 Reach 時，描述為 Accounts Center accounts。
3. 跨不同 objective 彙總時，Results 與 Cost per result 請顯示 N/A，不要自行計算。
4. 不要只因短期 CPM 或 Cost per result 偏高就建議 pause 或降 budget。
5. 第一版只允許：increase_daily_budget、decrease_daily_budget、pause_ad、pause_adset、no_change。
6. 預算調整建議不可超過 20%，且所有 action 都 requires_approval=true。
7. 如果證據不足，請建議 no_change。

輸出 JSON schema：
{{
  "summary": "string",
  "confidence": "low|medium|high",
  "data_quality_notes": ["string"],
  "diagnostics": [{{"entity_type":"campaign|adset|ad|account","entity_id":"string","finding":"string","evidence":["string"],"interpretation":"string"}}],
  "recommended_actions": [{{"action_id":"string","action_type":"increase_daily_budget|decrease_daily_budget|pause_ad|pause_adset|no_change","entity_type":"campaign|adset|ad|account","entity_id":"string","change":{{"percent":0}},"reason":"string","risk":"string","expected_observation_window_hours":48,"requires_approval":true}}],
  "telegram_summary": "string"
}}

Campaign insights JSON:
{json.dumps(campaign_data, ensure_ascii=False)}
"""
    res = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "你只輸出 JSON。你必須保守、可審計、避免幻覺。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
        response_format={"type": "json_object"},
    )
    return json.loads(res.choices[0].message.content or "{}")


def normalize(analysis: Dict[str, Any]) -> Dict[str, Any]:
    allowed = {"increase_daily_budget", "decrease_daily_budget", "pause_ad", "pause_adset", "no_change"}
    actions = analysis.get("recommended_actions") or []
    safe = []
    for idx, action in enumerate(actions[:3], 1):
        if action.get("action_type") not in allowed:
            action["action_type"] = "no_change"
        change = action.get("change") or {"percent": 0}
        try:
            percent = float(change.get("percent", 0))
        except Exception:
            percent = 0
        if abs(percent) > 20:
            percent = 20 if percent > 0 else -20
        action["change"] = {"percent": percent}
        action["requires_approval"] = True
        action.setdefault("action_id", f"action_{idx:03d}")
        safe.append(action)
    if not safe:
        safe = [{
            "action_id": "no_change_001",
            "action_type": "no_change",
            "entity_type": "account",
            "entity_id": "N/A",
            "change": {"percent": 0},
            "reason": "證據不足，不建議自動調整。",
            "risk": "沒有廣告改動。",
            "expected_observation_window_hours": 24,
            "requires_approval": True,
        }]
    analysis["recommended_actions"] = safe
    return analysis


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ad-account-id", default=os.getenv("META_AD_ACCOUNT_ID", "act_2073150323260144"))
    parser.add_argument("--date-preset", default=os.getenv("META_AGENT_DATE_PRESET", "last_7d"))
    parser.add_argument("--limit", type=int, default=int(os.getenv("META_AGENT_LIMIT", "100")))
    parser.add_argument("--model", default=os.getenv("META_AGENT_MODEL", "gpt-4.1-mini"))
    parser.add_argument("--pending-dir", default=os.getenv("META_AGENT_PENDING_DIR", "/data/meta_ads_agent_pending"))
    args = parser.parse_args()

    run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    pending_dir = Path(args.pending_dir)
    pending_dir.mkdir(parents=True, exist_ok=True)

    try:
        campaign_data = fetch_all_insights(args.ad_account_id, args.date_preset, "campaign", args.limit)
        analysis = normalize(run_ai(args.ad_account_id, args.date_preset, campaign_data, args.model))
        payload = {
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "ad_account_id": args.ad_account_id,
            "date_preset": args.date_preset,
            "status": "pending_approval",
            "analysis": analysis,
            "raw_campaign_insights": campaign_data,
        }
        pending_file = pending_dir / f"{run_id}.json"
        pending_file.write_text(dump(payload), encoding="utf-8")
        print(dump({"ok": True, "run_id": run_id, "pending_file": str(pending_file), "telegram_summary": analysis.get("telegram_summary") or analysis.get("summary"), "analysis": analysis}))
        return 0
    except Exception as e:
        print(dump({"ok": False, "run_id": run_id, "error": str(e)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
