#!/usr/bin/env python3
"""PPT Agent CLI（支持反思优化流程）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.agent import generate_ppt_from_file, generate_ppt_from_text  # noqa: E402
from src.agent.utils import logger  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PPT Agent - 结构化 PPT 生成器")
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--text", help="直接提供输入文本")
    input_group.add_argument("--file", help="文本文件路径")

    parser.add_argument("--model-provider", default="openai", help="模型提供商，例如 openai / google / stub")
    parser.add_argument("--model-name", default="gpt-3.5-turbo", help="具体模型名称")
    parser.add_argument("--use-stub", action="store_true", help="使用内置 stub，跳过真实模型调用")
    parser.add_argument("--name", help="输出文件名前缀 (默认基于标题)")
    parser.add_argument("--verbose", action="store_true", help="显示调试日志")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel("DEBUG")

    provider = args.model_provider
    model_name = args.model_name
    use_stub = args.use_stub or args.model_provider == "stub"

    if args.text:
        state = generate_ppt_from_text(args.text, provider, model_name, use_stub)
    else:
        state = generate_ppt_from_file(args.file, provider, model_name, use_stub)

    if state.errors:
        logger.error("生成失败: %s", "; ".join(state.errors))
        sys.exit(1)

    if args.name and state.html_output:
        from src.agent.utils import result_saver

        result_saver.save_html(state.html_output, args.name)

    print("✅ 生成成功")
    if state.outline:
        print(f"标题: {state.outline.title}")
        print(f"幻灯片数量: {len(state.slides)}")
    if state.consistency_report:
        print(f"一致性得分: {state.consistency_report.overall_score:.1f}")
    if state.output_file_path:
        print(f"输出文件: {state.output_file_path}")


if __name__ == "__main__":
    main()
