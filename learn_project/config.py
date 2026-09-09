"""learn-project 工作区配置加载。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "learn-project.json"
DEFAULT_SKIP_DIRS = frozenset(
    {"__pycache__", "node_modules", ".git", "dist", "build", ".venv", "web", "tests"}
)
DEFAULT_SKIP_FILES = frozenset({"__init__.py"})
DEFAULT_TS_BARRELS = frozenset({"index.ts", "index.tsx"})


@dataclass
class LearnProjectConfig:
    """单个仓库 learnProject 工作区配置。"""

    workspace: Path
    project_root: Path
    project_name: str
    source_dirs: tuple[str, ...]
    python_packages: tuple[str, ...]
    skip_dir_names: frozenset[str] = DEFAULT_SKIP_DIRS
    skip_file_names: frozenset[str] = DEFAULT_SKIP_FILES
    skip_ts_barrel_names: frozenset[str] = DEFAULT_TS_BARRELS
    config_schema: str | None = None
    scenarios_file: str = "config/scenarios.json"
    boundary_hints: dict[str, str] = field(default_factory=dict)
    runtime_boundary_files: tuple[str, ...] = ()
    trace_tests: tuple[str, ...] = ()
    data_flow_summary: str = ""
    webui_title: str = "项目学习图谱"

    @property
    def data_dir(self) -> Path:
        return self.workspace / "data"

    @property
    def docs_dir(self) -> Path:
        return self.workspace / "docs"

    def scenarios_path(self) -> Path:
        return self.workspace / self.scenarios_file

    def resolve(self, rel: str) -> Path:
        return self.project_root / rel


def find_workspace(start: Path | None = None) -> Path:
    """向上查找含 learn-project.json 的目录。"""
    cur = (start or Path.cwd()).resolve()
    for parent in [cur, *cur.parents]:
        if (parent / CONFIG_FILENAME).is_file():
            return parent
    raise FileNotFoundError(
        f"未找到 {CONFIG_FILENAME}，请在 learnProject 目录执行或传入 --workspace"
    )


def load_config(workspace: Path | None = None) -> LearnProjectConfig:
    """从工作区加载 learn-project.json。"""
    ws = workspace.resolve() if workspace else find_workspace()
    raw: dict[str, Any] = json.loads((ws / CONFIG_FILENAME).read_text(encoding="utf-8"))

    project_root = ws.parent
    if raw.get("projectRoot"):
        pr = Path(raw["projectRoot"])
        project_root = (ws / pr).resolve() if not pr.is_absolute() else pr

    return LearnProjectConfig(
        workspace=ws,
        project_root=project_root,
        project_name=raw.get("projectName", project_root.name),
        source_dirs=tuple(raw.get("sourceDirs", [])),
        python_packages=tuple(raw.get("pythonPackages", [])),
        skip_dir_names=frozenset(raw.get("skipDirNames", DEFAULT_SKIP_DIRS)),
        skip_file_names=frozenset(raw.get("skipFileNames", DEFAULT_SKIP_FILES)),
        skip_ts_barrel_names=frozenset(raw.get("skipTsBarrelNames", DEFAULT_TS_BARRELS)),
        config_schema=raw.get("configSchema"),
        scenarios_file=raw.get("scenariosFile", "config/scenarios.json"),
        boundary_hints=dict(raw.get("boundaryHints", {})),
        runtime_boundary_files=tuple(raw.get("runtimeBoundaryFiles", ())),
        trace_tests=tuple(raw.get("traceTests", ())),
        data_flow_summary=raw.get("dataFlowSummary", ""),
        webui_title=raw.get("webuiTitle", f"{raw.get('projectName', project_root.name)} 项目学习"),
    )
