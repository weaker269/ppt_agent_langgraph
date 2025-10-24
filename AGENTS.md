<!-- OPENSPEC:START -->
# OpenSpec Instructions

These instructions are for AI assistants working in this project.

Always open `@/openspec/AGENTS.md` when the request:
- Mentions planning or proposals (words like proposal, spec, change, plan)
- Introduces new capabilities, breaking changes, architecture shifts, or big performance/security work
- Sounds ambiguous and you need the authoritative spec before coding

Use `@/openspec/AGENTS.md` to learn:
- How to create and apply change proposals
- Spec format and conventions
- Project structure and guidelines

Keep this managed block so 'openspec update' can refresh the instructions.

<!-- OPENSPEC:END -->

# Repository Guidelines（仓库指引）

## 项目结构与模块组织
仓库以 `main.py` 为 CLI 入口，调用 `src/agent/graph.py` 构建 PPTAgentGraph；`src/agent` 按角色拆分 generators、renderers、evaluators、validators，`domain.py` 汇集 Pydantic 模型，`state.py` 管理运行态；业务素材放在 `prompts`、`docs`，执行结果落地 `results`，日志保存在 `logs`，自动化样例集中于 `example_input.txt`，测试资产统一归档于 `tests`。

## 构建、测试与开发命令
首次进入建议执行：
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```
快速试跑 `python main.py --text "演示主题" --model-provider stub --use-stub`；批量处理文本用 `python main.py --file docs/sample.txt`；执行回归 `pytest -q`，定位流程一致性运行 `pytest tests/test_workflow.py -k consistency`，观察重试逻辑执行 `pytest -k retry`。

## 代码风格与命名规范
遵循 PEP 8 与四空格缩进，函数与变量采用 snake_case，常量和枚举使用 UPPER_CASE；公共工具置于 `src/utils.py`，提示模板改动需同步更新 `prompts` 内文并补充中文注释；提交前务必运行 `ruff check` 与 `pytest` 以确认风格及行为稳定。

## 测试指南
统一使用 pytest，文件命名遵循 `test_*.py`；新增功能至少覆盖主路径与边界场景，断言质量评分、重试次数与输出文案；测试若依赖外部样例，请写入 `tests/fixtures` 并确保可重复执行。

## 提交与合并请求规范
推荐使用动词前缀提交信息，如 `feat: refine outline filter`；PR 需说明背景、核心改动、验证命令与关键输出（例如 `results/2024-xx-xx/*.html`），若涉及 CLI 参数或公共模型，请同步更新 README 与 `docs/QUICK_VALIDATION.md` 并标注兼容性风险。

## 安全与配置提示
默认离线运行，密钥通过 `.env` 或环境变量注入，禁止写回仓库；真实模型上线前配置超时、速率与告警策略，分享日志须先脱敏；若检索或索引失败，请记录降级路径并在 `TODO.md` 内同步状态。

## RAG 优化执行指引
- 默认采用 **递归分块 + 语义检索 + 精排** 作为文档锚定主线，确保 PPT 生成引用原文证据。
- 分块流程：章节 → 段落 → 句群，块长控制在 200~300 汉字并保留 1-2 句重叠；每个块需记录来源文件、偏移量等元数据，便于追溯。
- 内容生成、质量评估、一致性检查共用同一批证据块与滑动摘要，禁止各自拼接不同上下文导致逻辑漂移。
- 检索失败或索引不可用时必须触发降级策略并记录风险，严禁在无证据约束下让 LLM 自由扩写。
- 详细任务拆分、进度与策略更新请参阅 TODO.md 并同步维护两份文档。