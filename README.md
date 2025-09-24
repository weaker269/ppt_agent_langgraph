# PPT Agent (Lightweight LangGraph Workflow)

## 项目概览
该项目实现了一个可离线运行的演示文稿生成流程：给定一段文本或文件，自动生成大纲、幻灯片结构以及可预览的 HTML。优化后系统完全摆脱外部 LLM 依赖，适合快速验证演示内容质量或作为二次开发基线。

## 核心架构
```
main.py → PPTAgentGraph
          ├─ OutlineGenerator     # 文本 → PresentationOutline
          ├─ StyleSelector        # 标题/关键词 → 基础主题
          ├─ SlideComposer        # 大纲 → SlideContent 列表
          └─ HTMLRenderer         # 幻灯片 → 内置 HTML 模板
```
共享数据模型集中在 `src/agent/domain.py`，全局状态由 `src/agent/state.py` 管理；日志、结果保存逻辑在 `src/agent/utils.py`。

主要目录：
- `src/agent/` – 核心实现：领域模型、生成器、渲染器、顺序工作流
- `docs/` – 文档（快速验证指南等）
- `tests/` – 单元与集成测试

## 环境准备
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
> 依赖仅包含 `pydantic`、`jinja2`、`pytest`，可在无网络环境下安装（本地镜像）。

## 快速运行
```bash
python main.py --text "人工智能发布计划"
```
或使用文件：
```bash
python main.py --file docs/sample.txt
```
程序将在终端输出生成摘要，并在 `results/` 目录写入 `*.html` 及元数据 JSON。若希望指定文件名前缀，可使用 `--name`。

更多运行细节与输入建议见 `docs/QUICK_VALIDATION.md`。

## 定制与扩展
- **大纲策略** (`OutlineGenerator`): 可将启发式拆分替换为真实 LLM 或自定义算法。
- **幻灯片布局** (`SlideComposer`): 可扩展 `SlideType`/`SlideLayout` 枚举，或引入更多要点展开规则。
- **模板输出** (`HTMLRenderer`): 当前使用内置 Jinja 字符串，可接入外部模板文件或导出 PPTX。

自定义组件时建议：
1. 在 `domain.py` 扩展新的模型/枚举；
2. 添加对应的测试覆盖（见下节）。

## 测试
```bash
pytest -q
```
- `tests/test_domain.py`: 验证核心模型与枚举
- `tests/test_workflow.py`: 端到端流程验证（默认文本样例）

## 变更记录（与重构前比较）
- 移除了错误恢复、质量反思等复杂机制，保留最小可运行主干。
- 合并并精简领域模型，避免跨模块不一致。
- 将工作流改写为单一顺序流程，支持离线快速验证。
- 新增文档与测试，提供标准化运行与扩展指引。

欢迎根据业务需求继续演进：可逐步引入真实模型、增加输出格式或与现有知识库对接。
