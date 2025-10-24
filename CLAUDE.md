# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

这是一个基于 LangGraph 的 AI 演示文稿生成系统，能够从文本输入自动生成结构化的 PPT。系统包含：大纲规划、内容生成（含滑动窗口上下文）、质量评估与反思重试、一致性检查、RAG 文档锚定、以及 HTML 渲染等完整链路。

**核心特性**：
- 支持 Stub 模式（离线快速验证）和真实 LLM 模式（OpenAI/Google）
- RAG 证据检索系统（递归分块 + 混合检索 + 重排）
- 质量评估驱动的反思优化（85 分阈值重试）
- 跨页面一致性审查
- 可配置的样式主题与图表配色

## 技术栈

- **语言**: Python 3.x，使用 `uv` 进行依赖管理
- **核心框架**: LangGraph 工作流编排
- **数据模型**: Pydantic 2.x（严格类型定义）
- **LLM 集成**: OpenAI、Google Gemini（通过 `ai_client.py` 统一封装）
- **RAG 组件**: sentence-transformers、faiss-cpu、rank-bm25
- **文档解析**: PyMuPDF（PDF）、python-docx（Word）、内置 Markdown/文本解析器
- **测试**: pytest

## 开发环境设置

```bash
# 创建虚拟环境（务必使用 uv）
uv venv

# 激活虚拟环境
source .venv/bin/activate  # Linux/Mac
# 或 .\.venv\Scripts\activate  # Windows

# 安装依赖
uv pip install -r requirements.txt

# 配置环境变量（复制 .env.example 到 .env 并填入 API Keys）
# 必要变量：OPENAI_API_KEY 或 GOOGLE_API_KEY
```

## 常用命令

### 运行 PPT 生成

```bash
# Stub 模式（无需 API Key，快速验证流程）
python main.py --text "人工智能发布计划" --model-provider stub --use-stub

# 真实模型模式（需配置 API Key）
python main.py --file docs/sample.txt --model-provider openai --model-name gpt-4o

# 从文件读取输入
python main.py --file example_input.txt --model-provider google --model-name gemini-2.5-pro
```

### 测试

```bash
# 运行所有测试
pytest -q

# 运行特定测试文件
pytest tests/test_workflow.py -v

# 运行包含特定关键字的测试
pytest -k "consistency" -v  # 一致性检查相关测试
pytest -k "retry" -v        # 重试逻辑相关测试
pytest -k "rag" -v          # RAG 检索相关测试

# 查看测试覆盖率
pytest --cov=src tests/
```

### RAG 评估与基准测试

```bash
# 评估嵌入模型性能
python scripts/eval_embeddings.py

# 检索性能基准测试
python scripts/benchmark_retrieval.py
```

## 核心架构

### 工作流节点（LangGraph）

整个流程由 `src/agent/graph.py` 中的 `PPTAgentGraph` 编排，主要节点包括：

```
输入文本 
  ↓
准备 RAG 索引（_prepare_rag）
  ↓
大纲生成（OutlineGenerator）
  ↓
样式选择（StyleSelector）
  ↓
滑动窗口内容生成（SlidingWindowContentGenerator）
  ├─ 质量评估（QualityEvaluator）
  └─ 反思重试（达到 85 分阈值或重试上限）
  ↓
一致性检查（ConsistencyChecker）
  ↓
HTML 渲染（HTMLRenderer）
  ↓
输出持久化
```

### 目录结构

- **`src/agent/`**: 核心工作流逻辑
  - `graph.py`: PPTAgentGraph 主流程编排
  - `state.py`: OverallState 状态管理（Pydantic 模型）
  - `domain.py`: 领域模型定义（PresentationOutline、SlideContent、QualityScore 等）
  - `ai_client.py`: LLM 客户端统一封装（支持 OpenAI/Google/Stub）
  - `generators/`: 大纲生成器、内容生成器、样式选择器
  - `evaluators/`: 质量评估器
  - `validators/`: 一致性检查器
  - `renderers/`: HTML 渲染器

- **`src/rag/`**: RAG 文档检索系统
  - `models.py`: DocumentChunk、LoadedDocument 等数据模型
  - `loaders.py`: Markdown/PDF/Word/纯文本解析器
  - `chunkers.py`: 递归分块器（章节→段落→句群）
  - `index.py`: ChunkIndex（Faiss + BM25 索引构建）
  - `retriever.py`: HybridRetriever（混合检索 + 重排）
  - `metrics.py`: 检索性能监控与降级策略

- **`tests/`**: pytest 测试套件
  - `test_domain.py`: 领域模型验证
  - `test_workflow.py`: 端到端流程回归（基于 Stub）
  - `rag/`: RAG 子系统测试（分块、检索、评估）
  - `agent/`: Agent 逻辑测试（证据流、质量评估）

- **`results/`**: 生成的 HTML 输出与元数据 JSON
- **`logs/`**: 日志输出目录（包括 `rag_metrics.jsonl`）
- **`prompts/`**: LLM 提示词模板（若需自定义）
- **`docs/`**: 项目文档与快速验证指南

## 关键设计原则

### 1. RAG 文档锚定策略

**核心思想**：所有内容生成必须基于证据块，禁止 LLM 自由扩写。

- **分块规则**：200-300 汉字，保留 1-2 句重叠，记录元数据（文件名、章节标题、偏移量）
- **检索流程**：BM25 初筛 → Faiss 向量检索 → 重排（可选）→ Top-N 证据
- **证据注入位置**：
  - 内容生成：`SlidingWindowContentGenerator._create_content_slide`
  - 质量评估：`QualityEvaluator.evaluate`
  - 一致性检查：`ConsistencyChecker.check`
- **降级策略**：索引构建失败 → 记录 warning + 退回 Outline-based 生成

### 2. 滑动窗口上下文管理

**目的**：保持跨页面逻辑衔接与术语一致性。

- **窗口内容**：前 N 页的摘要（主旨 + 关键概念 + 证据引用）
- **上下文格式化**：`_format_context` 输出结构化的 `<SlideContext>` 片段
- **注入节点**：生成 prompt、评估 prompt、反思 prompt

### 3. 质量反思机制

**触发条件**：单页质量分 < 85 分

- **评估维度**：logic（逻辑）、relevance（相关性）、language（语言）、layout（布局）
- **反思流程**：
  1. `QualityEvaluator` 返回 `QualityFeedback`（问题描述 + 改进建议）
  2. `_regenerate` 生成新 prompt（包含质量反馈 + 原证据 + 上下文摘要）
  3. 重试上限：`max_retry_rounds`（默认 1 次）
- **快照记录**：每次重试的 prompt、输出、评分均保存到 `snapshots/`

### 4. 一致性检查

**检查维度**：
- 逻辑断裂（logical_break）
- 风格不一致（style_inconsistency）
- 术语冲突（terminology_mismatch）
- 冗余内容（redundant_content）
- 结构违规（structure_violation）

**输出**：`ConsistencyReport`（问题清单 + 建议 + 整体评分）

## 代码规范

### 类型约束
- **严格使用 Pydantic**：所有领域模型继承 `BaseModel`
- **禁止未定义的 dict**：若必须使用，需先征得同意
- **类型注解**：所有函数签名必须包含参数与返回值类型

### 命名约定
- **变量/函数**：snake_case（例：`generate_outline`）
- **类**：PascalCase（例：`OutlineGenerator`）
- **枚举/常量**：UPPER_CASE（例：`SlideType.CONTENT`）

### 模块化拆分
- **单一职责**：每个生成器/评估器/验证器只负责一个功能
- **依赖注入**：LLM 客户端通过构造函数传入，便于测试
- **公共工具**：`src/agent/utils.py`（logger、result_saver、snapshot_manager）

### 日志规范
- **中文信息**：CLI 输出与日志消息统一使用简体中文
- **结构化日志**：关键节点记录 run_id、耗时、质量分、重试次数
- **快照机制**：`snapshot_manager.write_json` 持久化中间产物到 `snapshots/<run_id>/`

## 测试要求

### 必须覆盖的场景
1. **领域模型验证**（`test_domain.py`）：字段校验、默认值、边界条件
2. **端到端流程**（`test_workflow.py`）：Stub 模式下的完整链路
3. **RAG 子系统**：
   - 分块语义完整性（`test_chunkers.py`）
   - 检索召回率与响应时间（`test_retriever.py`）
   - 降级策略触发（`test_metrics.py`）
4. **质量评估与重试**：触发反思、达到阈值、超过重试上限

### 断言重点
- 输出结构符合 Pydantic 模型定义
- 质量分在合理范围（0-100）
- 一致性问题数量与严重度符合预期
- HTML 输出包含必要的图表与样式

### 测试数据
- 使用 `example_input.txt` 作为基准输入
- 自定义测试语料放在 `tests/fixtures/`
- 避免依赖外部 API（优先使用 Stub 模式）

## 常见任务指南

### 新增一个 LLM 节点

1. 在 `src/agent/generators/`、`evaluators/` 或 `validators/` 下创建新文件
2. 定义类，接受 `AIModelClient` 作为构造参数
3. 实现核心方法（例：`generate`、`evaluate`、`check`）
4. 在 `domain.py` 中定义输入/输出模型（Pydantic）
5. 在 `graph.py` 的 `PPTAgentGraph` 中集成该节点
6. 编写对应的单元测试（优先 Stub 模式）
7. 更新 `TODO.md` 的完成记录

### 修改 Prompt 模板

1. 找到对应的生成器/评估器文件（例：`generators/outline.py`）
2. 修改 `_PROMPT_TEMPLATE` 常量（建议使用 f-string 或 jinja2）
3. 确保新增的证据/上下文片段格式一致
4. 在 Stub 模式下验证输出是否符合预期
5. 运行 `pytest -k <相关测试>` 确保无回归

### 调整 RAG 检索策略

1. **修改分块参数**：`src/rag/chunkers.py` 的 `chunk_size`、`sentence_overlap`
2. **调整检索权重**：`retriever.py` 的 `alpha`（BM25 vs 向量权重）
3. **更换嵌入模型**：环境变量 `RAG_EMBEDDING_MODEL` 或 `graph.py` 的 `_resolve_embedding_model_source`
4. **添加重排器**：在 `HybridRetriever` 中集成交叉编码器
5. **验证性能**：运行 `scripts/benchmark_retrieval.py` 查看 Top@K 命中率

### 扩展质量评估维度

1. 在 `domain.py` 的 `QualityDimension` 枚举中新增维度
2. 修改 `QualityEvaluator` 的 prompt，明确评分标准
3. 调整 `QualityScore.dimension_scores` 的聚合逻辑
4. 更新 `HTMLRenderer` 以可视化新维度评分
5. 补充测试用例验证新维度的分数范围

## 故障排查

### RAG 索引构建失败
- **症状**：日志显示 "RAG 索引构建失败" warning
- **原因**：缺少 sentence-transformers 或嵌入模型下载失败
- **解决**：
  1. 安装依赖：`uv pip install sentence-transformers`
  2. 检查网络或使用本地模型路径（环境变量 `RAG_EMBEDDING_MODEL_PATH`）
  3. 查看 `logs/` 中的详细错误堆栈

### 质量评估卡在重试循环
- **症状**：某一页反复重试但分数始终低于阈值
- **原因**：证据不足或 prompt 指令不明确
- **解决**：
  1. 检查 `snapshots/<run_id>/03_content/slide_XX_evidence.json` 是否为空
  2. 调整 `max_retry_rounds` 或降低阈值（临时方案）
  3. 优化 `_REFLECTION_PROMPT_TEMPLATE`，增加约束

### 一致性报告误报
- **症状**：ConsistencyReport 显示大量问题但人工检查无误
- **原因**：LLM 对术语/风格过于敏感
- **解决**：
  1. 在 `ConsistencyChecker` 的 prompt 中增加"宽容度"指示
  2. 调整问题严重度阈值（例：仅报告 high/critical）
  3. 提供反例样本，优化 prompt

## 注意事项

- **永远不要直接使用 pip**：必须通过 `uv pip` 管理依赖
- **保持 .env 机密**：API Keys 禁止提交到版本控制
- **Stub 优先验证**：新功能先在 Stub 模式下测试，避免消耗 API 配额
- **同步更新 TODO.md**：完成任务后及时更新完成记录与改动文件
- **快照用于调试**：`snapshots/` 目录包含每次运行的中间产物，排查问题时优先查看
- **日志结构化**：关键节点必须记录 run_id、耗时、质量分，便于后续分析

## 相关文档

- **快速验证指南**：`docs/QUICK_VALIDATION.md`
- **RAG 嵌入模型评估**：`docs/rag/embedding_selection.md`
- **任务进度跟踪**：`TODO.md`
- **OpenSpec 变更提案规范**：`openspec/AGENTS.md`
