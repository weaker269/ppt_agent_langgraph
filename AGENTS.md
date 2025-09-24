# Repository Guidelines

## Project Structure & Module Organization
`main.py` 负责 CLI 入口，直接调用 `src/agent` 暴露的 API。领域模型集中在 `src/agent/domain.py`，全局状态在 `src/agent/state.py`，顺序式工作流封装在 `src/agent/graph.py`。大纲/内容/样式/渲染分别位于 `src/agent/generators/` 与 `src/agent/renderers/`。运行日志与输出存放在 `logs/`、`results/` 目录。

## Build, Test, and Development Commands
推荐创建虚拟环境后安装依赖：
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
运行完整流程：`python main.py --text "示例文本"` 或 `python main.py --file docs/sample.txt`。回归测试：`pytest -q`。

## Coding Style & Naming Conventions
保持 Pydantic 模型 + Enum 统一定义，引入新结构时请扩展 `domain.py` 并在 `tests/` 下添加断言。Python 代码遵循 PEP 8，使用四空格缩进，函数名/变量名采用 `snake_case`，枚举项使用 `UPPER_CASE`。

## Testing Guidelines
所有新增能力需至少包含单元测试或集成测试。`tests/test_domain.py` 用于枚举和模型验证，`tests/test_workflow.py` 用于端到端流程验证。新增模块时请在 `tests/` 下创建对应测试文件并复用已有样例文本。

## Commit & Pull Request Guidelines
提交信息尽量描述变更意图（例如 `refactor: simplify slide composer`）。PR 需包含：变更摘要、测试说明（例如 `pytest -q`）、如果生成了新的结果文件请附上路径说明。涉及 CLI 或输出格式的调整应同步更新 `AGENTS.md` 与 `docs/QUICK_VALIDATION.md`。

## Configuration & Secrets
当前流程完全离线，不再依赖云端密钥。若后续接入真实模型，请通过环境变量传入，并在文档中明确说明；不要将凭据写入仓库。
