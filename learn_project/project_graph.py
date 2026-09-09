#!/usr/bin/env python3
"""项目源码引用图与结构文档生成（通用，由 learn-project.json 驱动）。"""

from __future__ import annotations

import ast
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import LearnProjectConfig

PYTHON_EXT = {".py"}
TS_EXT = {".ts", ".tsx"}


@dataclass
class SymbolInfo:
    """函数/类/接口等符号元信息。"""

    name: str
    kind: str  # class | function | method | interface | type | const
    line: int
    end_line: int
    summary: str
    signature: str = ""
    bases: list[str] = field(default_factory=list)


@dataclass
class ModuleInfo:
    """单个源文件的分析结果。"""

    id: str
    path: str
    language: str
    module: str
    summary: str
    line_count: int
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[dict[str, Any]] = field(default_factory=list)


def _first_line(text: str | None) -> str:
    if not text:
        return ""
    for line in text.strip().splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _node_signature(node: ast.AST) -> str:
    if isinstance(node, ast.ClassDef):
        bases = ", ".join(
            getattr(b, "id", None) or ast.unparse(b) for b in node.bases[:3]
        )
        return f"class {node.name}({bases})" if bases else f"class {node.name}"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        args = [a.arg for a in node.args.args[:5]]
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        return f"{prefix} {node.name}({', '.join(args)})"
    return ""


def _collect_python_symbols(tree: ast.AST) -> list[SymbolInfo]:
    symbols: list[SymbolInfo] = []
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", node.lineno) or node.lineno
            bases: list[str] = []
            if isinstance(node, ast.ClassDef):
                bases = [
                    getattr(b, "id", None) or ast.unparse(b)
                    for b in node.bases[:5]
                ]
            symbols.append(
                SymbolInfo(
                    name=node.name,
                    kind="class" if isinstance(node, ast.ClassDef) else "function",
                    line=node.lineno,
                    end_line=end,
                    summary=_first_line(ast.get_docstring(node)),
                    signature=_node_signature(node),
                    bases=bases,
                )
            )
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    end = getattr(node, "end_lineno", node.lineno) or node.lineno
                    symbols.append(
                        SymbolInfo(
                            name=target.id,
                            kind="const",
                            line=node.lineno,
                            end_line=end,
                            summary="module-level constant",
                        )
                    )
    return symbols


def _module_to_path(module: str, project_root: Path) -> str | None:
    rel = module.replace(".", "/")
    py_file = project_root / f"{rel}.py"
    init_file = project_root / rel / "__init__.py"
    if py_file.is_file():
        return str(py_file.relative_to(project_root))
    if init_file.is_file():
        return str(init_file.relative_to(project_root))
    return None


def _resolve_python_import(
    module: str | None,
    level: int,
    current_file: Path,
    project_root: Path,
    python_packages: tuple[str, ...],
) -> str | None:
    """将 import 解析为项目内相对路径。"""
    if level > 0:
        base = current_file.parent
        for _ in range(level - 1):
            base = base.parent
        if module:
            parts = module.split(".")
            candidate = base.joinpath(*parts)
        else:
            candidate = base
        py_file = candidate.with_suffix(".py")
        init_file = candidate / "__init__.py"
        if py_file.is_file():
            return str(py_file.relative_to(project_root))
        if init_file.is_file():
            return str(init_file.relative_to(project_root))
        return None

    if not module:
        return None

    for pkg in python_packages:
        if module == pkg or module.startswith(f"{pkg}."):
            return _module_to_path(module, project_root)

    return None


def _parse_python_file(path: Path, cfg: LearnProjectConfig) -> ModuleInfo:
    project_root = cfg.project_root
    rel = str(path.relative_to(project_root))
    text = path.read_text(encoding="utf-8", errors="replace")
    line_count = text.count("\n") + (1 if text else 0)
    try:
        tree = ast.parse(text, filename=rel)
    except SyntaxError:
        return ModuleInfo(
            id=rel,
            path=rel,
            language="python",
            module=rel.replace("/", ".").removesuffix(".py"),
            summary="(syntax error)",
            line_count=line_count,
        )

    module_doc = _first_line(ast.get_docstring(tree))
    symbols = _collect_python_symbols(tree)
    imports: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = _resolve_python_import(
                    alias.name, 0, path, project_root, cfg.python_packages
                )
                if target:
                    imports.append({"source": target, "names": [alias.asname or alias.name]})
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_python_import(
                node.module, node.level, path, project_root, cfg.python_packages
            )
            if target:
                names = [a.name for a in node.names if a.name != "*"]
                imports.append({"source": target, "names": names})

    return ModuleInfo(
        id=rel,
        path=rel,
        language="python",
        module=rel.replace("/", ".").removesuffix(".py"),
        summary=module_doc,
        line_count=line_count,
        symbols=symbols,
        imports=imports,
    )


_TS_IMPORT_RE = re.compile(
    r"""import\s+(?:type\s+)?(?:\{[^}]+\}|\*\s+as\s+\w+|\w+)\s+from\s+['"]([^'"]+)['"]""",
    re.MULTILINE,
)
_TS_EXPORT_CLASS_RE = re.compile(
    r"^export\s+(?:default\s+)?(?:abstract\s+)?class\s+(\w+)",
    re.MULTILINE,
)
_TS_EXPORT_FN_RE = re.compile(
    r"^export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)",
    re.MULTILINE,
)
_TS_EXPORT_CONST_RE = re.compile(
    r"^export\s+(?:default\s+)?const\s+(\w+)",
    re.MULTILINE,
)
_TS_EXPORT_INTERFACE_RE = re.compile(
    r"^export\s+(?:default\s+)?interface\s+(\w+)",
    re.MULTILINE,
)
_TS_EXPORT_TYPE_RE = re.compile(
    r"^export\s+(?:default\s+)?type\s+(\w+)",
    re.MULTILINE,
)
_TS_JSDOC_RE = re.compile(r"/\*\*(.*?)\*/", re.DOTALL)


def _resolve_ts_import(import_path: str, current_file: Path, project_root: Path) -> str | None:
    if import_path.startswith("."):
        base = (current_file.parent / import_path).resolve()
        for ext in ("", ".ts", ".tsx", "/index.ts", "/index.tsx"):
            candidate = Path(str(base) + ext)
            if candidate.is_file():
                return str(candidate.relative_to(project_root))
    return None


def _ts_symbol_summary(text: str, name: str, line: int) -> str:
    lines = text.splitlines()
    # 向上查找 JSDoc
    for i in range(line - 2, max(line - 15, -1), -1):
        chunk = "\n".join(lines[max(0, i - 5) : line])
        match = _TS_JSDOC_RE.search(chunk)
        if match:
            doc = match.group(1)
            for doc_line in doc.splitlines():
                cleaned = doc_line.strip().lstrip("*").strip()
                if cleaned and not cleaned.startswith("@"):
                    return cleaned
    return ""


def _parse_ts_file(path: Path, project_root: Path) -> ModuleInfo:
    rel = str(path.relative_to(project_root))
    text = path.read_text(encoding="utf-8", errors="replace")
    line_count = text.count("\n") + (1 if text else 0)
    symbols: list[SymbolInfo] = []

    patterns = [
        (_TS_EXPORT_CLASS_RE, "class"),
        (_TS_EXPORT_FN_RE, "function"),
        (_TS_EXPORT_INTERFACE_RE, "interface"),
        (_TS_EXPORT_TYPE_RE, "type"),
        (_TS_EXPORT_CONST_RE, "const"),
    ]
    for pattern, kind in patterns:
        for match in pattern.finditer(text):
            name = match.group(1)
            line = text[: match.start()].count("\n") + 1
            symbols.append(
                SymbolInfo(
                    name=name,
                    kind=kind,
                    line=line,
                    end_line=line,
                    summary=_ts_symbol_summary(text, name, line),
                    signature=f"{kind} {name}",
                )
            )

    file_summary = ""
    top_jsdoc = _TS_JSDOC_RE.match(text.lstrip())
    if top_jsdoc:
        file_summary = _first_line(top_jsdoc.group(1))

    imports: list[dict[str, Any]] = []
    for match in _TS_IMPORT_RE.finditer(text):
        target = _resolve_ts_import(match.group(1), path, project_root)
        if target:
            imports.append({"source": target, "names": []})

    return ModuleInfo(
        id=rel,
        path=rel,
        language="typescript",
        module=rel,
        summary=file_summary,
        line_count=line_count,
        symbols=symbols,
        imports=imports,
    )


def _is_ts_barrel_file(path: Path, cfg: LearnProjectConfig) -> bool:
    """判断 TS index 文件是否仅为 re-export barrel。"""
    if path.name not in cfg.skip_ts_barrel_names:
        return False
    text = path.read_text(encoding="utf-8", errors="replace")
    meaningful = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        meaningful.append(stripped)
    if not meaningful:
        return True
    barrel_prefixes = ("export ", "import ", "export{", "export *", "export type")
    return all(
        s.startswith(barrel_prefixes) or s in ("",)
        for s in meaningful
    )


def _is_definitional_file(path: Path, cfg: LearnProjectConfig) -> bool:
    """跳过不影响具体执行的定义性脚本。"""
    if path.name in cfg.skip_file_names:
        return True
    if path.suffix in TS_EXT and _is_ts_barrel_file(path, cfg):
        return True
    return False


def _iter_source_files(cfg: LearnProjectConfig) -> list[Path]:
    files: list[Path] = []
    project_root = cfg.project_root
    for src_dir in cfg.source_dirs:
        root = project_root / src_dir
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(part in cfg.skip_dir_names for part in path.parts):
                continue
            suffix = path.suffix
            if suffix in PYTHON_EXT or suffix in TS_EXT:
                if path.name.endswith(".d.ts"):
                    continue
                if _is_definitional_file(path, cfg):
                    continue
                files.append(path)
    return sorted(files)


def _build_directory_tree(modules: list[ModuleInfo]) -> dict[str, Any]:
    """按目录层级构建文件树，供 WebUI 侧边栏使用。"""
    result: dict[str, Any] = {"name": ".", "children": [], "files": []}

    def insert(node: dict[str, Any], parts: list[str], mod: ModuleInfo) -> None:
        if len(parts) == 1:
            node.setdefault("files", []).append({"id": mod.id, "name": parts[0]})
            return
        name = parts[0]
        children = node.setdefault("children", [])
        child = next((c for c in children if c["name"] == name), None)
        if child is None:
            child = {"name": name, "children": [], "files": []}
            children.append(child)
        insert(child, parts[1:], mod)

    for mod in modules:
        insert(result, list(Path(mod.path).parts), mod)

    def sort_node(n: dict[str, Any]) -> None:
        n.get("files", []).sort(key=lambda f: f["name"])
        for c in n.get("children", []):
            sort_node(c)
        n.get("children", []).sort(key=lambda c: c["name"])

    sort_node(result)
    return result


def _module_to_dict(mod: ModuleInfo) -> dict[str, Any]:
    data = asdict(mod)
    data["symbols"] = [asdict(s) for s in mod.symbols]
    return data


def generate_markdown(cfg: LearnProjectConfig, graph_data: dict[str, Any]) -> str:
    modules = graph_data.get("modules", [])
    py_modules = [m for m in modules if m["language"] == "python"]
    ts_modules = [m for m in modules if m["language"] == "typescript"]
    name = cfg.project_name
    pkg = cfg.python_packages[0] if cfg.python_packages else name

    lines = [
        f"# {name} 项目结构",
        "",
        f"> 自动生成于 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## 概览",
        "",
        f"- Python 模块：{len(py_modules)} 个文件",
        f"- TypeScript 模块：{len(ts_modules)} 个文件",
        f"- 总符号数：{sum(len(m.get('symbols', [])) for m in modules)}",
        "",
    ]
    if cfg.data_flow_summary:
        lines.extend(["## 核心数据流", "", "```", cfg.data_flow_summary, "```", ""])

    lines.extend(["## Python 包结构", ""])
    by_top: dict[str, list[dict[str, Any]]] = {}
    for mod in py_modules:
        parts = Path(mod["path"]).parts
        top = parts[1] if len(parts) > 1 and parts[0] == pkg else parts[0]
        by_top.setdefault(top, []).append(mod)

    for top_pkg in sorted(by_top):
        mods = by_top[top_pkg]
        lines.append(f"### `{pkg}/{top_pkg}/`")
        lines.append("")
        key_mods = sorted(mods, key=lambda m: (-len(m.get("symbols", [])), m["path"]))[:8]
        for mod in key_mods:
            syms = mod.get("symbols", [])
            sym_preview = ", ".join(s["name"] for s in syms[:5])
            summary = mod.get("summary") or "(无模块文档)"
            lines.append(f"- **{Path(mod['path']).name}** — {summary}")
            if sym_preview:
                lines.append(f"  - 符号：{sym_preview}")
        if len(mods) > 8:
            lines.append(f"  - … 另有 {len(mods) - 8} 个文件")
        lines.append("")

    if ts_modules:
        lines.extend(["## TypeScript 结构", ""])
        ts_by_dir: dict[str, int] = {}
        for mod in ts_modules:
            d = str(Path(mod["path"]).parent)
            ts_by_dir[d] = ts_by_dir.get(d, 0) + 1
        for d in sorted(ts_by_dir):
            lines.append(f"- `{d}/` — {ts_by_dir[d]} 个文件")

    lines.extend(
        [
            "",
            "## 使用方式",
            "",
            "```bash",
            f"bash .cursor/skills/learn-project/scripts/run.sh",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def analyze(cfg: LearnProjectConfig) -> dict[str, Any]:
    """分析项目并返回完整图数据。"""
    project_root = cfg.project_root
    files = _iter_source_files(cfg)
    modules: list[ModuleInfo] = []

    for path in files:
        if path.suffix == ".py":
            modules.append(_parse_python_file(path, cfg))
        else:
            modules.append(_parse_ts_file(path, project_root))

    module_ids = {m.id for m in modules}
    edges: list[dict[str, str]] = []
    seen_edges: set[tuple[str, str, str]] = set()
    for mod in modules:
        for imp in mod.imports:
            target = imp["source"]
            if target in module_ids:
                key = (mod.id, target, "import")
                if key not in seen_edges:
                    seen_edges.add(key)
                    edges.append({"from": mod.id, "to": target, "type": "import"})
        if mod.language != "python":
            continue
        for sym in mod.symbols:
            if sym.kind != "class" or not sym.bases:
                continue
            for base in sym.bases:
                base_name = base.split(".")[-1]
                for other in modules:
                    if other.language != "python":
                        continue
                    for osym in other.symbols:
                        if osym.kind == "class" and osym.name == base_name:
                            key = (mod.id, other.id, "inherit")
                            if key not in seen_edges:
                                seen_edges.add(key)
                                edges.append(
                                    {
                                        "from": mod.id,
                                        "to": other.id,
                                        "type": "inherit",
                                        "symbol": sym.name,
                                        "base": osym.name,
                                    }
                                )

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "projectRoot": str(project_root),
        "stats": {
            "moduleCount": len(modules),
            "edgeCount": len(edges),
            "symbolCount": sum(len(m.symbols) for m in modules),
            "pythonCount": sum(1 for m in modules if m.language == "python"),
            "typescriptCount": sum(1 for m in modules if m.language == "typescript"),
        },
        "directoryTree": _build_directory_tree(modules),
        "modules": [_module_to_dict(m) for m in modules],
        "edges": edges,
    }
