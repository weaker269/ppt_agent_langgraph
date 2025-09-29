# 项目概览
- 目标：构建一个基于 LangGraph 的演示文稿生成代理，输入文本后自动完成大纲规划、内容扩展、风格选择、质量评估与 HTML/PPT 渲染，并支持 Stub/真实 LLM 切换。
- 技术栈：Python 3 + LangGraph 工作流，Pydantic 定义领域模型，日志输出记录在 `logs/`，结果产物写入 `results/`，依赖管理通过 `requirements.txt`。
- 核心结构：
  - `main.py` 作为 CLI 入口，调用 `src/agent` 内的图式工作流。
  - `src/agent/domain.py` 定义 Pydantic 模型与枚举；`state.py` 管理状态；`graph.py` 组织 LangGraph 流程。
  - 子模块 `generators/`、`renderers/`、`validators/` 分别负责大纲、内容、风格、渲染与一致性检查。
- 运行输出：终端展示摘要，同时在 `results/` 下生成 HTML 与元数据，用于后续验证或上线对接。