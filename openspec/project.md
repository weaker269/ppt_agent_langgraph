# Project Context

## Purpose
本项目旨在构建一个基于 LangGraph 的 AI 演示文稿生成工作流，支持从原始文本输入到大纲规划、滑动窗口内容生成、质量评估与重试、跨页一致性检查以及 HTML 成果渲染的全链路自动化。目标是为咨询、市场、产品团队提供快速、风格统一、可追溯的 PPT 内容生产能力，并便于在真实模型与 Stub 离线模式之间切换。

## Tech Stack
- Python 3.10+（核心脚本语言）
- LangGraph / LangChain 组件（构建有状态的代理工作流）
- Pydantic 2.x（领域模型与数据校验）
- Sentence-Transformers + FAISS（语义检索与向量索引）
- Jinja2（HTML 渲染模板）
- PyMuPDF、python-docx、jieba 等中文内容处理库
- PyTest、Ruff（测试与静态检查）

## Project Conventions

### Code Style
- 遵循 PEP 8 与四空格缩进；函数、变量使用 snake_case，常量使用 UPPER_CASE。
- 所有注释、文档与提示词均使用中文描述逻辑与约束。
- 统一通过 `ruff check` 进行静态检查，提交前需保持无告警。
- 公共工具放置在 `src/utils.py`，这里的函数需要保持纯函数风格，避免隐藏状态。

### Architecture Patterns
- `main.py` 为 CLI 入口，负责解析参数并构建 `PPTAgentGraph`。
- `src/agent/graph.py` 使用 LangGraph 定义节点与边，形成生成器（generators）、评估器（evaluators）、验证器（validators）、渲染器（renderers）分层的流水线。
- `domain.py` 提供 Pydantic 数据模型（大纲、幻灯片、评估结果等）；`state.py` 管理工作流状态快照。
- 内容生成采用滑动窗口 + 反思重试模式，质量门槛设为 85 分；一致性校验单独占据节点以保证跨页约束。
- RAG 相关逻辑集中在 `src/rag`，默认使用递归分块 + 语义检索 + 精排策略，并记录元数据以支持追溯。

### Testing Strategy
- 使用 `pytest` 作为测试框架，测试文件遵循 `tests/test_*.py` 命名。
- `tests/test_domain.py` 覆盖核心模型约束，`tests/test_workflow.py` 在 Stub 模式下回归整条链路。
- 新增能力需覆盖主流程与关键分支，并确保质量分、重试次数等关键指标被断言。
- 本地提交前建议运行 `pytest -q`，并在需要时增加 fixtures 到 `tests/fixtures`。

### Git Workflow
- 建议以小步提交配合 PR 评审；分支可采用 `feature/<模块>`、`fix/<问题>` 等语义化命名。
- 提交信息使用动词 + 描述格式（如 `feat: refine outline filter`），并在 PR 中说明背景、改动、验证命令。
- 合并前需确保 `ruff check` 与 `pytest` 均通过；涉及 CLI 参数或公共模型的改动需同步更新 README 与 `docs/QUICK_VALIDATION.md`。

## Domain Context
- 服务对象以中文商务/技术演示为主，强调章节逻辑完整、跨页术语统一与风格一致性。
- 大纲生成、滑动窗口内容生成与质量评估共享同一批检索证据块，禁止脱离证据的自由扩写。
- 输出默认为带主题的 HTML，总结模块需附带质量评分、重试次数及一致性检查结果，便于快速评估交付品质。

## Important Constraints
- 默认离线运行，模型调用需通过 `.env` 或环境变量注入密钥，禁止将真实密钥写入仓库。
- 质量评估评分低于 85 分时必须触发重试，最大重试次数需遵循配置；一致性校验失败时需要输出问题清单而非强行通过。
- RAG 流程需记录来源文件、偏移量等元数据，确保生成内容可追溯；检索失败时必须按降级策略记录风险。
- 日志与结果文件落地在 `logs/` 与 `results/` 目录，需留意敏感信息脱敏与存储空间控制。

## External Dependencies
- OpenAI、Google Generative AI 等 LLM 服务（根据 `model_provider` 注入，需 API Key）。
- Sentence-Transformers 预训练模型（默认 `all-MiniLM` 系列，可按需替换）。
- FAISS CPU 索引用于向量检索；BM25、jieba 用于中文分词与关键词检索。
- PyMuPDF / python-docx 用于从 PDF、Docx 文档提取文本，支持自定义素材。
