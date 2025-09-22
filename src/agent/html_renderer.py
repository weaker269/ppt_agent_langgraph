"""
HTML PPT 渲染器模块

负责将生成的PPT数据渲染成HTML格式，包括：
- 模板渲染
- 图表配置处理
- 样式优化
- 输出文件生成
"""

import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime

try:
    from jinja2 import Environment, FileSystemLoader, Template
except ImportError:
    # 如果jinja2不可用，提供简单的模板替换
    Environment = None
    FileSystemLoader = None
    Template = None

from .state import OverallState, SlideContent, ContentType, ChartType
from .util import logger, FileManager, echarts_generator


class HTMLRenderer:
    """HTML PPT渲染器"""

    def __init__(self, template_dir: str = "templates"):
        self.template_dir = Path(template_dir)
        self.template_dir.mkdir(exist_ok=True)

        if Environment and FileSystemLoader:
            self.jinja_env = Environment(
                loader=FileSystemLoader(str(self.template_dir)),
                autoescape=True
            )
        else:
            self.jinja_env = None
            logger.warning("Jinja2不可用，将使用简单模板替换")

    def render_presentation(self, state: OverallState, output_path: str) -> str:
        """渲染完整的PPT演示文稿"""
        logger.info("开始渲染HTML演示文稿")

        try:
            # 准备渲染数据
            render_data = self._prepare_render_data(state)

            # 选择渲染方法
            if self.jinja_env:
                html_content = self._render_with_jinja(render_data)
            else:
                html_content = self._render_with_simple_template(render_data)

            # 确保输出目录存在
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # 写入HTML文件
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # 更新状态
            state.final_html = html_content

            logger.info("HTML演示文稿渲染完成", output_path=output_path)
            return output_path

        except Exception as e:
            logger.error("HTML演示文稿渲染失败", error=e)
            raise

    def _prepare_render_data(self, state: OverallState) -> Dict[str, Any]:
        """准备渲染数据"""
        slides_data = []

        # 处理所有幻灯片
        for slide in state.generated_slides:
            slide_data = {
                "title": slide.title,
                "subtitle": getattr(slide, 'subtitle', ''),
                "content_type": slide.content_type,
                "main_content": slide.main_content,
                "bullet_points": slide.bullet_points,
                "layout": slide.layout,
                "chart_config": self._process_chart_config(slide)
            }
            slides_data.append(slide_data)

        # 准备总体数据
        render_data = {
            "presentation_title": state.outline.get("title", "演示文稿"),
            "slides": slides_data,
            "total_slides": len(slides_data),
            "generation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "overall_quality_score": state.overall_quality_score,
            "content_style": state.global_context.content_style,
            "target_audience": state.global_context.target_audience
        }

        return render_data

    def _process_chart_config(self, slide: SlideContent) -> Optional[Dict[str, Any]]:
        """处理图表配置"""
        if slide.content_type != ContentType.CHART or not slide.chart_config:
            return None

        try:
            # 如果是字符串，尝试解析为JSON
            if isinstance(slide.chart_config, str):
                chart_config = json.loads(slide.chart_config)
            else:
                chart_config = slide.chart_config

            # 确保配置有效
            if not isinstance(chart_config, dict):
                return None

            # 添加默认配置
            if "animation" not in chart_config:
                chart_config["animation"] = {
                    "duration": 1000,
                    "easing": "cubicOut"
                }

            if "responsive" not in chart_config:
                chart_config["responsive"] = True

            return chart_config

        except Exception as e:
            logger.warning("图表配置处理失败", slide_id=slide.slide_id, error=e)
            return None

    def _render_with_jinja(self, render_data: Dict[str, Any]) -> str:
        """使用Jinja2渲染模板"""
        try:
            template = self.jinja_env.get_template("ppt_template.html")
            return template.render(**render_data)
        except Exception as e:
            logger.error("Jinja2模板渲染失败", error=e)
            # 降级到简单模板
            return self._render_with_simple_template(render_data)

    def _render_with_simple_template(self, render_data: Dict[str, Any]) -> str:
        """使用简单字符串替换渲染模板"""
        logger.info("使用简单模板渲染")

        # 读取模板文件
        template_path = self.template_dir / "ppt_template.html"
        if not template_path.exists():
            # 使用内置简单模板
            template_content = self._get_builtin_template()
        else:
            with open(template_path, 'r', encoding='utf-8') as f:
                template_content = f.read()

        # 替换基本变量
        html_content = template_content.replace(
            "{{ presentation_title }}", render_data["presentation_title"]
        ).replace(
            "{{ total_slides }}", str(render_data["total_slides"])
        )

        # 生成幻灯片HTML
        slides_html = ""
        for i, slide in enumerate(render_data["slides"]):
            slide_html = self._generate_slide_html(slide, i + 1)
            slides_html += slide_html

        # 替换幻灯片内容
        html_content = html_content.replace("{% for slide in slides %}", "").replace("{% endfor %}", slides_html)

        # 生成图表配置JavaScript
        chart_configs_js = self._generate_chart_configs_js(render_data["slides"])
        html_content = html_content.replace(
            "const chartConfigs = {", f"const chartConfigs = {{\n{chart_configs_js}"
        )

        return html_content

    def _generate_slide_html(self, slide_data: Dict[str, Any], slide_index: int) -> str:
        """生成单个幻灯片的HTML"""
        active_class = "active" if slide_index == 1 else ""

        # 根据内容类型确定样式
        slide_class = f"slide {active_class}"
        if slide_data["content_type"] == "title":
            slide_style = 'style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white;"'
        else:
            slide_style = ""

        # 构建幻灯片HTML
        slide_html = f'''
        <div class="{slide_class}" data-slide="{slide_index}" {slide_style}>
            <div class="slide-header">
                <h1 class="slide-title">{slide_data["title"]}</h1>
                {f'<div class="slide-subtitle">{slide_data["subtitle"]}</div>' if slide_data.get("subtitle") else ""}
            </div>
            <div class="slide-content {self._get_layout_class(slide_data)}">
                {self._generate_content_html(slide_data, slide_index)}
            </div>
        </div>
        '''

        return slide_html

    def _get_layout_class(self, slide_data: Dict[str, Any]) -> str:
        """获取布局CSS类"""
        layout = slide_data.get("layout", {})
        template = layout.get("template", "")

        if template == "two_column":
            return "two-column"
        return ""

    def _generate_content_html(self, slide_data: Dict[str, Any], slide_index: int) -> str:
        """生成内容HTML"""
        content_type = slide_data["content_type"]
        main_content = slide_data.get("main_content", "")
        bullet_points = slide_data.get("bullet_points", [])

        content_html = ""

        # 主要内容
        if main_content:
            content_html += f'<div class="main-content">{main_content}</div>'

        # 图表
        if content_type == "chart":
            content_html += f'<div class="chart-container" id="chart_{slide_index}"></div>'

        # 要点列表
        if bullet_points:
            points_html = ""
            for point in bullet_points:
                points_html += f"<li>{point}</li>"

            content_html += f'<ul class="bullet-points">{points_html}</ul>'

        return content_html

    def _generate_chart_configs_js(self, slides: List[Dict[str, Any]]) -> str:
        """生成图表配置JavaScript"""
        chart_configs = []

        for i, slide in enumerate(slides):
            if slide.get("chart_config"):
                config_json = json.dumps(slide["chart_config"], ensure_ascii=False, indent=2)
                chart_configs.append(f"            {i + 1}: {config_json}")

        return ",\n".join(chart_configs)

    def _get_builtin_template(self) -> str:
        """获取内置的简单HTML模板"""
        return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ presentation_title }}</title>
    <script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: 'Microsoft YaHei', Arial, sans-serif; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); overflow: hidden; height: 100vh; }
        .presentation-container { width: 100%; height: 100vh; position: relative; display: flex; align-items: center; justify-content: center; }
        .slide { width: 90%; max-width: 1000px; height: 80%; max-height: 600px; background: white; border-radius: 15px; box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1); padding: 40px; display: none; flex-direction: column; position: relative; overflow: hidden; }
        .slide.active { display: flex; }
        .slide-header { text-align: center; margin-bottom: 30px; border-bottom: 3px solid #667eea; padding-bottom: 20px; }
        .slide-title { font-size: 2.5em; color: #333; font-weight: 700; margin-bottom: 10px; }
        .slide-subtitle { font-size: 1.2em; color: #666; font-weight: 300; }
        .slide-content { flex: 1; display: flex; flex-direction: column; justify-content: center; }
        .slide-content.two-column { flex-direction: row; gap: 30px; }
        .slide-content.two-column > div { flex: 1; }
        .main-content { font-size: 1.1em; line-height: 1.6; color: #444; margin-bottom: 20px; }
        .bullet-points { list-style: none; padding: 0; }
        .bullet-points li { font-size: 1.1em; line-height: 1.8; color: #555; margin-bottom: 15px; padding-left: 30px; position: relative; }
        .bullet-points li::before { content: '▶'; color: #667eea; font-size: 1.2em; position: absolute; left: 0; top: 0; }
        .chart-container { width: 100%; height: 400px; margin: 20px 0; }
        .navigation { position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%); display: flex; gap: 15px; z-index: 1000; }
        .nav-btn { background: rgba(255, 255, 255, 0.9); border: none; border-radius: 50px; padding: 15px 25px; cursor: pointer; font-size: 1em; font-weight: 600; color: #333; transition: all 0.3s ease; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1); }
        .nav-btn:hover { background: white; transform: translateY(-2px); box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15); }
        .nav-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .slide-counter { position: fixed; top: 30px; right: 30px; background: rgba(255, 255, 255, 0.9); padding: 10px 20px; border-radius: 25px; font-weight: 600; color: #333; font-size: 1em; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1); }
        .progress-bar { position: fixed; top: 0; left: 0; width: 100%; height: 4px; background: rgba(255, 255, 255, 0.3); z-index: 1001; }
        .progress-fill { height: 100%; background: #667eea; transition: width 0.3s ease; width: 0%; }
    </style>
</head>
<body>
    <div class="progress-bar"><div class="progress-fill" id="progressFill"></div></div>
    <div class="slide-counter" id="slideCounter">1 / {{ total_slides }}</div>
    <div class="presentation-container">
        {% for slide in slides %}{% endfor %}
    </div>
    <div class="navigation">
        <button class="nav-btn" id="prevBtn" onclick="previousSlide()">上一页</button>
        <button class="nav-btn" id="nextBtn" onclick="nextSlide()">下一页</button>
    </div>
    <script>
        let currentSlide = 1;
        const totalSlides = {{ total_slides }};
        const slides = document.querySelectorAll('.slide');

        const chartConfigs = {
        };

        function initializeCharts() {
            Object.keys(chartConfigs).forEach(slideIndex => {
                const chartContainer = document.getElementById(`chart_${slideIndex}`);
                if (chartContainer) {
                    const chart = echarts.init(chartContainer);
                    chart.setOption(chartConfigs[slideIndex]);
                    window.addEventListener('resize', () => { chart.resize(); });
                }
            });
        }

        function updateSlideDisplay() {
            slides.forEach((slide, index) => {
                slide.classList.remove('active');
                if (index + 1 === currentSlide) {
                    slide.classList.add('active');
                }
            });
            document.getElementById('slideCounter').textContent = `${currentSlide} / ${totalSlides}`;
            const progress = (currentSlide / totalSlides) * 100;
            document.getElementById('progressFill').style.width = `${progress}%`;
            document.getElementById('prevBtn').disabled = currentSlide === 1;
            document.getElementById('nextBtn').disabled = currentSlide === totalSlides;
        }

        function nextSlide() {
            if (currentSlide < totalSlides) {
                currentSlide++;
                updateSlideDisplay();
            }
        }

        function previousSlide() {
            if (currentSlide > 1) {
                currentSlide--;
                updateSlideDisplay();
            }
        }

        document.addEventListener('keydown', (e) => {
            switch(e.key) {
                case 'ArrowRight':
                case ' ':
                    e.preventDefault();
                    nextSlide();
                    break;
                case 'ArrowLeft':
                    e.preventDefault();
                    previousSlide();
                    break;
            }
        });

        document.addEventListener('DOMContentLoaded', () => {
            updateSlideDisplay();
            initializeCharts();
        });
    </script>
</body>
</html>'''


# 创建全局渲染器实例
html_renderer = HTMLRenderer()