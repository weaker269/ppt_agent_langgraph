"""
PPT智能体工具函数和日志处理模块

包含文件操作、文本处理、日志记录等各种工具函数。
"""

import os
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from datetime import datetime
import hashlib
import re


class Logger:
    """日志处理类"""

    def __init__(self, name: str = "ppt_agent", log_dir: str = "logs"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(exist_ok=True)

        # 创建logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)

        # 避免重复添加handler
        if not self.logger.handlers:
            self._setup_handlers()

    def _setup_handlers(self):
        """设置日志处理器"""
        # 创建formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        )

        # 文件处理器 - 详细日志
        log_file = self.log_dir / f"{self.name}_{datetime.now().strftime('%Y%m%d')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        # 错误日志文件处理器
        error_log_file = self.log_dir / f"{self.name}_error_{datetime.now().strftime('%Y%m%d')}.log"
        error_handler = logging.FileHandler(error_log_file, encoding='utf-8')
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(formatter)

        # 控制台处理器 - 简化日志
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)

        # 添加处理器
        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_handler)
        self.logger.addHandler(console_handler)

    def debug(self, message: str, **kwargs):
        """调试级别日志"""
        self.logger.debug(message, extra=kwargs)

    def info(self, message: str, **kwargs):
        """信息级别日志"""
        self.logger.info(message, extra=kwargs)

    def warning(self, message: str, **kwargs):
        """警告级别日志"""
        self.logger.warning(message, extra=kwargs)

    def error(self, message: str, **kwargs):
        """错误级别日志"""
        self.logger.error(message, extra=kwargs)

    def critical(self, message: str, **kwargs):
        """严重错误级别日志"""
        self.logger.critical(message, extra=kwargs)

    def log_generation_step(self, step: str, slide_id: int, duration: float, success: bool):
        """记录生成步骤"""
        status = "成功" if success else "失败"
        self.info(f"生成步骤: {step} | 幻灯片ID: {slide_id} | 耗时: {duration:.2f}s | 状态: {status}")

    def log_quality_check(self, slide_id: int, score: float, issues: List[str]):
        """记录质量检查结果"""
        self.info(f"质量检查 | 幻灯片ID: {slide_id} | 评分: {score:.2f} | 问题数: {len(issues)}")
        if issues:
            for issue in issues:
                self.warning(f"质量问题 | 幻灯片ID: {slide_id} | {issue}")


class FileHandler:
    """文件处理工具类"""

    @staticmethod
    def read_text_file(file_path: Union[str, Path]) -> str:
        """读取文本文件"""
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        # 尝试不同编码
        encodings = ['utf-8', 'gbk', 'gb2312', 'utf-16']

        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    content = f.read()
                Logger().info(f"成功读取文件: {file_path} (编码: {encoding})")
                return content
            except UnicodeDecodeError:
                continue

        raise ValueError(f"无法解码文件: {file_path}")

    @staticmethod
    def write_text_file(file_path: Union[str, Path], content: str, encoding: str = 'utf-8'):
        """写入文本文件"""
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding=encoding) as f:
            f.write(content)

        Logger().info(f"成功写入文件: {file_path}")

    @staticmethod
    def save_json(file_path: Union[str, Path], data: Dict[str, Any], ensure_ascii: bool = False):
        """保存JSON文件"""
        file_path = Path(file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=2)

        Logger().info(f"成功保存JSON文件: {file_path}")

    @staticmethod
    def load_json(file_path: Union[str, Path]) -> Dict[str, Any]:
        """加载JSON文件"""
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"JSON文件不存在: {file_path}")

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        Logger().info(f"成功加载JSON文件: {file_path}")
        return data


class TextProcessor:
    """文本处理工具类"""

    @staticmethod
    def clean_text(text: str) -> str:
        """清理文本"""
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text.strip())

        # 移除特殊字符（保留中文、英文、数字、常用标点）
        text = re.sub(r'[^\u4e00-\u9fff\w\s.,;:!?()[]{}""''""——、。，；：！？（）【】{}]', '', text)

        return text

    @staticmethod
    def extract_keywords(text: str, max_keywords: int = 10) -> List[str]:
        """提取关键词（简单版本）"""
        # 移除停用词（简化版本）
        stop_words = {
            '的', '了', '是', '在', '有', '和', '与', '及', '或', '但',
            '这', '那', '些', '个', '中', '上', '下', '之', '于', '到',
            'the', 'is', 'at', 'of', 'on', 'a', 'an', 'and', 'or', 'but'
        }

        # 简单分词（按空格和标点分割）
        words = re.findall(r'\b\w+\b', text.lower())

        # 过滤停用词和短词
        keywords = [word for word in words if len(word) > 2 and word not in stop_words]

        # 统计词频
        word_freq = {}
        for word in keywords:
            word_freq[word] = word_freq.get(word, 0) + 1

        # 按频率排序
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)

        return [word for word, freq in sorted_words[:max_keywords]]

    @staticmethod
    def split_into_paragraphs(text: str, max_length: int = 200) -> List[str]:
        """将文本分割为段落"""
        # 按换行符分割
        paragraphs = text.split('\n')

        result = []
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # 如果段落太长，进一步分割
            if len(para) > max_length:
                sentences = re.split(r'[.!?。！？]', para)
                current_para = ""

                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue

                    if len(current_para + sentence) > max_length and current_para:
                        result.append(current_para.strip())
                        current_para = sentence
                    else:
                        current_para += sentence + "。"

                if current_para:
                    result.append(current_para.strip())
            else:
                result.append(para)

        return result


class HashGenerator:
    """哈希生成器"""

    @staticmethod
    def generate_content_hash(content: str) -> str:
        """生成内容哈希值"""
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    @staticmethod
    def generate_slide_id(slide_content: Dict[str, Any]) -> str:
        """生成幻灯片唯一ID"""
        content_str = json.dumps(slide_content, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content_str.encode('utf-8')).hexdigest()[:16]


class PerformanceMonitor:
    """性能监控工具"""

    def __init__(self):
        self.start_times = {}
        self.logger = Logger()

    def start_timer(self, operation: str):
        """开始计时"""
        self.start_times[operation] = time.time()
        self.logger.debug(f"开始计时: {operation}")

    def end_timer(self, operation: str) -> float:
        """结束计时并返回耗时"""
        if operation not in self.start_times:
            self.logger.warning(f"未找到计时器: {operation}")
            return 0.0

        duration = time.time() - self.start_times[operation]
        del self.start_times[operation]

        self.logger.debug(f"操作完成: {operation} | 耗时: {duration:.2f}s")
        return duration


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str = ".env"):
        self.config_path = Path(config_path)
        self.config = {}
        self.load_config()

    def load_config(self):
        """加载配置"""
        if self.config_path.exists():
            with open(self.config_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        self.config[key.strip()] = value.strip()

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        """设置配置值"""
        self.config[key] = str(value)

    def save_config(self):
        """保存配置到文件"""
        with open(self.config_path, 'w', encoding='utf-8') as f:
            for key, value in self.config.items():
                f.write(f"{key}={value}\n")


class ResultSaver:
    """结果保存器"""

    def __init__(self, results_dir: str = "results"):
        self.results_dir = Path(results_dir)
        self.results_dir.mkdir(exist_ok=True)
        self.logger = Logger()

    def save_presentation(self, presentation_data: Dict[str, Any], filename: str = None) -> Path:
        """保存演示文稿数据"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"presentation_{timestamp}.json"

        file_path = self.results_dir / filename
        FileHandler.save_json(file_path, presentation_data)

        self.logger.info(f"演示文稿已保存: {file_path}")
        return file_path

    def save_html_output(self, html_content: str, filename: str = None) -> Path:
        """保存HTML输出"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"presentation_{timestamp}.html"

        file_path = self.results_dir / filename
        FileHandler.write_text_file(file_path, html_content)

        self.logger.info(f"HTML文件已保存: {file_path}")
        return file_path

    def save_generation_log(self, log_data: Dict[str, Any], filename: str = None) -> Path:
        """保存生成日志"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"generation_log_{timestamp}.json"

        file_path = self.results_dir / filename
        FileHandler.save_json(file_path, log_data)

        return file_path


# 全局工具实例
logger = Logger()
file_handler = FileHandler()
text_processor = TextProcessor()
hash_generator = HashGenerator()
performance_monitor = PerformanceMonitor()
result_saver = ResultSaver()


def get_project_root() -> Path:
    """获取项目根目录"""
    return Path(__file__).parent.parent.parent


def ensure_directory(dir_path: Union[str, Path]):
    """确保目录存在"""
    Path(dir_path).mkdir(parents=True, exist_ok=True)


def format_duration(seconds: float) -> str:
    """格式化时长显示"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}分钟"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}小时"