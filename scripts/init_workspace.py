#!/usr/bin/env python3
"""为新仓库初始化 learnProject 工作区（通用模板）。"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = _SKILL_ROOT.parents[2] if len(_SKILL_ROOT.parents) >= 3 else Path.cwd()

DEFAULT_CONFIG = {
    "projectName": "my-project",
    "sourceDirs": ["src"],
    "pythonPackages": [],
    "skipDirNames": [
        "__pycache__", "node_modules", ".git", "dist", "build", ".venv", "web", "tests"
    ],
    "skipFileNames": ["__init__.py"],
    "skipTsBarrelNames": ["index.ts", "index.tsx"],
    "configSchema": None,
    "scenariosFile": "config/scenarios.json",
    "boundaryHints": {},
    "runtimeBoundaryFiles": [],
    "traceTests": [],
    "dataFlowSummary": "",
    "webuiTitle": "项目学习图谱",
}


def init_workspace(target: Path, project_name: str, source_dirs: list[str], python_packages: list[str]) -> None:
    """创建 learnProject 目录结构与默认配置。"""
    target.mkdir(parents=True, exist_ok=True)
    for sub in ("data", "docs", "config", "webui", "scripts"):
        (target / sub).mkdir(exist_ok=True)

    cfg = dict(DEFAULT_CONFIG)
    cfg["projectName"] = project_name
    cfg["sourceDirs"] = source_dirs
    cfg["pythonPackages"] = python_packages
    cfg["webuiTitle"] = f"{project_name} 项目学习"
    (target / "learn-project.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    scenarios = {"scenarios": []}
    (target / "config" / "scenarios.json").write_text(
        json.dumps(scenarios, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # 从 nanobot learnProject 复制 WebUI 与 server（若存在）
    sample = REPO_ROOT / "learnProject"
    for name in ("server.py", "README.md"):
        src = sample / name
        if src.is_file() and not (target / name).exists():
            shutil.copy2(src, target / name)
    webui_src = sample / "webui"
    webui_dst = target / "webui"
    if webui_src.is_dir() and not any(webui_dst.iterdir()):
        shutil.copytree(webui_src, webui_dst, dirs_exist_ok=True)

    # 兼容薄封装脚本
    scripts_src = sample / "scripts"
    if scripts_src.is_dir():
        for script in scripts_src.glob("*.py"):
            dst = target / "scripts" / script.name
            if not dst.exists():
                shutil.copy2(script, dst)

    print(f"Initialized workspace: {target}")
    print("Next: edit learn-project.json, add scenarios to config/scenarios.json")
    print(f"Run: python {_SKILL_ROOT}/scripts/analyze.py --workspace {target}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize learnProject workspace for any repo")
    parser.add_argument("--target", type=Path, default=Path("learnProject"))
    parser.add_argument("--name", default=Path.cwd().name)
    parser.add_argument("--source-dirs", nargs="+", default=["src"])
    parser.add_argument("--python-packages", nargs="+", default=[])
    args = parser.parse_args()
    init_workspace(args.target.resolve(), args.name, args.source_dirs, args.python_packages)


if __name__ == "__main__":
    main()
