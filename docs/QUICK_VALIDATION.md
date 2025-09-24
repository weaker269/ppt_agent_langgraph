# 快速验证指南

## 运行
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py --text "人工智能发布计划"
```
默认会在 `results/` 目录写入 HTML 及元数据 JSON，命名源自标题。

## 输入建议
- 尽量提供 3 个以上段落，段落之间空行分隔。
- 每段描述一个子主题，生成的大纲会按段落聚合。
- 若使用文件输入，推荐 UTF-8 编码的 `.txt` 或 `.md`。

## 流程概览
1. `OutlineGenerator` 将文本拆分为章节并提炼要点。
2. `SlideComposer` 根据章节生成标题页、章节页、内容页与总结页。
3. `StyleSelector` 根据标题与关键字挑选基础主题色。
4. `HTMLRenderer` 使用内置模板渲染，直接在浏览器预览。

## 验证方式
- 终端查看概要：CLI 会输出标题、幻灯片数量。
- 浏览器打开 `results/*.html` 检查排版、内容。
- `pytest -q` 确认模型与流程回归测试全部通过。

## 扩展入口
- 修改 `src/agent/domain.py` 可扩展更多幻灯片结构。
- 在 `src/agent/renderers/` 添加新的模板或导出格式。
- 若需接入真实模型，可在 `generators/outline.py` 的 `OutlineGenerator` 内引入新的 `generate_outline` 实现。
