"""执行场景流与边界提取（项目无关逻辑，场景数据来自 JSON 配置）。"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LearnProjectConfig


def _raise_message(node: ast.Raise) -> str:
    if node.exc is None:
        return "raise"
    exc = node.exc
    if isinstance(exc, ast.Call):
        if isinstance(exc.func, ast.Name):
            name = exc.func.id
        elif isinstance(exc.func, ast.Attribute):
            name = exc.func.attr
        else:
            name = "Exception"
        if exc.args:
            arg = exc.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return f"{name}: {arg.value[:120]}"
            try:
                return f"{name}: {ast.unparse(arg)[:120]}"
            except Exception:
                return name
        return name
    if isinstance(exc, ast.Name):
        return exc.id
    return ast.unparse(exc)[:80]


def _extract_runtime_boundaries(cfg: LearnProjectConfig) -> list[dict[str, Any]]:
    """从配置列出的核心文件提取 raise 与运行时校验点。"""
    boundaries: list[dict[str, Any]] = []
    for rel in cfg.runtime_boundary_files:
        path = cfg.resolve(rel)
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Raise):
                msg = _raise_message(node)
                if any(k in msg.lower() for k in ("error", "invalid", "reserved", "must", "cannot", "forbidden")):
                    bid = f"runtime-{rel.replace('/', '-')}-{node.lineno}"
                    boundaries.append(
                        {
                            "id": bid,
                            "name": f"L{node.lineno}",
                            "value": "",
                            "constraint": "raise",
                            "source": rel,
                            "line": node.lineno,
                            "category": "runtime",
                            "kind": "runtime",
                            "description": msg,
                        }
                    )
            elif isinstance(node, ast.If):
                try:
                    cond = ast.unparse(node.test)
                except Exception:
                    continue
                keywords = ("max_", "limit", "iteration", "timeout", "permission", "denied", "ttl")
                if any(k in cond.lower() for k in keywords):
                    bid = f"runtime-check-{rel.replace('/', '-')}-{node.lineno}"
                    boundaries.append(
                        {
                            "id": bid,
                            "name": f"if L{node.lineno}",
                            "value": "",
                            "constraint": "guard",
                            "source": rel,
                            "line": node.lineno,
                            "category": "runtime",
                            "kind": "runtime",
                            "description": f"条件守卫: {cond[:100]}",
                        }
                    )

    return boundaries[:80]


def _extract_boundaries_from_schema(
    schema_path: Path, project_root: Path, hints: dict[str, str]
) -> list[dict[str, Any]]:
    """从 Pydantic schema 的 Field 提取边界约束。"""
    rel = str(schema_path.relative_to(project_root))
    text = schema_path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=rel)
    boundaries: list[dict[str, Any]] = []
    seen: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        category = node.name
        for item in node.body:
            if not isinstance(item, ast.AnnAssign) or not isinstance(item.target, ast.Name):
                continue
            name = item.target.id
            if name in seen:
                continue
            line = item.lineno
            default_val = ""
            constraints: list[str] = []

            if item.value is not None:
                try:
                    default_val = ast.unparse(item.value)
                except Exception:
                    default_val = ""

            if "Field(" in default_val:
                for m in re.finditer(r"\b(ge|le|gt|lt)\s*=\s*([^,)]+)", default_val):
                    constraints.append(f"{m.group(1)}={m.group(2).strip()}")
                dm = re.search(r"default\s*=\s*([^,)]+)", default_val)
                if dm:
                    default_val = dm.group(1).strip()

            if name.startswith("_"):
                continue
            keywords = ("max", "min", "limit", "ttl", "ratio", "retry", "timeout", "fail_", "token")
            if not any(k in name.lower() for k in keywords):
                continue

            seen.add(name)
            boundaries.append(
                {
                    "id": name,
                    "name": name,
                    "value": default_val.strip("\"'"),
                    "constraint": ", ".join(constraints) if constraints else "",
                    "source": rel,
                    "line": line,
                    "category": category,
                    "kind": "config",
                    "description": hints.get(name, f"{category}.{name}"),
                }
            )

    return sorted(boundaries, key=lambda b: b["name"])


def _validate_and_enrich_scenarios(
    project_root: Path,
    scenarios: list[dict[str, Any]],
    runtime_bounds: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """校验步骤 path/line，并自动关联同文件附近的运行时边界。"""
    enriched: list[dict[str, Any]] = []
    for scenario in scenarios:
        steps_out: list[dict[str, Any]] = []
        for step in scenario.get("steps", []):
            step_copy = dict(step)
            issues: list[str] = []
            path = project_root / step["path"]
            line = int(step.get("line", 1))

            if not path.is_file():
                issues.append("文件不存在")
            else:
                text = path.read_text(encoding="utf-8", errors="replace")
                line_count = text.count("\n") + (1 if text else 0)
                if line > line_count:
                    issues.append(f"行号超范围 (max {line_count})")
                sym = step.get("symbol", "")
                if sym:
                    try:
                        tree = ast.parse(text, filename=step["path"])
                        names = {
                            n.name
                            for n in ast.walk(tree)
                            if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                        }
                        short = sym.split(".")[-1]
                        if short not in names and sym not in names:
                            issues.append(f"符号 '{sym}' 未在文件顶层找到")
                    except SyntaxError:
                        issues.append("语法错误，无法校验符号")

            nearby_runtime = [
                b["id"]
                for b in runtime_bounds
                if b["source"] == step["path"] and abs(b["line"] - line) <= 60
            ][:6]
            step_copy["runtimeBoundaryIds"] = nearby_runtime
            step_copy["validation"] = issues
            steps_out.append(step_copy)
        enriched.append({**scenario, "steps": steps_out})
    return enriched


def _infer_data_flows(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """推断相邻步骤间的数据传递标签。"""
    flows: list[dict[str, Any]] = []
    for i in range(len(steps) - 1):
        cur, nxt = steps[i], steps[i + 1]
        out_types = list(cur.get("dataTypes") or [])
        in_types = list(nxt.get("dataTypes") or [])
        shared = [t for t in out_types if t in in_types]
        if shared:
            label = " → ".join(shared)
            types = shared
        elif out_types:
            label = " → ".join(out_types[:3])
            types = out_types[:3]
        elif in_types:
            label = f"→ {' → '.join(in_types[:2])}"
            types = in_types[:2]
        else:
            label = "控制流"
            types = []
        flows.append(
            {
                "fromStep": cur["id"],
                "toStep": nxt["id"],
                "label": label,
                "types": types,
            }
        )
    return flows


def _load_scenarios(cfg: LearnProjectConfig) -> list[dict[str, Any]]:
    path = cfg.scenarios_path()
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return data
    return list(data.get("scenarios", []))


def build_scenarios_data(cfg: LearnProjectConfig) -> dict[str, Any]:
    """构建场景流 + 边界完整数据。"""
    project_root = cfg.project_root
    config_bounds: list[dict[str, Any]] = []
    if cfg.config_schema:
        schema_path = cfg.resolve(cfg.config_schema)
        if schema_path.is_file():
            config_bounds = _extract_boundaries_from_schema(
                schema_path, project_root, cfg.boundary_hints
            )

    runtime_bounds = _extract_runtime_boundaries(cfg)
    boundaries = config_bounds + runtime_bounds
    scenarios_raw = _validate_and_enrich_scenarios(
        project_root, _load_scenarios(cfg), runtime_bounds
    )
    scenarios = [{**s, "dataFlows": _infer_data_flows(s["steps"])} for s in scenarios_raw]

    validation_errors = sum(
        1 for s in scenarios for st in s["steps"] if st.get("validation")
    )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "boundaries": boundaries,
        "configBoundaryCount": len(config_bounds),
        "runtimeBoundaryCount": len(runtime_bounds),
        "validationErrors": validation_errors,
        "scenarios": scenarios,
    }
