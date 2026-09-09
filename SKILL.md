---
name: learn-project
description: >-
  Analyzes repository source code into import/call graphs and serves an interactive
  learnProject WebUI. Use when mapping project structure, execution scenarios,
  module dependencies, or setting up code visualization for any repo.
---

# learn-project

将仓库源码解析为**引用图谱 + 调用图 + 场景流**，通过 `learnProject/` 工作区与 WebUI 展示。

**解析实现位于本 skill**（`.cursor/skills/learn-project/learn_project/`），项目侧仅保留配置与数据。

## 快速执行

```bash
# 分析 + 启动 WebUI（nanobot 默认工作区）
bash .cursor/skills/learn-project/scripts/run.sh

# 指定工作区
python .cursor/skills/learn-project/scripts/analyze.py --workspace learnProject
cd learnProject && python server.py
```

## 适配其他项目

```bash
# 1. 初始化工作区
python .cursor/skills/learn-project/scripts/init_workspace.py \
  --target learnProject --name myapp \
  --source-dirs src pkg --python-packages myapp

# 2. 编辑 learnProject/learn-project.json（扫描目录、Python 包名等）
# 3. 编辑 learnProject/config/scenarios.json（执行场景，可留空）
# 4. 分析
python .cursor/skills/learn-project/scripts/analyze.py --workspace learnProject
```

## 目录职责

| 位置 | 职责 |
|------|------|
| `.cursor/skills/learn-project/learn_project/` | **通用解析库**（引用图、调用图、场景、trace） |
| `.cursor/skills/learn-project/scripts/` | CLI：`analyze.py` / `validate.py` / `collect_trace.py` / `init_workspace.py` |
| `learnProject/learn-project.json` | **项目配置**（扫描范围、包名、边界、trace 测试） |
| `learnProject/config/scenarios.json` | **项目场景数据**（手工维护执行流） |
| `learnProject/data/` | 生成物（graph / scenarios / callgraph / trace） |
| `learnProject/server.py` + `webui/` | 本地 WebUI（可复用） |
| `learnProject/scripts/*.py` | 薄封装，转发到 skill |

## 工作流

```
Task Progress:
- [ ] 1. 确认需求：新项目初始化 / 改扫描范围 / 优化解析 / 改 WebUI
- [ ] 2. 解析逻辑 → 改 skill `learn_project/`；项目配置 → 改 `learn-project.json`
- [ ] 3. `python .cursor/skills/learn-project/scripts/analyze.py --workspace learnProject`
- [ ] 4. 启动 server.py，验证 API 与 WebUI
- [ ] 5. 解析逻辑变更时同步 [reference.md](reference.md) 与 [sync.md](sync.md)
```

## 验证

```bash
python .cursor/skills/learn-project/scripts/analyze.py --workspace learnProject --strict
python .cursor/skills/learn-project/scripts/validate.py --workspace learnProject --strict
python .cursor/skills/learn-project/scripts/collect_trace.py --workspace learnProject  # 可选
```

## 附加资源

- 配置 schema、API、解析细节：[reference.md](reference.md)
- 变更同步清单：[sync.md](sync.md)
- 用户文档：`learnProject/README.md`
