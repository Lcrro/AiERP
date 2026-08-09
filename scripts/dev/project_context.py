"""Generate compact, secret-free project context for Nexterp development."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
RUNTIME_CONTEXT = ROOT / ".runtime" / "context"
CONFIG_PATH = ROOT / "config" / "project_context.yaml"
SENSITIVE_PARTS = {".env", ".secrets", ".git"}
SENSITIVE_SUFFIXES = {".key", ".pem", ".secret"}
IGNORED_TREE_NAMES = {".git", ".venv", "node_modules", ".runtime", "__pycache__"}
MARKDOWN_LINK_RE = re.compile(r"!?(?:\[[^\]]*\])\(([^)]+)\)")


def run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=True
    )
    return result.stdout.strip()


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise SystemExit(f"Missing project context config: {CONFIG_PATH}")
    with CONFIG_PATH.open("r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}
    validate_config(config)
    return config


def validate_config(config: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "current_milestone",
        "production_entrypoints",
        "local_services",
        "active_modules",
        "module_paths",
        "module_tests",
        "module_docs",
        "recent_completed",
        "next_steps",
        "known_issues",
        "verification_commands",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"project_context.yaml missing: {', '.join(missing)}")
    if not isinstance(config["schema_version"], int):
        raise ValueError("schema_version must be an integer")
    if not isinstance(config["production_entrypoints"], dict) or not config["production_entrypoints"]:
        raise ValueError("production_entrypoints must contain at least one entry")
    if any(not isinstance(value, str) or not value.strip() for value in config["production_entrypoints"].values()):
        raise ValueError("production_entrypoints values must be non-empty strings")
    if not isinstance(config["local_services"], list):
        raise ValueError("local_services must be a list")
    for service in config["local_services"]:
        if not isinstance(service, dict) or not service.get("id") or not service.get("command"):
            raise ValueError("every local service needs id and command")
    milestone = config["current_milestone"]
    if not isinstance(milestone, dict) or not milestone.get("id"):
        raise ValueError("current_milestone.id is required")
    module_ids = []
    for module in config["active_modules"]:
        if not isinstance(module, dict) or not module.get("id"):
            raise ValueError("every active module needs an id")
        module_ids.append(module["id"])
    for field in ("module_paths", "module_tests", "module_docs"):
        missing_modules = sorted(set(module_ids) - set(config[field]))
        if missing_modules:
            raise ValueError(f"{field} missing modules: {', '.join(missing_modules)}")
        for module_id, paths in config[field].items():
            if not isinstance(paths, list) or not all(isinstance(path, str) for path in paths):
                raise ValueError(f"{field}.{module_id} must be a list of paths")
            missing_paths = [path for path in paths if not path_exists(path)]
            if missing_paths:
                raise ValueError(f"{field}.{module_id} has missing paths: {', '.join(missing_paths)}")
            if any(Path(path).is_absolute() or is_sensitive(Path(path)) for path in paths):
                raise ValueError(f"{field}.{module_id} contains an absolute or sensitive path")


def git_state() -> dict[str, Any]:
    raw_status = run_git("status", "--porcelain=v1", "--untracked-files=all")
    entries = []
    ignored_runtime = []
    sensitive = []
    for line in raw_status.splitlines():
        if not line:
            continue
        path_text = line[3:].strip().strip('"')
        path = Path(path_text)
        normalized = path.as_posix().lower()
        if normalized.startswith("data/runtime/") or normalized.startswith(".runtime/"):
            ignored_runtime.append(path_text)
            continue
        if is_sensitive(path):
            sensitive.append(path_text)
            continue
        entries.append({"status": line[:2], "path": path_text})
    return {
        "branch": run_git("branch", "--show-current"),
        "head": run_git("rev-parse", "HEAD"),
        "head_short": run_git("rev-parse", "--short", "HEAD"),
        "last_commit": run_git("log", "-1", "--format=%h %ad %s", "--date=iso-strict"),
        "changes": entries,
        "runtime_files_excluded": sorted(ignored_runtime),
        "sensitive_paths_detected": sorted(sensitive),
    }


def is_sensitive(path: Path) -> bool:
    parts = {part.lower() for part in path.parts}
    if parts & SENSITIVE_PARTS:
        return True
    if path.name.lower() in {".env", ".env.local", ".env.production"}:
        return True
    return path.suffix.lower() in SENSITIVE_SUFFIXES


def path_exists(relative: str) -> bool:
    return (ROOT / relative).exists()


def symbols_for_path(path: Path) -> dict[str, Any]:
    relative = path.relative_to(ROOT).as_posix()
    result: dict[str, Any] = {"path": relative, "exists": path.exists()}
    if not path.exists() or not path.is_file():
        return result
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return result
    if path.suffix == ".py":
        try:
            tree = ast.parse(text)
            result["symbols"] = sorted(
                node.name
                for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            )[:80]
        except SyntaxError:
            result["symbols"] = []
    elif path.suffix in {".js", ".ts", ".tsx"}:
        result["symbols"] = sorted(
            set(re.findall(r"(?:function|class)\s+([A-Za-z_$][\w$]*)|(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=", text))
        )[:80]
    return result


def repo_map(config: dict[str, Any]) -> dict[str, Any]:
    modules: dict[str, Any] = {}
    for module in config["active_modules"]:
        module_id = module["id"]
        files: list[dict[str, Any]] = []
        for raw_path in config["module_paths"][module_id]:
            path = ROOT / raw_path
            if path.is_dir():
                candidates = sorted(
                    item for item in path.rglob("*")
                    if item.is_file() and item.suffix in {".py", ".js", ".ts", ".tsx"}
                    and not is_sensitive(item.relative_to(ROOT))
                )[:120]
                files.extend(symbols_for_path(item) for item in candidates)
            else:
                files.append(symbols_for_path(path))
        modules[module_id] = {
            "label": module["label"],
            "paths": config["module_paths"][module_id],
            "tests": config["module_tests"][module_id],
            "docs": config["module_docs"][module_id],
            "files": files,
        }
    return {"schema_version": 1, "modules": modules}


def doc_audit(config: dict[str, Any]) -> dict[str, Any]:
    markdown = sorted(
        path for path in ROOT.rglob("*.md")
        if not (set(path.relative_to(ROOT).parts) & IGNORED_TREE_NAMES)
        and not is_sensitive(path.relative_to(ROOT))
        and (
            path.relative_to(ROOT).as_posix().startswith("docs/")
            or (path.parent == ROOT and path.name in {"README.md", "AGENTS.md"})
        )
    )
    broken: list[dict[str, str]] = []
    classified: dict[str, list[str]] = {"active": [], "reference": [], "historical": [], "generated": []}
    for path in markdown:
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("docs/archive/"):
            category = "historical"
        elif relative.startswith("docs/generated/"):
            category = "generated"
        elif relative.startswith("docs/reference/"):
            category = "reference"
        else:
            category = "active"
        classified[category].append(relative)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for target in MARKDOWN_LINK_RE.findall(text):
            clean = target.split("#", 1)[0].split("?", 1)[0].strip().strip("<>")
            if not clean or re.match(r"^(?:https?:|mailto:|tel:)", clean):
                continue
            resolved = (path.parent / clean).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                broken.append({"source": relative, "target": target, "reason": "outside_repo"})
                continue
            if not resolved.exists():
                broken.append({"source": relative, "target": target, "reason": "missing"})
    return {
        "schema_version": 1,
        "markdown_count": len(markdown),
        "broken_links": broken,
        "classified": classified,
        "unclassified_count": 0,
    }


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def snapshot(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    state = git_state()
    project_snapshot = {
        "schema_version": 1,
        "config": config,
        "git": state,
        "entrypoint_paths": {
            key: value for key, value in config["production_entrypoints"].items()
        },
        "sensitive_files_in_context": [],
    }
    return project_snapshot, repo_map(config)


def resume_text(config: dict[str, Any]) -> str:
    state = git_state()
    milestone = config["current_milestone"]
    lines = [
        f"Nexterp 项目恢复摘要 | {milestone['id']}",
        f"分支: {state['branch']} | HEAD: {state['head_short']}",
        f"最近提交: {state['last_commit']}",
        f"工作区变化: {len(state['changes'])} 个业务文件；运行日志已排除 {len(state['runtime_files_excluded'])} 个",
        f"当前入口: {config['production_entrypoints'].get('workbench', '')}",
        f"ERPNext: {config['production_entrypoints'].get('erpnext_civil', '')}",
        "活动模块: " + "、".join(module["label"] for module in config["active_modules"]),
        "最近完成:",
    ]
    lines.extend(f"- {item}" for item in config["recent_completed"][:4])
    lines.append("下一步:")
    lines.extend(f"- {item}" for item in config["next_steps"][:4])
    if state["sensitive_paths_detected"]:
        lines.append("警告: 工作区发现敏感路径，禁止提交。")
    return "\n".join(lines) + "\n"


def status_markdown(config: dict[str, Any]) -> str:
    state = git_state()
    milestone = config["current_milestone"]
    lines = [
        "# 项目状态",
        "",
        f"当前里程碑：`{milestone['id']}`（{milestone.get('status', 'unknown')}）",
        f"当前分支：`{state['branch']}`，HEAD：`{state['head_short']}`",
        "",
        "## 生产入口",
        "",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in config["production_entrypoints"].items())
    lines.extend(["", "## 活动模块", ""])
    for module in config["active_modules"]:
        lines.append(f"- **{module['label']}** (`{module['id']}`)：代码 `{', '.join(config['module_paths'][module['id']])}`；测试 `{', '.join(config['module_tests'][module['id']])}`")
    lines.extend(["", "## 最近完成", ""])
    lines.extend(f"- {item}" for item in config["recent_completed"])
    lines.extend(["", "## 下一步", ""])
    lines.extend(f"{index}. {item}" for index, item in enumerate(config["next_steps"], 1))
    lines.extend(["", "## 验证命令", ""])
    lines.extend(f"- `{command}`: `{value}`" for command, value in config["verification_commands"].items())
    lines.extend(["", "## 维护边界", "", "- Git 和测试结果是项目事实来源，聊天记录不是事实来源。", "- 不提交 `.env`、`.secrets`、`data/runtime/` 日志、真实 ERPNext 凭据或业务运行数据。", "- 阶段结束、提交前或交接时更新状态，不要求每次提交都改状态。", ""])
    return "\n".join(lines)


def handoff_markdown(config: dict[str, Any]) -> str:
    state = git_state()
    lines = [
        "# 当前开发交接",
        "",
        "新任务先运行 `python scripts/dev/project_context.py resume`，再按本次请求选择模块。",
        "",
        f"- 分支：`{state['branch']}`",
        f"- HEAD：`{state['head']}`",
        f"- 工作区业务变化：`{len(state['changes'])}` 个；运行时文件不纳入上下文。",
        f"- 当前里程碑：`{config['current_milestone']['id']}`",
        "",
        "## 入口",
        "",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in config["production_entrypoints"].items())
    lines.extend(["", "## 需要知道的事实", ""])
    lines.extend(f"- {item}" for item in config["recent_completed"])
    lines.extend(["", "## 下一步", ""])
    lines.extend(f"- {item}" for item in config["next_steps"])
    lines.extend(["", "## 开发规约", "", "- 先核对 Git 工作区，保留用户未提交改动。", "- 只读取本次相关模块的代码、测试和文档；不要遍历全部文档。", "- 优先使用 CodeGraph，不可用时使用 `rg` 和 `.runtime/context/repo-map.json`。", "- 写操作必须使用员工本人身份、明确确认、幂等 request_id 和执行后回读。", "- 不读取或打包 `.env`、`.secrets`、凭据和运行日志。", ""])
    return "\n".join(lines)


def run(args: argparse.Namespace) -> int:
    config = load_config()
    if args.command == "resume":
        output = resume_text(config)
        sys.stdout.write(output[:8192])
        return 0
    if args.command == "snapshot":
        project_snapshot, mapping = snapshot(config)
        write_json(RUNTIME_CONTEXT / "project-snapshot.json", project_snapshot)
        write_json(RUNTIME_CONTEXT / "repo-map.json", mapping)
        print(f"Wrote {RUNTIME_CONTEXT / 'project-snapshot.json'}")
        print(f"Wrote {RUNTIME_CONTEXT / 'repo-map.json'}")
        return 0
    if args.command == "audit-docs":
        result = doc_audit(config)
        write_json(RUNTIME_CONTEXT / "doc-audit.json", result)
        print(json.dumps({"markdown_count": result["markdown_count"], "broken_links": len(result["broken_links"])}, ensure_ascii=False))
        return 0 if not result["broken_links"] else 1
    if args.command == "checkpoint":
        text = status_markdown(config)
        if not args.write:
            print(text)
            return 0
        path = ROOT / "docs" / "project-status.md"
        path.write_text(text, encoding="utf-8")
        print(f"Wrote {path}")
        return 0
    if args.command == "handoff":
        text = handoff_markdown(config)
        if not args.write:
            print(text)
            return 0
        path = ROOT / "docs" / "handoffs" / "current.md"
        path.write_text(text, encoding="utf-8")
        print(f"Wrote {path}")
        return 0
    if args.command == "check":
        project_snapshot, mapping = snapshot(config)
        audit_path = RUNTIME_CONTEXT / "doc-audit.json"
        errors: list[str] = []
        if not (RUNTIME_CONTEXT / "project-snapshot.json").exists():
            errors.append("missing project-snapshot.json; run snapshot")
        if not (RUNTIME_CONTEXT / "repo-map.json").exists():
            errors.append("missing repo-map.json; run snapshot")
        if not audit_path.exists():
            errors.append("missing doc-audit.json; run audit-docs")
        else:
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            if audit.get("broken_links"):
                errors.append(f"broken markdown links: {len(audit['broken_links'])}")
        if project_snapshot["git"]["sensitive_paths_detected"]:
            errors.append("sensitive paths detected in Git status")
        for output_path in (ROOT / "docs" / "project-status.md", ROOT / "docs" / "handoffs" / "current.md"):
            if output_path.exists():
                if any(part.lower() in {".env", ".secrets"} for part in output_path.parts):
                    errors.append(f"sensitive output path: {output_path}")
        status_path = ROOT / "docs" / "project-status.md"
        handoff_path = ROOT / "docs" / "handoffs" / "current.md"
        if status_path.exists() and len(status_path.read_text(encoding="utf-8").splitlines()) > 120:
            errors.append("docs/project-status.md exceeds 120 lines")
        if handoff_path.exists() and len(handoff_path.read_text(encoding="utf-8").splitlines()) > 150:
            errors.append("docs/handoffs/current.md exceeds 150 lines")
        print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 1
    raise SystemExit(f"Unknown command: {args.command}")


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command", required=True)
    for name in ("resume", "snapshot", "audit-docs", "check"):
        sub.add_parser(name)
    for name in ("checkpoint", "handoff"):
        command = sub.add_parser(name)
        command.add_argument("--write", action="store_true", help="write repository documents")
    return cli


if __name__ == "__main__":
    try:
        raise SystemExit(run(parser().parse_args()))
    except (ValueError, yaml.YAMLError) as exc:
        print(f"project_context error: {exc}", file=sys.stderr)
        raise SystemExit(2)
