# 常用命令
- 创建虚拟环境：`python -m venv .venv`；启用：`source .venv/bin/activate`（Windows PowerShell 可用 `.\.venv\Scripts\Activate.ps1`）。
- 安装依赖：`pip install -r requirements.txt`。
- 运行 CLI：`python main.py --text "示例主题" --model-provider stub --use-stub` 或 `python main.py --file docs/sample.txt --model-provider openai --model-name gpt-4o`。
- 运行流程验证：`pytest -q`。
- 查看样例输入：`example_input.txt`；快速校验参考：`docs/QUICK_VALIDATION.md`。