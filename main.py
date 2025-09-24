#!/usr/bin/env python3
"""PPT Agent 轻量 CLI。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.agent import generate_ppt_from_file, generate_ppt_from_text  # noqa: E402
from src.agent.utils import logger  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="PPT Agent - 本地快速验证演示文稿工作流",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--text", help="直接提供输入文本")
    group.add_argument("--file", help="文本文件路径")
    parser.add_argument("--name", help="输出文件前缀 (默认基于标题)")
    parser.add_argument("--verbose", action="store_true", help="显示更多调试日志")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel("DEBUG")

    if args.text:
        state = generate_ppt_from_text(args.text)
    else:
        state = generate_ppt_from_file(args.file)

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
    if state.output_file_path:
        print(f"输出文件: {state.output_file_path}")


if __name__ == "__main__":
    main()
