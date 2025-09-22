#!/usr/bin/env python3
"""
PPT Agent 工具函数

提供日志、文件处理、质量检查等通用功能
"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path


class Logger:
    """日志管理器"""

    def __init__(self, name: str = "ppt_agent", log_dir: str = "logs"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)

        # 创建日志目录
        os.makedirs(log_dir, exist_ok=True)

        # 设置日志格式
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # 文件处理器
        log_file = os.path.join(log_dir, f"{name}_{datetime.now().strftime('%Y%m%d')}.log")
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        # 添加处理器
        if not self.logger.handlers:
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)

    def info(self, message: str):
        """记录信息"""
        self.logger.info(message)

    def error(self, message: str):
        """记录错误"""
        self.logger.error(message)

    def warning(self, message: str):
        """记录警告"""
        self.logger.warning(message)

    def debug(self, message: str):
        """记录调试信息"""
        self.logger.debug(message)


class FileManager:
    """文件管理器"""

    @staticmethod
    def read_file(file_path: str, encoding: str = 'utf-8') -> str:
        """读取文件内容"""
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except Exception as e:
            raise Exception(f"读取文件失败 {file_path}: {e}")

    @staticmethod
    def write_file(file_path: str, content: str, encoding: str = 'utf-8') -> None:
        """写入文件内容"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, 'w', encoding=encoding) as f:
                f.write(content)
        except Exception as e:
            raise Exception(f"写入文件失败 {file_path}: {e}")

    @staticmethod
    def generate_filename(base_name: str, extension: str = "html", output_dir: str = "results") -> str:
        """生成唯一文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{base_name}_{timestamp}.{extension}"
        return os.path.join(output_dir, filename)

    @staticmethod
    def ensure_directory(directory: str) -> None:
        """确保目录存在"""
        os.makedirs(directory, exist_ok=True)


class QualityChecker:
    """质量检查器"""

    @staticmethod
    def check_content_completeness(content: str, min_length: int = 10) -> float:
        """检查内容完整性"""
        if not content or len(content.strip()) < min_length:
            return 0.0

        # 基于内容长度和结构的简单评分
        score = min(1.0, len(content.strip()) / 100)
        return score

    @staticmethod
    def check_structure_consistency(slides: List[Dict[str, Any]]) -> float:
        """检查结构一致性"""
        if not slides:
            return 0.0

        # 检查标题是否存在
        has_titles = sum(1 for slide in slides if slide.get('title', '').strip())
        title_ratio = has_titles / len(slides)

        # 检查内容是否存在
        has_content = sum(1 for slide in slides if slide.get('content', '').strip())
        content_ratio = has_content / len(slides)

        return (title_ratio + content_ratio) / 2

    @staticmethod
    def calculate_overall_quality(
        completeness: float,
        consistency: float,
        clarity: float = 0.8  # 默认清晰度
    ) -> Dict[str, float]:
        """计算总体质量分数"""
        overall = (completeness + consistency + clarity) / 3
        return {
            'completeness': completeness,
            'consistency': consistency,
            'clarity': clarity,
            'overall': overall
        }


class ContentProcessor:
    """内容处理器"""

    @staticmethod
    def clean_text(text: str) -> str:
        """清理文本内容"""
        # 移除多余的空行
        lines = [line.strip() for line in text.split('\n')]
        cleaned_lines = []

        for line in lines:
            if line or (cleaned_lines and cleaned_lines[-1]):
                cleaned_lines.append(line)

        return '\n'.join(cleaned_lines).strip()

    @staticmethod
    def split_into_chunks(text: str, max_length: int = 500) -> List[str]:
        """将长文本分割为合适的块"""
        if len(text) <= max_length:
            return [text]

        chunks = []
        sentences = text.split('. ')
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk + sentence) <= max_length:
                current_chunk += sentence + ". "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + ". "

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks

    @staticmethod
    def extract_key_points(text: str, max_points: int = 5) -> List[str]:
        """提取关键要点"""
        lines = text.split('\n')
        key_points = []

        for line in lines:
            line = line.strip()
            if line.startswith('- ') or line.startswith('• '):
                key_points.append(line[2:].strip())
            elif line and not line.startswith('#'):
                # 将长句子转换为要点
                if len(line) > 20 and '。' in line:
                    points = line.split('。')
                    for point in points:
                        if point.strip():
                            key_points.append(point.strip())

        return key_points[:max_points]


class ConfigManager:
    """配置管理器"""

    DEFAULT_CONFIG = {
        'output_dir': 'results',
        'log_dir': 'logs',
        'max_slides_per_section': 5,
        'quality_threshold': 0.8,
        'max_retries': 3,
        'template_theme': 'professional'
    }

    @staticmethod
    def load_config(config_file: str = "config.json") -> Dict[str, Any]:
        """加载配置文件"""
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    config = ConfigManager.DEFAULT_CONFIG.copy()
                    config.update(user_config)
                    return config
            except Exception:
                pass
        return ConfigManager.DEFAULT_CONFIG.copy()

    @staticmethod
    def save_config(config: Dict[str, Any], config_file: str = "config.json") -> None:
        """保存配置文件"""
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"保存配置失败: {e}")


# 全局实例
logger = Logger()
file_manager = FileManager()
quality_checker = QualityChecker()
content_processor = ContentProcessor()
config_manager = ConfigManager()