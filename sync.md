# learn-project 同步清单

**规则**：解析/API 逻辑改 skill；项目专属场景/边界改 `learnProject/learn-project.json` 与 `config/scenarios.json`。

## 触发条件 → 必改文件

| 变更类型 | 改动位置 | 同步 |
|----------|----------|------|
| 扫描/解析/调用图 | `learn_project/*.py` | `reference.md` |
| CLI 入口 | `scripts/analyze.py` 等 | `SKILL.md` 快速执行 |
| 工作区配置 schema | `learn_project/config.py` | `reference.md` learn-project.json |
| WebUI / server | `learnProject/webui/`、`server.py` | `reference.md` API/行为表 |
| nanobot 场景/边界 | `learnProject/config/scenarios.json`、`learn-project.json` | 无需改 skill |

## 一致性检查

1. `learn-project.json` 字段 ↔ `reference.md` 配置表
2. `learn_project/config.py` 默认值 ↔ 文档
3. CI 使用 skill 脚本路径 ↔ `SKILL.md`
4. 薄封装 `learnProject/scripts/` 仍能调用 skill

## 基线（2026-09-09）

```
moduleCount: 479, edgeCount: 1226, callEdges: ~4394, inheritEdges: ~129
```
