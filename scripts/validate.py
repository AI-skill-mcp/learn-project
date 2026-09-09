#!/usr/bin/env python3
"""learn-project 数据校验 CLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SKILL_ROOT = Path(__file__).resolve().parent.parent
if str(_SKILL_ROOT) not in sys.path:
    sys.path.insert(0, str(_SKILL_ROOT))

from learn_project.config import find_workspace, load_config
from learn_project.pipeline import run_validate


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate learnProject data")
    parser.add_argument("--workspace", type=Path, default=None)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace.resolve() if args.workspace else find_workspace()
    cfg = load_config(workspace)
    sys.exit(run_validate(cfg, strict=args.strict))


if __name__ == "__main__":
    main()
