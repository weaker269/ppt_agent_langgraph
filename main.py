#!/usr/bin/env python3
"""
PPT智能体主程序

使用示例：
python main.py --text "你的演示内容"
python main.py --file input.txt
python main.py --file input.md --model google
"""

import argparse
import sys
import os
from pathlib import Path

# 添加项目路径到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from src.agent import generate_ppt_from_text, generate_ppt_from_file, logger


def main():
    """主函数"""
    parser = argparse.ArgumentParser(
        description="PPT智能体 - 基于AI的演示文稿生成工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s --text "人工智能的发展历程和未来趋势"
  %(prog)s --file presentation_content.txt
  %(prog)s --file research_paper.md --model google
  %(prog)s --text "新产品发布会" --theme creative
        """
    )

    # 输入选项
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--text",
        type=str,
        help="直接输入要生成PPT的文本内容"
    )
    input_group.add_argument(
        "--file",
        type=str,
        help="输入文件路径（支持txt、md格式）"
    )

    # 模型选项
    parser.add_argument(
        "--model",
        type=str,
        choices=["openai", "google"],
        default="openai",
        help="选择AI模型提供商 (默认: openai)"
    )

    # 样式选项
    parser.add_argument(
        "--theme",
        type=str,
        choices=["professional", "modern", "creative", "academic", "minimal"],
        help="指定样式主题（可选，系统会自动选择）"
    )

    # 输出选项
    parser.add_argument(
        "--output",
        type=str,
        help="输出文件路径（可选）"
    )

    # 调试选项
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细日志"
    )

    # 解析参数
    args = parser.parse_args()

    # 设置日志级别
    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
        logger.info("已启用详细日志模式")

    try:
        # 打印欢迎信息
        print("🎯 PPT智能体 v1.0")
        print("=" * 50)

        # 生成PPT
        if args.text:
            print(f"📝 从文本生成PPT...")
            print(f"🤖 使用模型: {args.model}")
            result = generate_ppt_from_text(args.text, args.model)
        else:
            if not os.path.exists(args.file):
                print(f"❌ 错误: 文件不存在 - {args.file}")
                sys.exit(1)

            print(f"📁 从文件生成PPT: {args.file}")
            print(f"🤖 使用模型: {args.model}")
            result = generate_ppt_from_file(args.file, args.model)

        # 检查生成结果
        if result.errors:
            print("❌ 生成过程中出现错误:")
            for error in result.errors:
                print(f"   • {error}")
            sys.exit(1)

        # 显示结果
        print("\n✅ PPT生成完成!")
        print("=" * 50)

        if result.outline:
            print(f"📊 标题: {result.outline.title}")
            print(f"📄 页数: {len(result.slides)}")
            print(f"🎨 主题: {result.selected_theme.value}")

            if result.outline.estimated_duration:
                print(f"⏱️  预计时长: {result.outline.estimated_duration}分钟")

        if result.output_file_path:
            print(f"💾 文件路径: {result.output_file_path}")

            # 自动打开文件（如果配置了）
            from src.agent.utils import ConfigManager
            config = ConfigManager()
            if config.get("AUTO_OPEN_HTML", "false").lower() == "true":
                try:
                    import webbrowser
                    webbrowser.open(f"file://{os.path.abspath(result.output_file_path)}")
                    print("🌐 已在浏览器中打开PPT")
                except Exception as e:
                    print(f"⚠️  无法自动打开浏览器: {e}")

        # 显示警告（如果有）
        if result.warnings:
            print("\n⚠️  警告信息:")
            for warning in result.warnings:
                print(f"   • {warning}")

        print("\n🎉 生成成功！您可以在浏览器中查看生成的PPT。")

    except KeyboardInterrupt:
        print("\n\n⛔ 用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 程序执行出错: {e}")
        logger.error(f"主程序异常: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()