"""运行时调用 Trace 采集（pytest + sys.settrace）。"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LearnProjectConfig


@dataclass
class TraceCollector:
    """记录配置包路径内的函数调用边。"""

    project_root: Path
    path_prefixes: tuple[str, ...]
    stack: list[str] = field(default_factory=list)
    edges: list[dict[str, Any]] = field(default_factory=list)
    _seen: set[tuple[str, str]] = field(default_factory=set)

    def _frame_id(self, frame) -> str | None:
        try:
            rel = str(Path(frame.f_code.co_filename).resolve().relative_to(self.project_root))
        except ValueError:
            return None
        if not any(rel.startswith(p) for p in self.path_prefixes):
            return None
        if rel.endswith("__init__.py"):
            return None
        return f"{rel}::{frame.f_code.co_name}"

    def trace(self, frame, event, arg):
        if event == "call":
            fid = self._frame_id(frame)
            if fid:
                caller = self.stack[-1] if self.stack else None
                if caller and caller != fid:
                    key = (caller, fid)
                    if key not in self._seen:
                        self._seen.add(key)
                        self.edges.append(
                            {
                                "from": caller,
                                "to": fid,
                                "type": "runtime",
                                "line": frame.f_lineno,
                            }
                        )
                self.stack.append(fid)
        elif event == "return":
            if self.stack:
                self.stack.pop()
        return self.trace


def collect_trace(cfg: LearnProjectConfig, tests: list[str] | None = None) -> dict[str, Any]:
    """在单进程内运行 pytest 并采集 trace。"""
    import pytest

    tests = tests or list(cfg.trace_tests)
    prefixes = tuple(f"{p.replace('.', '/')}/" for p in cfg.python_packages)
    collector = TraceCollector(cfg.project_root, prefixes)
    sys.settrace(collector.trace)
    try:
        for test_id in tests:
            pytest.main(["-q", test_id, "--no-cov", "-p", "no:warnings"])
    finally:
        sys.settrace(None)

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "tests": tests,
        "stats": {"edgeCount": len(collector.edges), "testCount": len(tests)},
        "edges": collector.edges,
    }
