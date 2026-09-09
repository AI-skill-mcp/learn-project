#!/usr/bin/env python3
"""分析 nanobot 包内 Python 函数调用关系，生成聚焦调用图数据。

采用增强 AST 静态分析（v2）：
- 精确 import 绑定与跨模块符号解析
- 模块级/函数级简单赋值追踪（x = Foo → x.method）
- super() / self. / 构造调用解析
- 嵌套函数与类方法
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LearnProjectConfig

SKIP_FILES = {"__init__.py"}
ENGINE = "ast-v2"


@dataclass
class SymbolNode:
    """可调用符号节点。"""

    id: str
    path: str
    name: str
    qualname: str
    kind: str
    line: int
    end_line: int = 0
    bases: list[str] = field(default_factory=list)


@dataclass
class ImportBinding:
    """本地名 → 目标模块路径 + 符号名。"""

    local: str
    target_path: str
    symbol: str | None = None  # None 表示导入整个模块


class CallGraphBuilder:
    """基于增强 AST 构建项目内调用图。"""

    def __init__(self, cfg: LearnProjectConfig) -> None:
        self.cfg = cfg
        self.project_root = cfg.project_root
        self.python_packages = cfg.python_packages
        self.symbols: dict[str, SymbolNode] = {}
        self.edges: list[dict[str, Any]] = []
        self._imports: dict[str, list[ImportBinding]] = {}
        self._path_quals: dict[str, dict[str, str]] = {}  # path -> qualname -> id
        self._class_bases: dict[str, list[str]] = {}  # sym_id -> base qualnames

    def _sym_id(self, path: str, qualname: str) -> str:
        return f"{path}::{qualname}"

    def _register(
        self,
        path: str,
        qualname: str,
        name: str,
        kind: str,
        line: int,
        end_line: int,
        bases: list[str] | None = None,
    ) -> str:
        sid = self._sym_id(path, qualname)
        if sid not in self.symbols:
            self.symbols[sid] = SymbolNode(
                sid, path, name, qualname, kind, line, end_line, bases or []
            )
            self._path_quals.setdefault(path, {})[qualname] = sid
            if bases:
                self._class_bases[sid] = bases
        return sid

    def _resolve_import_module(
        self, module: str | None, level: int, file_path: Path
    ) -> str | None:
        """将 import 解析为项目内相对路径。"""
        if level > 0:
            base = file_path.parent
            for _ in range(level - 1):
                base = base.parent
            if module:
                candidate = base.joinpath(*module.split("."))
            else:
                candidate = base
        elif module and any(
            module == pkg or module.startswith(f"{pkg}.") for pkg in self.python_packages
        ):
            rel = module.replace(".", "/")
            candidate = self.project_root / rel
        else:
            return None

        py_file = candidate.with_suffix(".py")
        init_file = candidate / "__init__.py"
        if py_file.is_file():
            return str(py_file.relative_to(self.project_root))
        if init_file.is_file():
            return str(init_file.relative_to(self.project_root))
        return None

    def _collect_imports(self, tree: ast.AST, path: str, file_path: Path) -> list[ImportBinding]:
        bindings: list[ImportBinding] = []
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                target_path = self._resolve_import_module(node.module, node.level, file_path)
                if not target_path:
                    continue
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    local = alias.asname or alias.name
                    bindings.append(ImportBinding(local, target_path, alias.name))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if not any(
                        name == pkg or name.startswith(f"{pkg}.") for pkg in self.python_packages
                    ):
                        continue
                    local = alias.asname or name.split(".")[-1]
                    target_path = self._resolve_import_module(name, 0, file_path)
                    if target_path:
                        bindings.append(ImportBinding(local, target_path, None))
        self._imports[path] = bindings
        return bindings

    def _base_to_qualname(self, base: ast.expr, path: str, bindings: list[ImportBinding]) -> str | None:
        if isinstance(base, ast.Name):
            for b in bindings:
                if b.local == base.id and b.symbol:
                    return b.symbol
            if base.id in self._path_quals.get(path, {}):
                return base.id
            return base.id
        if isinstance(base, ast.Attribute):
            parts: list[str] = []
            cur: ast.expr = base
            while isinstance(cur, ast.Attribute):
                parts.insert(0, cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.insert(0, cur.id)
                head = parts[0]
                for b in bindings:
                    if b.local == head and b.symbol:
                        parts[0] = b.symbol
                        break
                return ".".join(parts)
        return None

    def _scan_definitions(self, path: str, tree: ast.AST, bindings: list[ImportBinding]) -> None:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                end = getattr(node, "end_lineno", node.lineno) or node.lineno
                self._register(path, node.name, node.name, "function", node.lineno, end)
            elif isinstance(node, ast.ClassDef):
                end = getattr(node, "end_lineno", node.lineno) or node.lineno
                bases = [
                    q
                    for b in node.bases
                    if (q := self._base_to_qualname(b, path, bindings))
                ]
                self._register(path, node.name, node.name, "class", node.lineno, end, bases)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        qn = f"{node.name}.{item.name}"
                        ie = getattr(item, "end_lineno", item.lineno) or item.lineno
                        self._register(path, qn, item.name, "method", item.lineno, ie)

    def _lookup_in_path(self, path: str, name: str, class_ctx: str | None = None) -> list[str]:
        """在指定模块路径内查找符号 id。"""
        quals = self._path_quals.get(path, {})
        hits: list[str] = []
        if class_ctx:
            cid = quals.get(f"{class_ctx}.{name}")
            if cid:
                hits.append(cid)
        cid = quals.get(name)
        if cid:
            hits.append(cid)
        for qual, sid in quals.items():
            if qual.endswith(f".{name}") and sid not in hits:
                hits.append(sid)
        return hits

    def _resolve_import_symbol(self, binding: ImportBinding, attr: str | None = None) -> list[str]:
        """通过 import 绑定解析符号。"""
        sym_name = attr or binding.symbol
        if not sym_name:
            return []
        return self._lookup_in_path(binding.target_path, sym_name)

    def _resolve_name(
        self,
        name: str,
        path: str,
        bindings: list[ImportBinding],
        class_stack: list[str],
        locals_map: dict[str, str],
    ) -> list[str]:
        if name in locals_map:
            bound = locals_map[name]
            if "::" in bound:
                return [bound]
            return self._lookup_in_path(path, bound, class_stack[-1] if class_stack else None)

        for b in bindings:
            if b.local == name:
                if b.symbol:
                    return self._lookup_in_path(b.target_path, b.symbol)
                return []

        if class_stack:
            hits = self._lookup_in_path(path, name, class_stack[-1])
            if hits:
                return hits
        return self._lookup_in_path(path, name)

    def _collect_assignments(self, node: ast.AST, locals_map: dict[str, str], path: str) -> None:
        """收集简单赋值：Name = Name | Attribute | Call。"""
        for child in ast.walk(node):
            if not isinstance(child, ast.Assign) or len(child.targets) != 1:
                continue
            target = child.targets[0]
            if not isinstance(target, ast.Name):
                continue
            val = child.value
            if isinstance(val, ast.Name):
                locals_map[target.id] = val.id
            elif isinstance(val, ast.Call) and isinstance(val.func, ast.Name):
                locals_map[target.id] = val.func.id
            elif isinstance(val, ast.Attribute) and isinstance(val.value, ast.Name):
                locals_map[target.id] = f"{val.value.id}.{val.attr}"

    def _resolve_super_call(
        self, attr: str, path: str, class_stack: list[str], bindings: list[ImportBinding]
    ) -> list[str]:
        if not class_stack:
            return []
        class_name = class_stack[-1]
        class_id = self._sym_id(path, class_name)
        bases = self._class_bases.get(class_id, self.symbols.get(class_id, SymbolNode("", "", "", "", "", 0)).bases)
        for base_qual in bases:
            for b in bindings:
                if b.symbol == base_qual or b.local == base_qual.split(".")[0]:
                    hits = self._lookup_in_path(b.target_path, attr, base_qual.split(".")[-1])
                    if hits:
                        return hits
            hits = self._lookup_in_path(path, attr, base_qual)
            if hits:
                return hits
        return []

    def _resolve_callee(
        self,
        node: ast.Call,
        path: str,
        class_stack: list[str],
        bindings: list[ImportBinding],
        locals_map: dict[str, str],
    ) -> list[str]:
        func = node.func
        targets: list[str] = []

        if isinstance(func, ast.Name):
            name = func.id
            if name in locals_map:
                bound = locals_map[name]
                if "::" in bound:
                    targets.append(bound)
                else:
                    targets.extend(self._resolve_name(bound, path, bindings, class_stack, locals_map))
            else:
                targets.extend(self._resolve_name(name, path, bindings, class_stack, locals_map))
                # 构造调用 Foo() → Foo.__init__
                init_hits = []
                for tid in list(targets):
                    sym = self.symbols.get(tid)
                    if sym and sym.kind == "class":
                        iid = self._sym_id(sym.path, f"{sym.qualname}.__init__")
                        if iid in self.symbols:
                            init_hits.append(iid)
                targets.extend(init_hits)

        elif isinstance(func, ast.Attribute):
            attr = func.attr
            if isinstance(func.value, ast.Call) and isinstance(func.value.func, ast.Name):
                # Foo().bar() 少见，跳过
                pass
            elif isinstance(func.value, ast.Name):
                base = func.value.id
                if base == "super" and class_stack:
                    targets.extend(self._resolve_super_call(attr, path, class_stack, bindings))
                elif base in locals_map:
                    bound = locals_map[base]
                    if "." in bound:
                        head, _ = bound.split(".", 1)
                        for b in bindings:
                            if b.local == head:
                                targets.extend(self._resolve_import_symbol(b, attr))
                    targets.extend(self._resolve_name(bound, path, bindings, class_stack, locals_map))
                else:
                    for b in bindings:
                        if b.local == base:
                            targets.extend(self._resolve_import_symbol(b, attr))
                            break
                    if not targets:
                        qual_hits = self._resolve_name(f"{base}.{attr}", path, bindings, class_stack, locals_map)
                        if qual_hits:
                            targets.extend(qual_hits)
                        else:
                            for b in bindings:
                                if b.local == base and not b.symbol:
                                    targets.extend(self._lookup_in_path(b.target_path, attr))
            elif isinstance(func.value, ast.Attribute) and isinstance(func.value.value, ast.Name):
                root = func.value.value.id
                mid = func.value.attr
                for b in bindings:
                    if b.local == root:
                        # module.sub.func
                        sub_bindings = [ImportBinding(mid, b.target_path, mid)]
                        targets.extend(self._resolve_import_symbol(sub_bindings[0], attr))
                if not targets:
                    targets.extend(
                        self._resolve_name(f"{root}.{mid}.{attr}", path, bindings, class_stack, locals_map)
                    )
            elif isinstance(func.value, ast.Name) and func.value.id == "self" and class_stack:
                hits = self._lookup_in_path(path, attr, class_stack[-1])
                targets.extend(hits)

        return list(dict.fromkeys(targets))[:8]

    def _walk_function(
        self,
        path: str,
        func_node: ast.AST,
        class_stack: list[str],
        bindings: list[ImportBinding],
    ) -> None:
        qual = func_node.name
        if class_stack:
            qual = f"{class_stack[-1]}.{func_node.name}"
        caller = self._sym_id(path, qual)
        if caller not in self.symbols:
            return

        locals_map: dict[str, str] = {}
        self._collect_assignments(func_node, locals_map, path)

        for child in ast.walk(func_node):
            if isinstance(child, ast.Call) and child is not func_node:
                for callee in self._resolve_callee(child, path, class_stack, bindings, locals_map):
                    if callee != caller:
                        self.edges.append(
                            {"from": caller, "to": callee, "line": child.lineno, "type": "call"}
                        )

        # 嵌套函数
        body = getattr(func_node, "body", [])
        for item in body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                nested_stack = class_stack + ([func_node.name] if not class_stack else [])
                self._register(
                    path,
                    f"{qual}.{item.name}" if class_stack else f"{func_node.name}.{item.name}",
                    item.name,
                    "function",
                    item.lineno,
                    getattr(item, "end_lineno", item.lineno) or item.lineno,
                )
                self._walk_function(path, item, nested_stack if not class_stack else class_stack, bindings)

    def _scan_calls(self, path: str, tree: ast.AST) -> None:
        bindings = self._imports.get(path, [])
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        self._walk_function(path, item, [node.name], bindings)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self._walk_function(path, node, [], bindings)

    def process_file(self, file_path: Path) -> None:
        if file_path.name in SKIP_FILES:
            return
        rel = str(file_path.relative_to(self.project_root))
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError:
            return
        bindings = self._collect_imports(tree, rel, file_path)
        self._scan_definitions(rel, tree, bindings)

    def build(self) -> dict[str, Any]:
        files: list[Path] = []
        for pkg in self.python_packages:
            root = self.project_root / pkg.replace(".", "/")
            if root.is_file() and root.suffix == ".py":
                files.append(root)
            elif root.is_dir():
                files.extend(sorted(root.rglob("*.py")))
        files = sorted(set(files))
        for f in files:
            if f.name in SKIP_FILES or "tests" in f.parts:
                continue
            self.process_file(f)
        for f in files:
            if f.name in SKIP_FILES or "tests" in f.parts:
                continue
            rel = str(f.relative_to(self.project_root))
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"), filename=rel)
            except SyntaxError:
                continue
            self._scan_calls(rel, tree)

        seen: set[tuple[str, str]] = set()
        unique_edges = []
        for e in self.edges:
            key = (e["from"], e["to"])
            if key not in seen:
                seen.add(key)
                unique_edges.append(e)

        inherit_edges: list[dict[str, Any]] = []
        for sid, bases in self._class_bases.items():
            sym = self.symbols[sid]
            for base in bases:
                for bsid in self._lookup_in_path(sym.path, base) + self._lookup_in_path(sym.path, base.split(".")[-1]):
                    if bsid != sid:
                        inherit_edges.append(
                            {"from": sid, "to": bsid, "type": "inherit", "line": sym.line}
                        )
                for b in self._imports.get(sym.path, []):
                    if b.symbol == base or b.local == base:
                        for bsid in self._lookup_in_path(b.target_path, base.split(".")[-1]):
                            inherit_edges.append(
                                {"from": sid, "to": bsid, "type": "inherit", "line": sym.line}
                            )

        inherit_seen: set[tuple[str, str]] = set()
        for ie in inherit_edges:
            key = (ie["from"], ie["to"])
            if key not in inherit_seen:
                inherit_seen.add(key)
                unique_edges.append(ie)

        return {
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "engine": ENGINE,
            "stats": {
                "symbolCount": len(self.symbols),
                "edgeCount": len(unique_edges),
                "callEdgeCount": sum(1 for e in unique_edges if e["type"] == "call"),
                "inheritEdgeCount": sum(1 for e in unique_edges if e["type"] == "inherit"),
            },
            "symbols": [s.__dict__ for s in self.symbols.values()],
            "edges": unique_edges,
        }


def build_callgraph(cfg: LearnProjectConfig) -> dict[str, Any]:
    """分析配置的 Python 包并返回调用图 JSON 数据。"""
    return CallGraphBuilder(cfg).build()
