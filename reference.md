# learn-project 技术参考

> 解析实现：`.cursor/skills/learn-project/learn_project/`  
> 项目配置：`learnProject/learn-project.json`

## learn-project.json（工作区配置）

| 字段 | 说明 |
|------|------|
| `projectName` | 项目显示名 |
| `sourceDirs` | 相对仓库根的扫描目录 |
| `pythonPackages` | Python 包名（import 解析 + 调用图 + trace 前缀） |
| `skipDirNames` / `skipFileNames` / `skipTsBarrelNames` | 跳过规则 |
| `configSchema` | Pydantic schema 路径（配置边界提取，可 null） |
| `scenariosFile` | 场景 JSON 相对工作区路径 |
| `boundaryHints` | 配置边界字段 → 中文说明 |
| `runtimeBoundaryFiles` | 运行时边界扫描文件列表 |
| `traceTests` | pytest 节点 id 列表 |
| `dataFlowSummary` | 结构文档中的数据流 ASCII 图 |
| `webuiTitle` | WebUI 标题 |

`projectRoot` 可选，默认工作区上级目录（仓库根）。

## 扫描配置（由 learn-project.json 驱动）

| 常量 | 说明 |
|------|------|
| `sourceDirs` | 相对项目根的扫描目录 |
| `skipDirNames` | 跳过目录 |
| `skipFileNames` | 定义性 Python 文件 |
| `skipTsBarrelNames` | 纯 re-export 的 index.ts(x) |

**定义性文件跳过规则**（`_is_definitional_file`）：
- `__init__.py`：包初始化，一律跳过
- `index.ts` / `index.tsx`：仅含 import/export 的 barrel 文件跳过

## 解析策略

### Python（`ast` 模块）

| 提取项 | 方法 |
|--------|------|
| 模块 docstring | `ast.get_docstring(tree)` 首行 |
| class / function | 顶层 `ClassDef`, `FunctionDef`, `AsyncFunctionDef` |
| 符号 docstring | `ast.get_docstring(node)` 首行 |
| 签名 | class 名+基类；function 参数列表（最多 5 个） |
| import 边 | `Import` / `ImportFrom`，解析为项目内相对路径 |

**import 解析规则**：
- `nanobot.*` 绝对导入 → `nanobot/.../*.py` 或 `__init__.py`
- 相对导入（`level > 0`）→ 从当前文件目录向上解析

### TypeScript（正则）

| 提取项 | 模式 |
|--------|------|
| import | `import ... from '...'` |
| export class/function/const/interface/type | 行首 `export` 正则 |
| 符号说明 | 向上查找最近 `/** ... */` JSDoc 首行 |
| import 边 | 相对路径 `.` 开头，解析 `.ts`/`.tsx`/index |

## 输出：project-graph.json

```json
{
  "generatedAt": "ISO8601",
  "projectRoot": "/abs/path",
  "stats": {
    "moduleCount": 522,
    "edgeCount": 1236,
    "symbolCount": 3867,
    "pythonCount": 302,
    "typescriptCount": 220
  },
  "directoryTree": { "name": ".", "children": [...], "files": [...] },
  "modules": [
    {
      "id": "nanobot/agent/loop.py",
      "path": "nanobot/agent/loop.py",
      "language": "python",
      "module": "nanobot.agent.loop",
      "summary": "模块 docstring 首行",
      "line_count": 800,
      "symbols": [
        {
          "name": "AgentLoop",
          "kind": "class",
          "line": 45,
          "end_line": 200,
          "summary": "类 docstring 首行",
          "signature": "class AgentLoop(...)"
        }
      ],
      "imports": [
        { "source": "nanobot/bus/queue.py", "names": ["MessageBus"] }
      ]
    }
  ],
  "edges": [
    { "from": "nanobot/agent/loop.py", "to": "nanobot/bus/queue.py", "type": "import" }
  ]
}
```

### Symbol kind 枚举

`class` | `function` | `method` | `interface` | `type` | `const`

## HTTP API（server.py，默认 :9876）

| 端点 | 参数 | 返回 |
|------|------|------|
| `GET /api/graph` | — | `project-graph.json` 内容 |
| `GET /api/scenarios` | — | `scenarios.json`（场景流 + 边界 + dataFlows） |
| `GET /api/callgraph` | — | `callgraph.json`（AST 调用图） |
| `GET /api/runtime-trace` | — | `runtime-trace.json`（pytest 运行时 trace，可选） |
| `GET /api/file` | `path`, `start`, `end` | `{ path, start, end, total, content, language }` |
| `GET /api/search` | `q` | `{ results: [{ type, module, symbol? }] }`，最多 50 条 |
| `GET /` | — | `webui/index.html` |

**安全**：`/api/file` 路径必须在 `PROJECT_ROOT` 内，防目录穿越。

## 场景与校验脚本

| 脚本 | 说明 |
|------|------|
| `learn_project/scenarios.py` | 场景校验 + 边界提取 + dataFlows |
| `learn_project/callgraph.py` | AST v2 调用图 |
| `learn_project/trace.py` | pytest trace |
| `scripts/analyze.py` | 全量分析 CLI |
| `scripts/validate.py` | `--strict` 校验 |
| `scripts/collect_trace.py` | trace 采集 |
| `scripts/init_workspace.py` | 新项目初始化 |

CI（`.github/workflows/ci.yml` coverage 矩阵）会运行 `analyze_project.py --strict` 与 `validate_learn_project.py --strict`。

### scenarios.json 扩展字段

每个 scenario 含 `dataFlows`：`[{ fromStep, toStep, label, types }]`，由相邻步骤 `dataTypes` 重叠推断。

## WebUI 行为（webui/app.js）

| 交互 | 行为 |
|------|------|
| 图谱节点 hover | tooltip：路径、summary、符号列表、统计 |
| 图谱节点 click | 选中 + 打开右侧代码 Tab（全文件） |
| 目录树 checkbox | 默认全选；控制主图谱展示范围 |
| 目录 checkbox | 级联勾选/取消子文件 |
| 灰度依赖 | 选中模块引用的未勾选模块 → 灰度节点（虚线边框） |
| 上游隐藏 | 灰度模块的 import 上游不展示 |
| 面板拖拽 | 侧栏与代码面板边界可拖拽调宽（180–600px / 200–900px） |
| 目录树 click | 打开代码 Tab |
| 符号列表 click | 打开 Tab 并高亮 `line..end_line` |
| 搜索 | 匹配 path / summary / symbol name，点击跳转 |
| Tab 右键 | 关闭 Tab |
| 语言过滤 | 复选框控制 Python / TypeScript 节点可见性 |
| 场景流 | 步骤间显示 `dataFlows` 数据类型标签 |
| 调用图 Trace | 「叠加 Trace」将 runtime-trace 边以橙色虚线叠加 |

**依赖（CDN）**：vis-network、highlight.js

## 调用图（analyze_callgraph.py）

引擎：`ast-v2`（增强 AST，不依赖 PyCG）

| 能力 | 说明 |
|------|------|
| import 绑定 | `from X import Y` 精确映射到目标模块符号 |
| 赋值追踪 | `x = Foo` 后 `x.method()` 可解析 |
| super/self | `super().m()`、`self.m()` 方法解析 |
| 构造调用 | `Foo()` 关联 `Foo.__init__` |
| 继承边 | 调用图内 `type: inherit` 符号级边 |

输出 `callgraph.json` 含 `engine`、`stats.callEdgeCount`、`stats.inheritEdgeCount`。

> **PyCG 说明**：社区方案 [PyCG](https://github.com/vitsalis/PyCG) 精度更高，但 pip 包在 macOS 上 `PyCG`/`pycg` 大小写冲突，且在 Python 3.13 上 import hook 报错，暂未接入。若未来环境兼容可再评估。

## 引用图继承边

`project-graph.json` 的 `edges` 除 `type: import` 外，新增 `type: inherit`（模块级类继承，含 `symbol`/`base` 字段）。WebUI 引用图以紫色虚线展示。

1. TS 解析为正则，不处理 re-export 链、namespace、复杂泛型
2. Python 仅提取**顶层**符号，不递归类内方法
3. 外部包 import（如 `httpx`）不生成边
4. 动态 import / `__getattr__` 懒加载无法静态分析
5. 大图（500+ 节点）力导向布局可能拥挤，可考虑按包聚合

## 优化方向备忘

- [ ] TS 改用 `typescript` compiler API 或 tree-sitter
- [ ] Python 类内方法提取
- [ ] 按 `nanobot/agent/` 等子包折叠节点
- [ ] 引用类型细分：import / inherit / call
- [ ] 增量分析（仅变更文件）
