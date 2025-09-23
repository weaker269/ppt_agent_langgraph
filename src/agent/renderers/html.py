"""
HTML渲染器模块

负责将生成的PPT内容转换为基于reveal.js的HTML演示文稿。
实现了灵活的模板系统和样式自定义功能。
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from jinja2 import Environment, FileSystemLoader, Template

from ..state import OverallState, SlideContent, SlideType, SlideLayout
from ..generators.style import StyleSelector
from ..utils import logger, performance_monitor, FileHandler


class HTMLRenderer:
    """HTML渲染器类"""

    def __init__(self, templates_dir: Optional[str] = None):
        """
        初始化HTML渲染器

        Args:
            templates_dir: 模板目录路径
        """
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"

        self.templates_dir = Path(templates_dir)
        self.templates_dir.mkdir(exist_ok=True)

        # 初始化Jinja2环境
        self.jinja_env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=True
        )

        # 样式选择器（用于生成CSS）
        self.style_selector = StyleSelector()

        # 确保模板文件存在
        self._ensure_templates_exist()

    def render_presentation(self, state: OverallState) -> OverallState:
        """
        渲染完整的演示文稿

        Args:
            state: 当前状态

        Returns:
            更新后的状态（包含HTML输出）
        """
        logger.info("开始渲染HTML演示文稿")
        performance_monitor.start_timer("html_rendering")

        try:
            # 准备渲染数据
            render_data = self._prepare_render_data(state)

            # 生成样式CSS
            custom_css = self._generate_custom_css(state)

            # 渲染主模板
            html_content = self._render_main_template(render_data, custom_css)

            # 更新状态
            state.html_output = html_content

            duration = performance_monitor.end_timer("html_rendering")
            logger.info(f"HTML渲染完成，耗时: {duration:.2f}s")

            return state

        except Exception as e:
            logger.error(f"HTML渲染失败: {e}")
            state.errors.append(f"HTML渲染失败: {str(e)}")
            performance_monitor.end_timer("html_rendering")
            return state

    def _prepare_render_data(self, state: OverallState) -> Dict[str, Any]:
        """准备渲染数据"""
        if not state.outline:
            raise ValueError("缺少演示大纲")

        # 基础信息
        render_data = {
            "title": state.outline.title,
            "subtitle": state.outline.subtitle,
            "author": "PPT智能体",
            "date": "",
            "total_slides": len(state.slides),
            "estimated_duration": state.outline.estimated_duration,
            "theme": state.selected_theme.value,
            "slides": []
        }

        # 处理每个幻灯片
        for slide in state.slides:
            slide_data = self._process_slide_for_rendering(slide)
            render_data["slides"].append(slide_data)

        logger.debug(f"准备渲染数据完成，共{len(render_data['slides'])}页")
        return render_data

    def _process_slide_for_rendering(self, slide: SlideContent) -> Dict[str, Any]:
        """处理单个幻灯片的渲染数据"""
        slide_data = {
            "id": slide.slide_id,
            "type": slide.slide_type.value,
            "layout": slide.layout.value,
            "title": slide.title,
            "content": slide.content,
            "bullet_points": slide.bullet_points,
            "images": slide.images,
            "notes": slide.notes,
            "keywords": slide.keywords,
            "duration": slide.estimated_duration,
            "html_class": self._get_slide_css_class(slide),
            "processed_content": self._process_slide_content(slide)
        }

        return slide_data

    def _get_slide_css_class(self, slide: SlideContent) -> str:
        """获取幻灯片CSS类名"""
        classes = [f"slide-{slide.slide_type.value}", f"layout-{slide.layout.value}"]

        # 根据内容添加特殊类
        if len(slide.bullet_points) > 5:
            classes.append("content-heavy")
        if slide.images:
            classes.append("has-images")
        if slide.slide_type == SlideType.TITLE:
            classes.append("title-slide")

        return " ".join(classes)

    def _process_slide_content(self, slide: SlideContent) -> Dict[str, Any]:
        """处理幻灯片内容，生成结构化的HTML数据"""
        processed = {
            "main_content": [],
            "sidebar_content": [],
            "footer_content": [],
            "has_two_columns": slide.layout in [SlideLayout.TWO_COLUMN, SlideLayout.IMAGE_TEXT],
            "has_images": bool(slide.images),
            "bullet_style": "modern" if len(slide.bullet_points) <= 3 else "compact"
        }

        # 处理主要内容
        if slide.layout == SlideLayout.TWO_COLUMN:
            # 双列布局：内容分为两列
            mid_point = len(slide.content) // 2
            processed["main_content"] = slide.content[:mid_point] if mid_point > 0 else slide.content
            processed["sidebar_content"] = slide.content[mid_point:] if mid_point > 0 else []
        elif slide.layout == SlideLayout.IMAGE_TEXT:
            # 图文布局：内容在一侧，图片在另一侧
            processed["main_content"] = slide.content
            processed["sidebar_content"] = slide.images
        else:
            # 单列布局
            processed["main_content"] = slide.content

        return processed

    def _generate_custom_css(self, state: OverallState) -> str:
        """生成自定义CSS"""
        try:
            # 使用样式选择器生成基础CSS
            base_css = self.style_selector.get_style_css(state)

            # 添加reveal.js特定的样式
            reveal_css = self._get_reveal_specific_css(state)

            # 添加布局特定的样式
            layout_css = self._get_layout_specific_css()

            # 添加动画样式
            animation_css = self._get_animation_css()

            return f"{base_css}\n\n{reveal_css}\n\n{layout_css}\n\n{animation_css}"

        except Exception as e:
            logger.error(f"CSS生成失败: {e}")
            return self._get_fallback_css()

    def _get_reveal_specific_css(self, state: OverallState) -> str:
        """获取reveal.js特定的CSS"""
        theme = state.selected_theme.value
        styles = state.custom_styles

        return f"""
        /* Reveal.js特定样式 */
        .reveal .slides {{
            text-align: left;
        }}

        .reveal .slides section.title-slide {{
            text-align: center;
        }}

        .reveal .slides section.title-slide h1 {{
            font-size: 3em;
            margin-bottom: 0.5em;
        }}

        .reveal .slides section.title-slide .subtitle {{
            font-size: 1.5em;
            color: var(--secondary-color);
            margin-bottom: 1em;
        }}

        .reveal .slides section.slide-section {{
            background: linear-gradient(135deg, var(--primary-color), var(--secondary-color));
            color: white;
        }}

        .reveal .slides section.slide-section h2 {{
            color: white;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}

        .reveal .progress {{
            height: 4px;
        }}

        .reveal .controls {{
            bottom: 20px;
            right: 20px;
        }}

        /* 幻灯片编号 */
        .reveal .slide-number {{
            position: fixed;
            display: block;
            right: 15px;
            bottom: 15px;
            font-size: 14px;
            background-color: rgba(0,0,0,0.1);
            padding: 5px 10px;
            border-radius: 3px;
        }}
        """

    def _get_layout_specific_css(self) -> str:
        """获取布局特定的CSS"""
        return """
        /* 布局特定样式 */
        .layout-two_column .slide-content {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 2em;
            align-items: start;
        }

        .layout-three_column .slide-content {
            display: grid;
            grid-template-columns: 1fr 1fr 1fr;
            gap: 1.5em;
            align-items: start;
        }

        .layout-image_text .slide-content {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 2em;
            align-items: center;
        }

        .layout-title_content .slide-content {
            display: flex;
            flex-direction: column;
            gap: 1.5em;
        }

        .layout-list_layout .bullet-points {
            display: grid;
            gap: 1em;
        }

        .layout-list_layout .bullet-points.compact {
            gap: 0.5em;
        }

        /* 要点样式 */
        .bullet-points {
            list-style: none;
            padding: 0;
        }

        .bullet-points li {
            padding: 0.5em 0;
            padding-left: 1.5em;
            position: relative;
        }

        .bullet-points li::before {
            content: "▶";
            color: var(--accent-color);
            position: absolute;
            left: 0;
            top: 0.5em;
        }

        .bullet-points.modern li::before {
            content: "●";
            font-size: 1.2em;
        }

        /* 图片样式 */
        .slide-images {
            display: flex;
            flex-wrap: wrap;
            gap: 1em;
            justify-content: center;
        }

        .slide-images .image-placeholder {
            background: linear-gradient(45deg, #f0f0f0, #e0e0e0);
            border: 2px dashed var(--secondary-color);
            border-radius: var(--border-radius);
            padding: 2em;
            text-align: center;
            color: var(--secondary-color);
            min-height: 200px;
            display: flex;
            align-items: center;
            justify-content: center;
            flex: 1;
            min-width: 250px;
        }

        /* 内容重度页面 */
        .content-heavy {
            font-size: 0.9em;
        }

        .content-heavy .bullet-points {
            gap: 0.3em;
        }

        .content-heavy h2 {
            font-size: 1.8em;
        }
        """

    def _get_animation_css(self) -> str:
        """获取动画CSS"""
        return """
        /* 动画样式 */
        .reveal .slides section {
            transition: all 0.3s ease;
        }

        .reveal .slides section.present {
            opacity: 1;
            transform: scale(1);
        }

        .reveal .slides section.past {
            opacity: 0.3;
            transform: scale(0.95);
        }

        .reveal .slides section.future {
            opacity: 0.3;
            transform: scale(0.95);
        }

        /* 元素进入动画 */
        .fade-in {
            animation: fadeIn 0.6s ease-in-out;
        }

        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(20px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .slide-in-left {
            animation: slideInLeft 0.6s ease-out;
        }

        @keyframes slideInLeft {
            from {
                opacity: 0;
                transform: translateX(-50px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }

        .slide-in-right {
            animation: slideInRight 0.6s ease-out;
        }

        @keyframes slideInRight {
            from {
                opacity: 0;
                transform: translateX(50px);
            }
            to {
                opacity: 1;
                transform: translateX(0);
            }
        }

        /* 高亮效果 */
        .highlight {
            animation: highlight 2s ease-in-out infinite alternate;
        }

        @keyframes highlight {
            from {
                background-color: var(--accent-color);
            }
            to {
                background-color: transparent;
            }
        }
        """

    def _get_fallback_css(self) -> str:
        """获取备用CSS"""
        return """
        /* 备用样式 */
        :root {
            --primary-color: #2C3E50;
            --secondary-color: #3498DB;
            --accent-color: #E74C3C;
            --background-color: #FFFFFF;
            --text-color: #2C3E50;
        }

        body {
            font-family: Arial, sans-serif;
            color: var(--text-color);
            background-color: var(--background-color);
        }

        .reveal h1, .reveal h2, .reveal h3 {
            color: var(--primary-color);
        }
        """

    def _render_main_template(self, render_data: Dict[str, Any], custom_css: str) -> str:
        """渲染主模板"""
        try:
            # 加载主模板
            template = self.jinja_env.get_template("main.html")

            # 合并渲染数据
            template_data = {
                **render_data,
                "custom_css": custom_css,
                "reveal_config": self._get_reveal_config(),
                "meta_description": f"{render_data['title']} - 由PPT智能体生成",
                "generator": "PPT智能体 v1.0"
            }

            # 渲染模板
            html_content = template.render(**template_data)

            return html_content

        except Exception as e:
            logger.error(f"模板渲染失败: {e}")
            return self._generate_fallback_html(render_data)

    def _get_reveal_config(self) -> Dict[str, Any]:
        """获取reveal.js配置"""
        return {
            "hash": True,
            "controls": True,
            "progress": True,
            "center": True,
            "touch": True,
            "loop": False,
            "rtl": False,
            "navigationMode": "default",
            "shuffle": False,
            "fragments": True,
            "fragmentInURL": True,
            "embedded": False,
            "help": True,
            "pause": True,
            "showNotes": False,
            "autoPlayMedia": None,
            "preloadIframes": None,
            "autoAnimate": True,
            "autoAnimateMatcher": None,
            "autoAnimateEasing": "ease",
            "autoAnimateDuration": 1.0,
            "autoAnimateUnmatched": True,
            "autoSlide": 0,
            "autoSlideStoppable": True,
            "autoSlideMethod": "Reveal.navigateNext",
            "defaultTiming": None,
            "mouseWheel": False,
            "previewLinks": False,
            "postMessage": True,
            "postMessageEvents": False,
            "focusBodyOnPageVisibilityChange": True,
            "transition": "slide",
            "transitionSpeed": "default",
            "backgroundTransition": "fade",
            "viewDistance": 3,
            "mobileViewDistance": 2,
            "parallaxBackgroundImage": "",
            "parallaxBackgroundSize": "",
            "parallaxBackgroundRepeat": "",
            "parallaxBackgroundPosition": "",
            "parallaxBackgroundHorizontal": None,
            "parallaxBackgroundVertical": None,
            "display": "block",
            "hideInactiveCursor": True,
            "hideCursorTime": 5000
        }

    def _generate_fallback_html(self, render_data: Dict[str, Any]) -> str:
        """生成备用HTML"""
        logger.warning("使用备用HTML模板")

        slides_html = ""
        for slide in render_data.get("slides", []):
            slide_html = f"""
            <section>
                <h2>{slide.get('title', '未命名幻灯片')}</h2>
                {''.join([f'<p>{content}</p>' for content in slide.get('content', [])])}
                {'<ul>' + ''.join([f'<li>{point}</li>' for point in slide.get('bullet_points', [])]) + '</ul>' if slide.get('bullet_points') else ''}
            </section>
            """
            slides_html += slide_html

        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>{render_data.get('title', 'PPT演示')}</title>
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.3.1/dist/reveal.css">
            <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.3.1/dist/theme/white.css">
        </head>
        <body>
            <div class="reveal">
                <div class="slides">
                    {slides_html}
                </div>
            </div>
            <script src="https://cdn.jsdelivr.net/npm/reveal.js@4.3.1/dist/reveal.js"></script>
            <script>
                Reveal.initialize();
            </script>
        </body>
        </html>
        """

    def _ensure_templates_exist(self):
        """确保模板文件存在"""
        main_template_path = self.templates_dir / "main.html"

        if not main_template_path.exists():
            logger.info("创建主模板文件")
            self._create_main_template()

    def _create_main_template(self):
        """创建主模板文件"""
        template_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }}{% if subtitle %} - {{ subtitle }}{% endif %}</title>
    <meta name="description" content="{{ meta_description }}">
    <meta name="generator" content="{{ generator }}">

    <!-- Reveal.js CSS -->
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.3.1/dist/reveal.css">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/reveal.js@4.3.1/dist/theme/white.css">

    <!-- 自定义样式 -->
    <style>
        {{ custom_css | safe }}
    </style>
</head>
<body>
    <div class="reveal">
        <div class="slides">
            {% for slide in slides %}
            <section class="{{ slide.html_class }}" data-slide-id="{{ slide.id }}">
                {% if slide.type == 'title' %}
                    <!-- 标题页 -->
                    <h1>{{ slide.title }}</h1>
                    {% if subtitle %}
                    <p class="subtitle">{{ subtitle }}</p>
                    {% endif %}
                    <p class="author">{{ author }}</p>
                    {% if date %}
                    <p class="date">{{ date }}</p>
                    {% endif %}
                {% elif slide.type == 'section' %}
                    <!-- 章节页 -->
                    <h2>{{ slide.title }}</h2>
                {% else %}
                    <!-- 内容页 -->
                    <h2>{{ slide.title }}</h2>

                    <div class="slide-content">
                        {% if slide.processed_content.has_two_columns %}
                        <div class="main-column fade-in">
                            {% for content in slide.processed_content.main_content %}
                            <p>{{ content }}</p>
                            {% endfor %}
                        </div>
                        <div class="sidebar-column slide-in-right">
                            {% if slide.processed_content.has_images %}
                                <div class="slide-images">
                                    {% for image in slide.processed_content.sidebar_content %}
                                    <div class="image-placeholder">
                                        <p>{{ image }}</p>
                                    </div>
                                    {% endfor %}
                                </div>
                            {% else %}
                                {% for content in slide.processed_content.sidebar_content %}
                                <p>{{ content }}</p>
                                {% endfor %}
                            {% endif %}
                        </div>
                        {% else %}
                        <div class="single-column fade-in">
                            {% for content in slide.processed_content.main_content %}
                            <p>{{ content }}</p>
                            {% endfor %}
                        </div>
                        {% endif %}

                        {% if slide.bullet_points %}
                        <ul class="bullet-points {{ slide.processed_content.bullet_style }} slide-in-left">
                            {% for point in slide.bullet_points %}
                            <li>{{ point }}</li>
                            {% endfor %}
                        </ul>
                        {% endif %}

                        {% if slide.images and not slide.processed_content.has_two_columns %}
                        <div class="slide-images fade-in">
                            {% for image in slide.images %}
                            <div class="image-placeholder">
                                <p>{{ image }}</p>
                            </div>
                            {% endfor %}
                        </div>
                        {% endif %}
                    </div>
                {% endif %}

                <!-- 演讲者备注 -->
                {% if slide.notes %}
                <aside class="notes">
                    {{ slide.notes }}
                </aside>
                {% endif %}
            </section>
            {% endfor %}
        </div>
    </div>

    <!-- Reveal.js JavaScript -->
    <script src="https://cdn.jsdelivr.net/npm/reveal.js@4.3.1/dist/reveal.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/reveal.js@4.3.1/plugin/notes/notes.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/reveal.js@4.3.1/plugin/markdown/markdown.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/reveal.js@4.3.1/plugin/highlight/highlight.js"></script>

    <script>
        // 初始化Reveal.js
        Reveal.initialize({{ reveal_config | tojson | safe }});

        // 添加幻灯片编号
        Reveal.configure({
            slideNumber: 'c/t'
        });

        // 自定义事件处理
        Reveal.on('slidechanged', function(event) {
            console.log('切换到幻灯片:', event.indexh + 1);
        });
    </script>
</body>
</html>"""

        FileHandler.write_text_file(
            self.templates_dir / "main.html",
            template_content
        )