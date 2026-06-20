from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.agent_runtime import ToolGateway, ToolSession, make_tool_access_policy
from nexterp_agent.agent_runtime.deepseek_material_request import plan_material_request_with_deepseek
from nexterp_agent.erpnext.adapter import ERPNextAdapter
from nexterp_agent.erpnext.client import ERPNextClient
from nexterp_agent.erpnext.config import load_erpnext_settings


DEFAULT_TEXT = "城东项目道路班组明天需要帆布手套100双，送到城东项目仓，用于今天的劳保补充。"


def main() -> int:
    parser = argparse.ArgumentParser(description="Ask DeepSeek to draft a Material Request ToolCall.")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="Natural-language employee request.")
    parser.add_argument(
        "--context-json",
        help="Optional JSON context containing resolved company/project/warehouse/item candidates.",
    )
    parser.add_argument("--execute", action="store_true", help="Execute the proposed ToolCall through ToolGateway.")
    parser.add_argument("--erpnext-profile", default="civil", help="ERPNext env profile used when --execute is set.")
    parser.add_argument("--agent-profile", default="采购员", help="Tool access profile used by ToolGateway.")
    parser.add_argument("--expected-user", help="Expected ERPNext API user; enables identity verification when set.")
    args = parser.parse_args()

    context = _load_context(args.context_json)
    plan = plan_material_request_with_deepseek(args.text, context=context)
    print(json.dumps({"deepseek_plan": plan}, ensure_ascii=False, indent=2))

    if not args.execute:
        print("\n[dry-run] 未执行 ERPNext 写入。确认候选 ToolCall 后可追加 --execute。", file=sys.stderr)
        return 0

    if plan.get("status") != "needs_confirmation":
        print("\n[blocked] DeepSeek 认为信息不足，需要先追问，不执行。", file=sys.stderr)
        return 1

    gateway = _build_gateway(args.erpnext_profile, args.agent_profile, args.expected_user)
    result = gateway.execute(plan["tool_call"], origin="agent")
    print(json.dumps({"erpnext_result": result.to_dict()}, ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def _load_context(context_json: str | None) -> dict[str, Any] | None:
    if not context_json:
        return None
    context_path = Path(context_json)
    if context_path.exists():
        return json.loads(context_path.read_text(encoding="utf-8"))
    return json.loads(context_json)


def _build_gateway(erpnext_profile: str, agent_profile: str, expected_user: str | None) -> ToolGateway:
    settings = load_erpnext_settings(erpnext_profile)
    client = ERPNextClient(
        settings.base_url,
        settings.api_key,
        settings.api_secret,
        host_header=settings.host_header,
    )
    adapter = ERPNextAdapter(client)
    session = ToolSession(
        user=expected_user,
        policy=make_tool_access_policy(agent_profile),
        verify_erpnext_identity=bool(expected_user),
    )
    return ToolGateway(adapter, session)


if __name__ == "__main__":
    raise SystemExit(main())
