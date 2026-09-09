"""全量分析流水线。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .callgraph import build_callgraph
from .config import LearnProjectConfig
from .project_graph import analyze, generate_markdown
from .scenarios import build_scenarios_data
from .trace import collect_trace


def run_analyze(cfg: LearnProjectConfig, strict: bool = False) -> None:
    """运行引用图、场景、调用图全量分析。"""
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    cfg.docs_dir.mkdir(parents=True, exist_ok=True)

    print(f"Analyzing project at {cfg.project_root}")
    graph_data = analyze(cfg)
    graph_path = cfg.data_dir / "project-graph.json"
    graph_path.write_text(json.dumps(graph_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {graph_path} ({graph_data['stats']['moduleCount']} modules, "
        f"{graph_data['stats']['edgeCount']} edges)"
    )

    md_path = cfg.docs_dir / "project-structure.md"
    md_path.write_text(generate_markdown(cfg, graph_data), encoding="utf-8")
    print(f"Wrote {md_path}")

    scenario_data = build_scenarios_data(cfg)
    scenarios_path = cfg.data_dir / "scenarios.json"
    scenarios_path.write_text(json.dumps(scenario_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {scenarios_path}")
    if scenario_data["validationErrors"]:
        print(f"WARNING: {scenario_data['validationErrors']} scenario step validation error(s)")
        if strict:
            sys.exit(1)

    callgraph_path = cfg.data_dir / "callgraph.json"
    callgraph_path.write_text(
        json.dumps(build_callgraph(cfg), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {callgraph_path}")


def run_validate(cfg: LearnProjectConfig, strict: bool = False) -> int:
    """校验 learnProject 数据完整性，strict 时失败返回 1。"""
    errors: list[str] = []
    warnings: list[str] = []

    scenario_data = build_scenarios_data(cfg)
    if scenario_data["validationErrors"]:
        errors.append(f"场景步骤校验失败: {scenario_data['validationErrors']} 处")

    for name in ("project-graph.json", "scenarios.json", "callgraph.json"):
        if not (cfg.data_dir / name).is_file():
            warnings.append(f"缺少数据文件 {name}，请运行 analyze")

    if not (cfg.data_dir / "runtime-trace.json").is_file():
        warnings.append("缺少 runtime-trace.json，可选运行 collect_trace")

    for w in warnings:
        print(f"WARN: {w}")
    for e in errors:
        print(f"ERROR: {e}")

    if errors:
        if strict:
            return 1
        print(f"Validation finished with {len(errors)} error(s)")
        return 0

    print(
        f"OK: {len(scenario_data['scenarios'])} scenarios, "
        f"{scenario_data['configBoundaryCount']} config boundaries, "
        f"{scenario_data['runtimeBoundaryCount']} runtime boundaries"
    )
    return 0


def run_collect_trace(cfg: LearnProjectConfig) -> None:
    """采集运行时 trace。"""
    cfg.data_dir.mkdir(parents=True, exist_ok=True)
    tests = list(cfg.trace_tests)
    print(f"Collecting runtime trace from {len(tests)} tests...")
    data = collect_trace(cfg, tests)
    out = cfg.data_dir / "runtime-trace.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out} ({data['stats']['edgeCount']} runtime edges)")
