## 优化路线图（RAG 文档锚定 + PPT 生成链路增强）

> 标记规则：`[ ]` 待办 ｜ `[~]` 进行中 ｜ `[x]` 完成  
> 完成后请在“完成记录”处追加 `YYYY-MM-DD @成员` + 简述改动、效果与数据指标

---

### 0. 使用说明
- 执行任一任务前先在“完成记录”登记状态变更；如需拆分子任务，可在同级下补充 `- [ ] 子任务`。
- 若任务涉及代码改动，请同步补充对应模块 / 文件路径，便于后续 Code Review。
- 任务完成后，除更新本表外，如需对团队规范/原则有永久影响，需同步更新 `AGENTS.md`（见任务四）。

---

### 一、文档锚定（方案二：层级分块 + 语义检索 RAG）

#### 1.1 嵌入模型与索引选型
- [x] **目标**：确定中文嵌入模型、向量库与部署方式，为后续检索提供能力基线。  
- **实现路径**：对比 `BAAI/bge-large-zh-v1.5`、`text2vec-base-chinese`、`m3e-base`；以 `sentence-transformers` 进行离线评估（余弦相似度 + Top-K 命中率）。  
- **工具/依赖**：`sentence-transformers`、`faiss-cpu`、`rank-bm25`（用于关键词对照）。  
- **产出**：  
  - 评测脚本 `scripts/eval_embeddings.py`（输出命中率、平均相似度、耗时）。  
  - 结论记录在 `docs/rag/embedding_selection.md`。  
- **验收标准**：指定模型在测试语料上的 Top-5 召回率 ≥ 0.85，向量构建耗时满足批量场景（1000 chunk < 5s）。  
- **完成记录**：
  - 2025-10-11 @Codex 完成评测：新增 `scripts/eval_embeddings.py`、`docs/rag/embedding_eval_samples.jsonl`、`docs/rag/embedding_selection.md`，生成 `results/embedding_eval.json`；`text2vec-base-chinese` Top-5 召回率 1.0，`bge-large` Top-5 召回率 0.67，建议先以前者 + BM25 组合作为基线方案。

#### 1.2 文档解析与递归分块实现
- [x] **目标**：生成统一的 `DocumentChunk` 数据结构，覆盖 Markdown、纯文本、PDF、Word。  
- **实现路径**：  
  - 新增 `src/rag/loaders.py`：封装 `markdown` / `plain text` / `pymupdf` / `python-docx` 解析。  
  - 新增 `src/rag/chunkers.py`：递归分割（章节→段落→句群），块长控制 200~300 汉字，重叠 1-2 句；截取时保留源文件名、章节标题、偏移量。  
  - 对无明显结构的文档，启用基于句号/换行的分段 + 字符窗口 fallback。  
- **工具/依赖**：`pymupdf`、`python-docx`、`langchain-text-splitters` 或自研 splitter；中文断句可用 `regex + jieba`。  
- **产出**：  
  - Pydantic 模型 `DocumentChunk`（新增文件 `src/rag/models.py`）。  
  - 单元测试 `tests/rag/test_chunkers.py` 覆盖多格式输入。  
- **验收标准**：随机抽取 10 篇文档，人工确认 chunk 语义完整度 ≥ 90%；单文档分块时延 < 1s/万字。  
- **完成记录**：
  - 2025-10-11 @Codex 新增 `src/rag/{models,loaders,chunkers}.py` 与 `tests/rag/test_chunkers.py`，实现 Markdown/纯文本/PDF/Docx 解析与递归分块，补充 PyMuPDF、python-docx 依赖；`pytest tests/rag/test_chunkers.py -q` 通过，验证多格式 chunk 长度与元数据正确。

#### 1.3 索引构建与双阶段检索
- [ ] **目标**：实现 BM25 + 向量召回，再用交叉编码器重排，输出 Top-N 证据块。  
- **实现路径**：  
  - 新增 `src/rag/index.py`：Faiss index + metadata 存储（可选 SQLite/Parquet）。  
  - 新增 `src/rag/retriever.py`：  
    1. BM25 初筛（`rank_bm25`）。  
    2. 向量检索（Faiss）。  
    3. 交叉编码器重排（建议 `BAAI/bge-reranker-large` 或 `cross-encoder/ms-marco-MiniLM-L-6-v2` 作为备选）。  
  - 支持批量查询、缓存最近查询结果，写入 `snapshots/<run>/retrieval`。  
- **工具/依赖**：`faiss-cpu`、`rank-bm25`、`transformers`（交叉编码器）、`numpy`。  
- **产出**：  
  - 检索 API：`retrieve_evidence(query: str, top_k: int = 5) -> List[DocumentChunk]`。  
  - 集成测试 `tests/rag/test_retriever.py`（构造小型语料验证排序效果）。  
- **验收标准**：真实样本上平均响应 < 200ms/查询（CPU 环境），Top-3 命中率 ≥ 0.9；若交叉编码器耗时过高需提供降级（仅向量 + BM25 混合评分）。  
- **完成记录**：

#### 1.4 生成链路集成
- [ ] **目标**：在内容生成/质量评估/一致性阶段注入证据块，保持上下游一致。  
- **实现路径**：  
  - 修改 `SlidingWindowContentGenerator._create_content_slide`：  
    * 将 `key_point` 与滑窗摘要组成检索 query。  
    * 选取 Top-N 证据（建议 2-3 条，每条控制在 120 汉字以内），写入 prompt 的 `EVIDENCE_SECTION`。  
  - 调整 `_GENERATON_PROMPT_TEMPLATE` 与 `_REFLECTION_PROMPT_TEMPLATE`，新增 “参考原文证据” 模块，明确禁止超出证据范围编造事实。  
  - `QualityEvaluator.evaluate` 与 `ConsistencyChecker.check` 调用检索接口，以相同 query 注入证据，维护日志。  
- **工具/依赖**：现有 LLM 调用框架；新增 prompt 片段建议使用 `jinja2` 模板化以减少字符串拼接错误。  
- **产出**：  
  - 代码改动 diff（记录在完成日志中）。  
  - 快照示例：`snapshots/<run>/03_content/slide_XX_evidence.json`。  
- **验收标准**：至少完成一次端到端运行，验证每页 prompt 中包含证据内容，HTML 输出可追踪 `metadata` 中的证据 ID 列表。  
- **完成记录**：

#### 1.5 监控、回退与性能评估
- [ ] **目标**：保证检索链路的稳定性与透明性。  
- **实现路径**：  
  - 新增 `src/rag/metrics.py`：记录命中率、响应时间、降级次数，输出到 `logs/rag_metrics.jsonl`。  
  - 定义降级策略（例如：检索空结果 → 退回 Outline-based 段落；交叉编码器超时 → 记录 warning 并跳过精排）。  
  - 编写性能回归脚本 `scripts/benchmark_retrieval.py`，定期跑批。  
- **验收标准**：日志中有结构化记录；在多次运行中验证降级路径有效且有告警。  
- **完成记录**：

---

### 二、滑动窗口信息增强

#### 2.1 滑窗摘要结构升级
- [ ] **目标**：让 `SlidingSummary` 携带主旨、关键事实、证据引用，支撑上下文衔接。  
- **实现路径**：  
  - 扩展 `SlideSummary` 模型：新增字段 `supporting_evidence_ids: List[str]`、`transition_hint: str`。  
  - 新增函数 `build_slide_summary(slide: SlideContent, evidence: List[DocumentChunk])`，使用 `text_tools` 对 `speaker_notes + evidence` 生成 150 字以内的摘要。  
- **工具/依赖**：`textwrap`、`jieba` 或 `ruotian-nlp` 做中文句子切分；必要时使用轻量 LLM 复写摘要（可选）。  
- **验收标准**：随机抽样 5 页，确认摘要涵盖本页主旨且引用 evidence ID。  
- **完成记录**：

#### 2.2 Prompt 注入与格式对齐
- [ ] **目标**：统一内容生成、质量评估、反思的上下文格式。  
- **实现路径**：  
  - 修改 `_format_context` 输出：从标题列表升级为 “上一页摘要 + 关键数据点 + 对应证据 ID”。  
  - 在生成/评估 prompt 中添加 `CONTEXT_SUMMARY` section，固定格式：  
    ```text
    <SlideContext>
      - Slide #2 主旨：...（evidence: DOC_12, DOC_45）
      - Slide #3 主旨：...
    </SlideContext>
    ```  
  - 调整 Quality/Consistency prompt，强调需检查与上下文是否一致。  
- **验收标准**：运行后查看快照，确保 prompt 按新格式输出并无 JSON 解析问题。  
- **完成记录**：

#### 2.3 配置化与可视化
- [ ] **目标**：使滑窗长度、证据数量、摘要策略可配置。  
- **实现路径**：  
  - 在 `OverallState` 中新增 `window_config`（例如 `max_prev_slides`、`max_evidence_per_slide`）。  
  - CLI / `.env` 支持覆盖该配置。  
  - 在结果 HTML 中新增 “上下文摘要” 面板，展示上一页摘要与证据链接。  
- **工具/依赖**：现有 `HTMLRenderer`；可用少量 `Alpine.js` 或原生 JS 展示折叠面板。  
- **验收标准**：配置改动能影响生成行为；HTML 中显示上下文摘要且样式一致。  
- **完成记录**：

---

### 三、一致性与反思联动

#### 3.1 质量评估证据化
- [ ] **目标**：让质量评估 LLM 明确引用证据来判定问题，减少漏检。  
- **实现路径**：  
  - 在 `QualityEvaluator` prompt 中新增 `Evidence` section；若 evidence 空则显式提示风险。  
  - 评估结果 `QualityFeedback` 引入 `evidence_refs` 字段，指明问题来源。  
- **验收标准**：质量反馈中能看到证据编号，且反思阶段可读取。  
- **完成记录**：

#### 3.2 反思阶段闭环
- [ ] **目标**：确保反思 prompt 包含所有必要信息并约束改写范围。  
- **实现路径**：  
  - `_regenerate` 生成 prompt 时附加：质量反馈摘要、上下文摘要、证据原文。  
  - 对反思生成的幻灯片校验：必须引用原证据或说明新增证据（并触发检索）。  
- **验收标准**：触发反思的页面在第二版输出中问题减少且保留证据引用。  
- **完成记录**：

#### 3.3 一致性检查增强
- [ ] **目标**：将一致性问题定位到证据层，便于人工排查。  
- **实现路径**：  
  - `ConsistencyChecker` 获取证据后，对比跨页用词、数据；问题结构中加入 `evidence_refs`。  
  - 若模型返回的问题缺乏证据，记录 warning 并建议人工复核。  
- **验收标准**：一致性报告中包含证据引用，且重复/矛盾页可快速定位。  
- **完成记录**：

---

### 四、文档与协作规范

#### 4.1 TODO.md 维护
- [ ] **目标**：保持任务表与实际进度一致。  
- **要求**：每次完成任何任务或子任务时，更新 `[ ]` → `[x]` 并在完成记录中填入实际信息（改动文件、关键指标）。  
- **完成记录**：

#### 4.2 AGENTS.md & 其他文档
- [ ] **目标**：将经过验证的策略/原则沉淀到团队规范。  
- **实现路径**：  
  - 当 RAG 策略、滑窗规则、降级方案等成熟后，更新 `AGENTS.md` 对应章节。  
  - 对外文档（如 `README.md`、`docs/`）同步新增使用说明或配置项。  
- **验收标准**：团队成员可从文档获得完整指导，无需追溯历史讨论。  
- **完成记录**：

---

### 附：完成记录示例
```
2025-10-10 @Alice
- 完成 1.2 文档解析：新增 src/rag/chunkers.py、tests/rag/test_chunkers.py
- 效果：对 sample.md / sample.pdf 分块后人工检查语义完整度 95%，平均耗时 0.6s/万字
```
