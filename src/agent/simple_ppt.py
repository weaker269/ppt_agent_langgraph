#!/usr/bin/env python3
"""
PPT Agent 核心生成器

集成架构组件的PPT生成工具，保持轻量级同时具备良好的设计
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

# 导入架构组件
from .state import SlideContent, SlideType, ContentType, GenerationResult, QualityMetrics
from .prompts import ContentParser, StyleTemplates
from .util import logger, file_manager, quality_checker, content_processor


class SimplePPTGenerator:
    """架构化的PPT生成器"""

    def __init__(self, theme: str = "professional", quality_threshold: float = 0.8):
        self.theme = theme
        self.quality_threshold = quality_threshold
        self.max_retry = 3
        logger.info("PPT生成器初始化完成")

    def generate_from_file(self, input_file: str, output_dir: str = "results") -> GenerationResult:
        """从文件生成PPT"""
        start_time = datetime.now()

        try:
            logger.info(f"开始生成PPT: {input_file}")

            # 使用file_manager读取文件
            content = file_manager.read_file(input_file)

            # 创建输出目录
            file_manager.ensure_directory(output_dir)

            # 生成输出文件名
            input_name = os.path.splitext(os.path.basename(input_file))[0]
            output_file = file_manager.generate_filename(input_name, "html", output_dir)

            # 解析内容并生成PPT
            slides_data = self._parse_content_to_slides(content)
            slides = self._convert_to_slide_objects(slides_data)

            # 质量检查
            quality_metrics = self._check_quality(slides)

            # 生成HTML
            html_content = self._generate_html(slides_data)

            # 写入文件
            file_manager.write_file(output_file, html_content)

            # 计算生成时间
            generation_time = (datetime.now() - start_time).total_seconds()

            logger.info(f"PPT生成成功: {output_file}")

            return GenerationResult(
                success=True,
                output_file=output_file,
                slides_count=len(slides),
                quality_metrics=quality_metrics,
                generation_time=generation_time
            )

        except Exception as e:
            logger.error(f"PPT生成失败: {e}")
            generation_time = (datetime.now() - start_time).total_seconds()

            return GenerationResult(
                success=False,
                output_file="",
                slides_count=0,
                quality_metrics=QualityMetrics(),
                generation_time=generation_time,
                error_message=str(e)
            )

    def _parse_content_to_slides(self, content: str) -> List[Dict[str, Any]]:
        """将内容解析为幻灯片 - 使用ContentParser"""
        # 使用内容处理器清理文本
        cleaned_content = content_processor.clean_text(content)

        # 使用ContentParser解析结构
        structure = ContentParser.parse_markdown_structure(cleaned_content)

        slides = []

        # 创建标题页
        if structure['main_title']:
            slides.append({
                'title': structure['main_title'],
                'type': 'title',
                'content': ''
            })

        # 创建内容页
        for section in structure['sections']:
            section_content = section['content']

            # 处理长内容，可能需要分页
            if len(section_content) > 800:
                chunks = content_processor.split_into_chunks(section_content, 600)
                for i, chunk in enumerate(chunks):
                    title = section['title']
                    if len(chunks) > 1:
                        title += f" ({i+1}/{len(chunks)})"

                    slides.append({
                        'title': title,
                        'type': 'content',
                        'content': self._format_content(chunk)
                    })
            else:
                slides.append({
                    'title': section['title'],
                    'type': 'content',
                    'content': self._format_content(section_content)
                })

        return slides

    def _format_content(self, content: str) -> str:
        """格式化内容为HTML"""
        lines = content.split('\n')
        formatted_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue

            if line.startswith('**') and line.endswith('**'):
                # 粗体文本作为小标题
                formatted_lines.append(f"<h3>{line[2:-2]}</h3>")
            elif line.startswith('• '):
                # 列表项
                formatted_lines.append(f"<li>{line[2:].strip()}</li>")
            else:
                # 普通文本
                formatted_lines.append(f"<p>{line}</p>")

        return '\n'.join(formatted_lines)

    def _convert_to_slide_objects(self, slides_data: List[Dict[str, Any]]) -> List[SlideContent]:
        """将字典数据转换为SlideContent对象"""
        slides = []
        for i, slide_data in enumerate(slides_data):
            slide = SlideContent(
                slide_id=i + 1,
                title=slide_data['title'],
                slide_type=SlideType.TITLE if slide_data['type'] == 'title' else SlideType.CONTENT,
                content=slide_data['content'],
                content_type=ContentType.LIST if '<li>' in slide_data['content'] else ContentType.TEXT
            )
            slides.append(slide)
        return slides

    def _check_quality(self, slides: List[SlideContent]) -> QualityMetrics:
        """检查幻灯片质量"""
        if not slides:
            return QualityMetrics()

        # 转换为字典格式进行质量检查
        slides_dict = [
            {'title': slide.title, 'content': slide.content}
            for slide in slides
        ]

        completeness = quality_checker.check_content_completeness(
            '\n'.join([slide.content for slide in slides])
        )
        consistency = quality_checker.check_structure_consistency(slides_dict)

        quality_metrics = QualityMetrics(
            completeness_score=completeness,
            consistency_score=consistency,
            clarity_score=0.8  # 默认清晰度
        )
        quality_metrics.calculate_overall_score()

        return quality_metrics

    def _generate_html(self, slides: List[Dict[str, Any]]) -> str:
        """生成HTML内容 - 使用样式模板"""
        # 获取主题样式
        theme_style = StyleTemplates.get_theme(self.theme)

        slides_html = ""

        for i, slide in enumerate(slides):
            slide_class = "slide"
            if i == 0:
                slide_class += " active"
            if slide['type'] == 'title':
                slide_class += " title-slide"

            # 处理内容
            content = slide['content']
            if '<li>' in content:
                # 包含列表项，转换为无序列表
                content = content.replace('<li>', '').replace('</li>', '')
                items = [item.strip() for item in content.split('<p>') if item.strip()]
                items = [item.replace('</p>', '') for item in items if item]
                if items:
                    content = '<ul class="bullet-points">' + ''.join([f'<li>{item}</li>' for item in items]) + '</ul>'

            slides_html += f'''
        <div class="{slide_class}" data-slide="{i+1}">
            <div class="slide-header">
                <h1 class="slide-title">{slide['title']}</h1>
            </div>
            <div class="slide-content">
                {content}
            </div>
        </div>'''

        # 生成完整HTML - 使用主题样式
        html_template = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PPT演示文稿</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Microsoft YaHei', Arial, sans-serif;
            background: {theme_style['background']};
            overflow: hidden;
            height: 100vh;
        }}
        .presentation-container {{
            width: 100%;
            height: 100vh;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
        }}
        .slide {{
            width: 90%;
            max-width: 1000px;
            height: 80%;
            max-height: 600px;
            background: white;
            border-radius: 15px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            padding: 40px;
            display: none;
            flex-direction: column;
            position: relative;
            overflow: hidden;
        }}
        .slide.active {{ display: flex; }}
        .slide.title-slide {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-align: center;
            justify-content: center;
        }}
        .slide-header {{
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 3px solid {theme_style['primary_color']};
            padding-bottom: 20px;
        }}
        .title-slide .slide-header {{ border-bottom: 3px solid white; }}
        .slide-title {{
            font-size: {theme_style['title_size']};
            color: {theme_style['text_color']};
            font-weight: 700;
            margin-bottom: 10px;
        }}
        .title-slide .slide-title {{ color: white; font-size: 3.5em; }}
        .slide-content {{
            flex: 1;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .slide-content p {{
            font-size: {theme_style['content_size']};
            line-height: 1.6;
            color: {theme_style['text_color']};
            margin-bottom: 15px;
        }}
        .slide-content h3 {{
            font-size: 1.4em;
            color: {theme_style['primary_color']};
            margin: 20px 0 10px 0;
        }}
        .bullet-points {{
            list-style: none;
            padding: 0;
        }}
        .bullet-points li {{
            font-size: 1.1em;
            line-height: 1.8;
            color: #555;
            margin-bottom: 15px;
            padding-left: 30px;
            position: relative;
        }}
        .bullet-points li::before {{
            content: '▶';
            color: {theme_style['primary_color']};
            font-size: 1.2em;
            position: absolute;
            left: 0;
            top: 0;
        }}
        .navigation {{
            position: fixed;
            bottom: 30px;
            left: 50%;
            transform: translateX(-50%);
            display: flex;
            gap: 15px;
            z-index: 1000;
        }}
        .nav-btn {{
            background: rgba(255, 255, 255, 0.9);
            border: none;
            border-radius: 50px;
            padding: 15px 25px;
            cursor: pointer;
            font-size: 1em;
            font-weight: 600;
            color: #333;
            transition: all 0.3s ease;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }}
        .nav-btn:hover {{
            background: white;
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
        }}
        .nav-btn:disabled {{
            opacity: 0.5;
            cursor: not-allowed;
        }}
        .slide-counter {{
            position: fixed;
            top: 30px;
            right: 30px;
            background: rgba(255, 255, 255, 0.9);
            padding: 10px 20px;
            border-radius: 25px;
            font-weight: 600;
            color: #333;
            font-size: 1em;
            box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
        }}
        .progress-bar {{
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 4px;
            background: rgba(255, 255, 255, 0.3);
            z-index: 1001;
        }}
        .progress-fill {{
            height: 100%;
            background: {theme_style['primary_color']};
            transition: width 0.3s ease;
            width: 0%;
        }}
    </style>
</head>
<body>
    <div class="progress-bar">
        <div class="progress-fill" id="progressFill"></div>
    </div>
    <div class="slide-counter" id="slideCounter">1 / {len(slides)}</div>
    <div class="presentation-container">
        {slides_html}
    </div>
    <div class="navigation">
        <button class="nav-btn" id="prevBtn" onclick="previousSlide()">上一页</button>
        <button class="nav-btn" id="nextBtn" onclick="nextSlide()">下一页</button>
    </div>
    <script>
        let currentSlide = 1;
        const totalSlides = {len(slides)};
        const slides = document.querySelectorAll('.slide');

        function updateSlideDisplay() {{
            slides.forEach((slide, index) => {{
                slide.classList.remove('active');
                if (index + 1 === currentSlide) {{
                    slide.classList.add('active');
                }}
            }});
            document.getElementById('slideCounter').textContent = `${{currentSlide}} / ${{totalSlides}}`;
            const progress = (currentSlide / totalSlides) * 100;
            document.getElementById('progressFill').style.width = `${{progress}}%`;
            document.getElementById('prevBtn').disabled = currentSlide === 1;
            document.getElementById('nextBtn').disabled = currentSlide === totalSlides;
        }}

        function nextSlide() {{
            if (currentSlide < totalSlides) {{
                currentSlide++;
                updateSlideDisplay();
            }}
        }}

        function previousSlide() {{
            if (currentSlide > 1) {{
                currentSlide--;
                updateSlideDisplay();
            }}
        }}

        document.addEventListener('keydown', (e) => {{
            switch(e.key) {{
                case 'ArrowRight':
                case ' ':
                    e.preventDefault();
                    nextSlide();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    previousSlide();
                    break;
            }}
        }});

        document.addEventListener('DOMContentLoaded', () => {{
            updateSlideDisplay();
        }});
    </script>
</body>
</html>'''

        return html_template


def main():
    """主函数"""
    import sys

    if len(sys.argv) < 2:
        print("🤖 PPT Agent 简化版")
        print("使用方法: python simple_ppt.py input_file.txt")

        # 创建示例文件
        if not os.path.exists("example.txt"):
            with open("example.txt", "w", encoding="utf-8") as f:
                f.write("""# 人工智能发展

## 历史回顾
人工智能发展经历了多个重要阶段：
- 1950年代：图灵测试提出
- 1980年代：专家系统兴起
- 2010年代：深度学习突破

## 当前应用
### 主要领域
- 语音识别
- 图像处理
- 自然语言处理

### 商业应用
人工智能已经在各行各业得到广泛应用。

## 未来趋势
预计人工智能将在更多领域发挥重要作用。
""")
            print("✅ 已创建示例文件: example.txt")
            print("💡 运行: python simple_ppt.py example.txt")

        return

    input_file = sys.argv[1]

    if not os.path.exists(input_file):
        print(f"❌ 文件不存在: {input_file}")
        return

    try:
        generator = SimplePPTGenerator()
        output_file = generator.generate_from_file(input_file)

        print("✅ PPT生成成功!")
        print(f"📄 输出文件: {output_file}")
        print("🌐 在浏览器中打开HTML文件即可查看PPT")

    except Exception as e:
        print(f"❌ 生成失败: {e}")


if __name__ == "__main__":
    main()