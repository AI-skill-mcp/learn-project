#!/usr/bin/env python3
"""learn-project 运行时 Trace 采集 CLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from learn_project.config import find_workspace, load_config
from learn_project.pipeline import run_collect_trace


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect runtime call trace via pytest")
    parser.add_argument("--workspace", type=Path, default=None)
    args = parser.parse_args()

    workspace = args.workspace.resolve() if args.workspace else find_workspace()
    cfg = load_config(workspace)
    run_collect_trace(cfg)


if __name__ == "__main__":
    main()
