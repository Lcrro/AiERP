from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
import json
import os
from pathlib import Path
import sys
from typing import Callable
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from nexterp_agent.agent_runtime.civil_runtime import CivilAgentRuntime, RuntimeTurnResult
from nexterp_agent.agent_runtime.credentials import load_user_credentials
from nexterp_agent.erpnext.client import ERPNextClient


DEFAULT_JSON_REPORT = ROOT / "data" / "runtime" / "civil_agent_day_report.json"
DEFAULT_MD_REPORT = ROOT / "docs" / "scenarios" / "civil-agent-day-runtime-report.md"


@dataclass(frozen=True)
class Event:
    time: str
    name: str
    user: str
    commands: Callable[[dict[str, list[str]]], list[str]]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def latest(state: dict[str, list[str]], doctype: str) -> str:
    values = state.get(doctype) or []
    return values[-1] if values else f"<缺少{doctype}单号>"


def build_events() -> list[Event]:
    mao = "mao.xiaoquan@stec-up.local"
    pan = "pan.feng@stec-up.local"
    gm = "zhang.zhenguang@stec-up.local"
    return [
        Event("08:00", "管理层查看今日异常", gm, lambda _: ["今天公司有哪些异常需要我关注"]),
        Event("08:20", "项目提报劳保用品需求", mao, lambda _: ["合流1.3标明天需要20双手套帆布加厚双层，送到合流1.3标仓库，创建材料申请草稿"]),
        Event("08:35", "项目提报管材管件需求", mao, lambda _: ["合流1.3标后天需要10个PPR直接 25，送到合流1.3标仓库，创建材料申请草稿"]),
        Event("08:50", "项目提报电气耗材需求", mao, lambda _: ["合流1.3标明天需要10卷绝缘胶带黑色18mm乘10m，送到合流1.3标仓库，创建材料申请草稿"]),
        Event(
            "09:10",
            "审核并提交材料需求",
            mao,
            lambda state: [f"提交材料申请 {name}" for name in state.get("Material Request", [])[-3:]],
        ),
        Event("09:30", "采购汇总待处理材料申请", pan, lambda _: ["查询所有待采购的材料申请"]),
        Event(
            "10:00",
            "常用品转采购订单",
            pan,
            lambda state: [f"把材料申请 {latest(state, 'Material Request')} 交给测试综合供应商做成采购订单草稿"],
        ),
        Event(
            "10:30",
            "管材材料发起询价",
            pan,
            lambda _: ["向测试综合供应商询价10个PPR直接 25，要求三天内报价，创建询价草稿"],
        ),
        Event("11:20", "项目仓检查可用库存", mao, lambda _: ["合流1.3标仓库还有多少6.8级螺栓M12*40"]),
        Event(
            "13:30",
            "供应商送货并采购收货",
            pan,
            lambda state: [
                f"提交采购订单 {latest(state, 'Purchase Order')}",
                f"根据采购订单 {latest(state, 'Purchase Order')} 创建采购收货草稿",
                "提交刚才创建的采购收货",
            ],
        ),
        Event(
            "14:00",
            "到货规格不符并退货",
            pan,
            lambda state: [
                f"采购收货 {latest(state, 'Purchase Receipt')} 到货规格不符，记录差异并给我创建跟进待办",
                f"采购收货 {latest(state, 'Purchase Receipt')} 规格不符，全部退货，创建退货草稿",
            ],
        ),
        Event("14:30", "项目仓领料", mao, lambda _: ["合流1.3标从合流1.3标仓库领用5个6.8级螺栓M12*40用于现场施工，创建项目领料草稿"]),
        Event("15:10", "缺料检查与补采", mao, lambda _: ["合流1.3标仓库还有多少绝缘胶带黑色18mm乘10m"]),
        Event(
            "16:00",
            "财务处理采购发票",
            gm,
            lambda state: [f"根据采购收货 {latest(state, 'Purchase Receipt')} 创建采购发票草稿"],
        ),
        Event("16:40", "采购跟进未到货订单", pan, lambda _: ["查询所有已经逾期但还没完成收货的采购订单"]),
        Event("17:20", "项目经理查看项目成本", gm, lambda _: ["查看合流1.3标今天的项目成本"]),
        Event("18:00", "总经理查看收尾摘要", gm, lambda _: ["汇总今天公司已完成、未完成、异常和明天风险"]),
    ]


def document_from_result(result: RuntimeTurnResult) -> tuple[str, str] | None:
    for payload in reversed(result.tool_results or (() if result.tool_result is None else (result.tool_result,))):
        data = payload.get("data") if isinstance(payload, dict) else None
        if isinstance(data, dict) and data.get("doctype") and data.get("name"):
            return str(data["doctype"]), str(data["name"])
    return None


def run() -> int:
    parser = argparse.ArgumentParser(description="Run the UP civil-company day through employee natural-language Agents.")
    parser.add_argument("--execute", action="store_true", help="Explicitly confirm write steps and create real sandbox documents.")
    parser.add_argument("--from-time", default="08:00")
    parser.add_argument("--to-time", default="18:00")
    parser.add_argument("--continue-on-error", action="store_true")
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--json-report", type=Path, default=DEFAULT_JSON_REPORT)
    parser.add_argument("--md-report", type=Path, default=DEFAULT_MD_REPORT)
    args = parser.parse_args()
    load_dotenv(args.env_file)

    def client_factory(user: str) -> ERPNextClient:
        credentials = load_user_credentials(user)
        return ERPNextClient(
            os.environ["NEXTERP_CIVIL_BASE_URL"],
            credentials["api_key"],
            credentials["api_secret"],
            host_header=os.getenv("NEXTERP_CIVIL_HOST_HEADER"),
        )

    runtime = CivilAgentRuntime(client_factory=client_factory)
    run_id = uuid4().hex
    state: dict[str, list[str]] = {}
    records: list[dict] = []
    failed = False
    for event in build_events():
        if not (args.from_time <= event.time <= args.to_time):
            continue
        event_record = {"time": event.time, "event": event.name, "user": event.user, "turns": []}
        commands = event.commands(state)
        if not commands:
            event_record["status"] = "blocked_dependency"
            event_record["message"] = "前置单据不存在。"
            records.append(event_record)
            failed = True
            if not args.continue_on_error:
                break
            continue
        for turn_index, command in enumerate(commands, start=1):
            request_id = f"civil-day:{run_id}:{event.time}:{turn_index}"
            result = runtime.run_once(
                command,
                user=event.user,
                execute=args.execute,
                today=date.today(),
                request_id=request_id,
            )
            event_record["turns"].append({"request_id": request_id, "command": command, "result": result.to_dict()})
            document = document_from_result(result)
            if document:
                state_key = "Purchase Receipt Return" if document[1].startswith("MAT-PR-RET-") else document[0]
                state.setdefault(state_key, []).append(document[1])
            if result.status in {"failed", "unsupported_intent", "needs_clarification"}:
                failed = True
                if not args.continue_on_error:
                    break
        statuses = [turn["result"]["status"] for turn in event_record["turns"]]
        event_record["status"] = "completed" if statuses and all(status in {"completed", "needs_confirmation"} for status in statuses) else "failed"
        event_record["documents"] = {key: values[-3:] for key, values in state.items()}
        records.append(event_record)
        if failed and not args.continue_on_error:
            break

    payload = {
        "run_date": date.today().isoformat(),
        "run_id": run_id,
        "execute": args.execute,
        "event_count": len(records),
        "completed": sum(record["status"] == "completed" for record in records),
        "failed": sum(record["status"] != "completed" for record in records),
        "documents": state,
        "events": records,
    }
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.md_report.parent.mkdir(parents=True, exist_ok=True)
    args.md_report.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("run_date", "execute", "event_count", "completed", "failed", "documents")}, ensure_ascii=False, indent=2))
    return 1 if payload["failed"] else 0


def render_markdown(payload: dict) -> str:
    lines = [
        "# 土木公司全天 Agent Runtime 执行报告",
        "",
        f"- 日期：`{payload['run_date']}`",
        f"- 真实写入：`{payload['execute']}`",
        f"- 事件：`{payload['event_count']}`；完成：`{payload['completed']}`；失败：`{payload['failed']}`",
        "",
        "| 时间 | 事件 | 员工账号 | 状态 | 产生单据 |",
        "|---|---|---|---|---|",
    ]
    for event in payload["events"]:
        documents: list[str] = []
        for turn in event.get("turns", []):
            result = turn["result"]
            for tool_result in result.get("tool_results") or ([result.get("tool_result")] if result.get("tool_result") else []):
                data = tool_result.get("data") if isinstance(tool_result, dict) else None
                if isinstance(data, dict) and data.get("name"):
                    documents.append(str(data["name"]))
        lines.append(f"| {event['time']} | {event['event']} | `{event['user']}` | {event['status']} | {', '.join(documents)} |")
    lines.extend(["", "完整的意图、解析、ToolCall 与 ToolResult 保存在同名 JSON 报告中。", ""])
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(run())
