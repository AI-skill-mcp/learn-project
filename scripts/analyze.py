#!/usr/bin/env python3
"""learn-project 全量分析 CLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from learn_project.config import find_workspace, load_config
from learn_project.pipeline import run_analyze


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze repository for learnProject WebUI")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=None,
        help="learnProject 工作区目录（含 learn-project.json），默认自动查找",
    )
    parser.add_argument("--strict", action="store_true", help="场景校验失败时 exit 1")
    args = parser.parse_args()

    workspace = args.workspace.resolve() if args.workspace else find_workspace()
    cfg = load_config(workspace)
    run_analyze(cfg, strict=args.strict)


if __name__ == "__main__":
    main()
