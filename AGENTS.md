# Repository Guidelines

## 项目结构与模块组织
main.py 负责 CLI 启动并调用 src/agent/graph.py 内的 PPTAgentGraph；src/agent 依角色分成 generators、renderers、evaluators、validators，domain.py 汇集模型定义，state.py 维护运行状态；tests、logs、results、prompts、docs 与 example_input.txt 分别承载测试、日志、成果、提示模板与样例资料。

## 构建、测试与开发命令
环境准备顺序：python3 -m venv .venv → source .venv/bin/activate → pip install -r requirements.txt。常用命令：python main.py --text "示例主题" --model-provider stub --use-stub 进行快速试跑；python main.py --file docs/sample.txt 处理批量文本；pytest -q 或 pytest tests/test_workflow.py -k consistency 校验主流程；pytest -k retry 观察重试策略。

## 代码风格与命名约定
遵循 PEP 8 与四空格缩进，函数及变量采用 snake_case，枚举常量使用 UPPER_CASE。全部 Pydantic 模型集中在 domain.py，公共逻辑置于 utils.py；调整提示语时同步维护 prompts 目录与生成器注释，提交前执行 ruff check 及 pytest 维持一致性。

## 测试规范
测试框架为 pytest，文件命名遵循 test_*.py：tests/test_domain.py 覆盖模型，tests/test_workflow.py 验证端到端流程，tests/test_renderer.py 检查渲染，tests/test_style.py 确认样式策略。新增能力至少具备正向与边界用例，并断言质量得分、重试次数及反馈文本。

## 提交与合并请求规范
推荐使用动词前缀提交，如 feat: extend outline quality gates 或 fix: protect html theme assets。PR 描述应写明变更背景、核心改动、pytest -q 结果及必要的截图或结果路径（results/2024-xx-xx/*.html），若调整 CLI 参数、输出结构或公共模型，请同步更新 README.md 与 docs/QUICK_VALIDATION.md 并提示兼容性风险。

## 配置与安全提示
默认运行离线；接入真实模型时仅通过环境变量或 .env 注入 GOOGLE_API_KEY、OPENAI_API_KEY，禁止写入仓库。日志位于 logs 目录，分享前应脱敏；部署生产环境时配置 rate limit、timeout 与 alert，并在 prompts 中记录提示变更便于回溯。
