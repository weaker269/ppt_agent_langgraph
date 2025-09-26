# PPT Agent (LangGraph Workflow)

## 项目概览
该项目构建了一个可扩展的 AI 驱动演示生成流程：给定文本输入，自动完成大纲规划、滑动窗口式幻灯片生成、质量反思重试、跨页一致性审查，以及带主题的 HTML 输出。系统提供 Stub 与真实模型两种模式，既能离线快速验证，也便于切换在线 LLM。

## 核心架构
```
main.py → PPTAgentGraph
          ├─ OutlineGenerator         # 文本 → PresentationOutline (LLM + 回退)
          ├─ StyleSelector            # 动态样式分析与主题选取
          ├─ SlidingWindowContentGenerator
          │     ├─ 滑动窗口上下文
          │     ├─ 质量评估 + 85 分阈值重试
          │     └─ 反思优化 (初始 / 再生成)
          ├─ QualityEvaluator         # 多维度评分、结构化反馈
          ├─ ConsistencyChecker       # 跨页面逻辑/术语/风格检查
          └─ HTMLRenderer             # 带主题和质量摘要的 HTML 输出
```
共享模型定义于 `src/agent/domain.py`，状态管理在 `src/agent/state.py`，LLM 客户端封装见 `src/agent/ai_client.py`。

## 运行环境
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
依赖包含 `openai` 与 `google-generativeai`，可根据 `.env` 的 `DEFAULT_MODEL_PROVIDER` 切换使用的模型。首次运行会自动读取 `.env` 并写入环境变量，确保已在文件中配置 `GOOGLE_API_KEY` / `OPENAI_API_KEY` 等凭据。

## 快速体验
```bash
python main.py --text "人工智能发布计划" --model-provider stub --use-stub
```
或使用真实模型：
```bash
export OPENAI_API_KEY=...
python main.py --file docs/sample.txt --model-provider openai --model-name gpt-4o
```
执行完成后终端会输出摘要，同时在 `results/` 目录生成 HTML 与 metadata JSON（包含质量分、风格、重试次数等信息）。更多验证建议见 `docs/QUICK_VALIDATION.md`。

## 自定义能力
- **大纲生成 (`generators/outline.py`)**：可更换提示词或接入自定义算法。
- **内容生成 (`generators/content.py`)**：滑动窗口与反思逻辑可扩展，例如加入多模型投票或模板填充。
- **质量评估 (`evaluators/quality.py`)**：支持自定义打分维度、阈值和反馈口径。
- **一致性检查 (`validators/consistency.py`)**：可增强术语检测或加入自定义的风格审计规则。
- **样式与渲染 (`generators/style.py`, `renderers/html.py`)**：可以挂接外部模板、PPTX 导出或品牌配色库。

## 测试
```bash
pytest -q
```
- `tests/test_domain.py`：校验核心模型及属性
- `tests/test_workflow.py`：基于 Stub 的端到端流程回归（含质量/一致性验证）

## 关键特性回顾
- 文本解析 → 大纲生成 → 滑动窗口内容 → HTML 渲染全链路自动化。
- 多维度质量评估、85 分阈值重试、结构化反馈、双模式生成。
- 样式智能选择、色板/字体/布局配置 + 可视化质量摘要。
- 跨页面一致性审查，输出问题清单与建议。
- Stub 与真实模型可切换，便于本地验证与生产环境扩展。
