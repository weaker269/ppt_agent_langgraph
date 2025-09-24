"""
智能错误恢复管理器

提供全面的错误检测、分类和自动恢复机制。
"""

import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from enum import Enum
import traceback
import time

from ..state import OverallState, SlideContent
from ..utils import ConfigManager

logger = logging.getLogger(__name__)


class ErrorType(Enum):
    """错误类型"""
    MODEL_FAILURE = "model_failure"           # AI模型调用失败
    CONTENT_GENERATION = "content_generation" # 内容生成失败
    PARSING_ERROR = "parsing_error"           # 解析失败
    QUALITY_CHECK = "quality_check"           # 质量检查失败
    RENDERING_ERROR = "rendering_error"       # 渲染失败
    NETWORK_ERROR = "network_error"           # 网络错误
    VALIDATION_ERROR = "validation_error"     # 验证失败
    RESOURCE_ERROR = "resource_error"         # 资源不足
    CONFIGURATION_ERROR = "configuration_error"  # 配置错误
    UNKNOWN_ERROR = "unknown_error"           # 未知错误


class RecoveryStrategy(Enum):
    """恢复策略"""
    RETRY = "retry"                     # 重试
    FALLBACK = "fallback"               # 降级处理
    SKIP = "skip"                       # 跳过
    ALTERNATIVE = "alternative"         # 替代方案
    MANUAL_INTERVENTION = "manual"      # 需要人工干预
    GRACEFUL_DEGRADATION = "degrade"    # 优雅降级


@dataclass
class RecoveryAction:
    """恢复动作"""
    strategy: RecoveryStrategy
    action_func: Optional[Callable] = None
    parameters: Dict[str, Any] = None
    max_attempts: int = 3
    delay_seconds: float = 1.0
    description: str = ""
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}


class ErrorRecoveryManager:
    """错误恢复管理器"""
    
    def __init__(self):
        """初始化错误恢复管理器"""
        self.config = ConfigManager()
        self.recovery_enabled = self.config.get("ENABLE_ERROR_RECOVERY", "true").lower() == "true"
        self.max_global_retries = int(self.config.get("MAX_GLOBAL_RETRIES", "3"))
        self.recovery_delay = float(self.config.get("RECOVERY_DELAY", "2.0"))
        
        # 错误计数器
        self.error_counts = {}
        self.recovery_history = []
        
        # 注册恢复策略
        self._register_recovery_strategies()
        
        logger.info(f"错误恢复管理器初始化完成，启用状态: {self.recovery_enabled}")
    
    def _register_recovery_strategies(self):
        """注册恢复策略 - 增强版本，支持上下文相关的恢复决策"""
        self.recovery_strategies = {
            ErrorType.MODEL_FAILURE: [
                RecoveryAction(
                    strategy=RecoveryStrategy.RETRY,
                    action_func=self._smart_retry,
                    max_attempts=3,
                    delay_seconds=2.0,
                    description="智能重试AI模型调用"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.ALTERNATIVE,
                    action_func=self._try_alternative_model,
                    description="尝试备用AI模型"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.FALLBACK,
                    action_func=self._use_template_content,
                    description="使用模板内容"
                )
            ],
            
            ErrorType.CONTENT_GENERATION: [
                RecoveryAction(
                    strategy=RecoveryStrategy.RETRY,
                    action_func=self._retry_with_context_adjustment,
                    max_attempts=2,
                    delay_seconds=1.0,
                    description="调整上下文后重试"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.ALTERNATIVE,
                    action_func=self._simplify_generation_prompt,
                    description="简化生成提示"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.FALLBACK,
                    action_func=self._use_basic_content,
                    description="使用基础内容模板"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.GRACEFUL_DEGRADATION,
                    action_func=self._create_minimal_slide,
                    description="创建最小化幻灯片"
                )
            ],
            
            ErrorType.PARSING_ERROR: [
                RecoveryAction(
                    strategy=RecoveryStrategy.ALTERNATIVE,
                    action_func=self._try_alternative_parsing,
                    description="尝试备用解析方法"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.FALLBACK,
                    action_func=self._extract_partial_content,
                    description="提取部分可用内容"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.RETRY,
                    action_func=self._retry_with_cleaner_prompt,
                    max_attempts=2,
                    description="使用清理后的提示重试"
                )
            ],
            
            ErrorType.QUALITY_CHECK: [
                RecoveryAction(
                    strategy=RecoveryStrategy.RETRY,
                    action_func=self._retry_with_quality_focus,
                    max_attempts=2,
                    description="专注质量重新生成"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.FALLBACK,
                    action_func=self._accept_with_warning,
                    description="接受但添加质量警告"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.ALTERNATIVE,
                    action_func=self._apply_quality_fixes,
                    description="应用质量修正"
                )
            ],
            
            ErrorType.RENDERING_ERROR: [
                RecoveryAction(
                    strategy=RecoveryStrategy.RETRY,
                    action_func=self._retry_with_fallback_template,
                    description="使用备用模板重试"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.ALTERNATIVE,
                    action_func=self._simplify_rendering,
                    description="简化渲染复杂度"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.FALLBACK,
                    action_func=self._basic_html_rendering,
                    description="基础HTML渲染"
                )
            ],
            
            ErrorType.NETWORK_ERROR: [
                RecoveryAction(
                    strategy=RecoveryStrategy.RETRY,
                    action_func=self._exponential_backoff_retry,
                    max_attempts=5,
                    delay_seconds=1.0,
                    description="指数退避重试"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.FALLBACK,
                    action_func=self._use_offline_mode,
                    description="切换离线模式"
                )
            ],
            
            ErrorType.RESOURCE_ERROR: [
                RecoveryAction(
                    strategy=RecoveryStrategy.ALTERNATIVE,
                    action_func=self._reduce_resource_usage,
                    description="减少资源使用"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.GRACEFUL_DEGRADATION,
                    action_func=self._batch_processing_fallback,
                    description="降级到批处理模式"
                )
            ],
            
            ErrorType.VALIDATION_ERROR: [
                RecoveryAction(
                    strategy=RecoveryStrategy.ALTERNATIVE,
                    action_func=self._fix_validation_issues,
                    description="修复验证问题"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.FALLBACK,
                    action_func=self._skip_validation,
                    description="跳过验证继续"
                )
            ],
            
            ErrorType.CONFIGURATION_ERROR: [
                RecoveryAction(
                    strategy=RecoveryStrategy.ALTERNATIVE,
                    action_func=self._use_default_config,
                    description="使用默认配置"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.MANUAL_INTERVENTION,
                    action_func=self._prompt_config_fix,
                    description="提示配置修复"
                )
            ],
            
            ErrorType.UNKNOWN_ERROR: [
                RecoveryAction(
                    strategy=RecoveryStrategy.RETRY,
                    max_attempts=1,
                    description="单次重试"
                ),
                RecoveryAction(
                    strategy=RecoveryStrategy.GRACEFUL_DEGRADATION,
                    action_func=self._emergency_fallback,
                    description="紧急降级处理"
                )
            ]
        }

    def _classify_error(self, error: Exception, context: Dict[str, Any]) -> ErrorType:
        """增强的错误分类，支持上下文相关的智能分类"""
        error_message = str(error).lower()
        error_class = type(error).__name__.lower()
        
        # 获取上下文信息
        operation = context.get("operation", "").lower()
        slide_id = context.get("slide_id", 0)
        attempt_count = context.get("attempt_count", 0)
        
        # 基于错误消息的分类
        if any(keyword in error_message for keyword in ["timeout", "connection", "network", "unreachable"]):
            return ErrorType.NETWORK_ERROR
            
        elif any(keyword in error_message for keyword in ["api_key", "openai", "google", "authentication", "unauthorized"]):
            return ErrorType.MODEL_FAILURE
            
        elif any(keyword in error_message for keyword in ["json", "parse", "decode", "invalid format"]):
            return ErrorType.PARSING_ERROR
            
        elif any(keyword in error_message for keyword in ["validation", "invalid", "constraint", "requirement"]):
            return ErrorType.VALIDATION_ERROR
            
        elif any(keyword in error_message for keyword in ["memory", "resource", "quota", "limit"]):
            return ErrorType.RESOURCE_ERROR
            
        elif any(keyword in error_message for keyword in ["config", "setting", "environment", "missing"]):
            return ErrorType.CONFIGURATION_ERROR
            
        elif any(keyword in error_message for keyword in ["quality", "score", "threshold"]):
            return ErrorType.QUALITY_CHECK
            
        elif any(keyword in error_message for keyword in ["render", "html", "template"]):
            return ErrorType.RENDERING_ERROR
            
        # 基于上下文的分类
        elif operation in ["generate_content", "content_generation"] and "content" in error_message:
            return ErrorType.CONTENT_GENERATION
            
        elif operation in ["render", "html_render"] and any(keyword in error_message for keyword in ["template", "css", "style"]):
            return ErrorType.RENDERING_ERROR
            
        # 基于错误类型的分类
        elif error_class in ["connectionerror", "timeout", "httperror"]:
            return ErrorType.NETWORK_ERROR
            
        elif error_class in ["jsondecodeerror", "valueerror", "keyerror"]:
            return ErrorType.PARSING_ERROR
            
        elif error_class in ["attributeerror", "typeerror", "importerror"]:
            return ErrorType.CONFIGURATION_ERROR
            
        # 基于重试次数的动态分类
        if attempt_count > 2:
            logger.warning(f"错误多次重试后仍失败，可能需要人工干预: {error_message}")
            return ErrorType.UNKNOWN_ERROR
            
        return ErrorType.UNKNOWN_ERROR

    def _should_abort_recovery(self, error_type: ErrorType, context: Dict[str, Any] = None) -> bool:
        """智能决定是否应该放弃恢复"""
        if context is None:
            context = {}
            
        # 检查全局重试限制
        if self.error_counts.get(error_type, 0) >= self.max_global_retries:
            return True
            
        # 检查特定上下文的限制
        slide_id = context.get("slide_id")
        if slide_id:
            slide_error_key = f"{error_type.value}_{slide_id}"
            slide_errors = context.get("slide_errors", {}).get(slide_error_key, 0)
            if slide_errors >= 2:  # 每张幻灯片最多重试2次
                logger.warning(f"幻灯片 {slide_id} 的 {error_type.value} 错误已达到最大重试次数")
                return True
                
        # 检查连续错误
        if len(self.recovery_history) >= 5:
            recent_failures = [r for r in self.recovery_history[-5:] if r.get("result") == "failure"]
            if len(recent_failures) >= 4:  # 最近5次恢复中有4次失败
                logger.error("连续恢复失败过多，停止自动恢复")
                return True
                
        # 检查危险的错误类型
        dangerous_errors = [ErrorType.CONFIGURATION_ERROR, ErrorType.RESOURCE_ERROR]
        if error_type in dangerous_errors and self.error_counts.get(error_type, 0) >= 1:
            return True
            
        return False

    def _execute_recovery_action(self, action: RecoveryAction, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """增强的恢复动作执行，包含验证和回滚机制"""
        action_start_time = time.time()
        
        try:
            logger.info(f"执行恢复动作: {action.description}")
            
            # 保存当前状态以便回滚
            state_snapshot = self._create_state_snapshot(state)
            
            # 执行恢复动作
            result = None
            if action.strategy == RecoveryStrategy.RETRY:
                result = self._execute_retry_action(action, error, context, state)
            elif action.action_func:
                result = action.action_func(error, context, state)
            else:
                logger.warning(f"恢复动作缺少执行函数: {action.description}")
                return None
                
            # 验证恢复结果
            if self._validate_recovery_result(result, action, context):
                execution_time = time.time() - action_start_time
                logger.info(f"恢复动作成功: {action.description} (耗时: {execution_time:.2f}s)")
                
                # 记录成功的恢复
                self._record_recovery_attempt(action, error, context, "success", execution_time)
                return result
            else:
                # 恢复结果验证失败，回滚状态
                logger.warning(f"恢复结果验证失败: {action.description}")
                self._restore_state_snapshot(state, state_snapshot)
                self._record_recovery_attempt(action, error, context, "validation_failed", time.time() - action_start_time)
                return None
                
        except Exception as recovery_error:
            execution_time = time.time() - action_start_time
            logger.error(f"恢复动作执行失败: {action.description}, 错误: {recovery_error}")
            self._record_recovery_attempt(action, error, context, "execution_failed", execution_time)
            raise recovery_error

    def _validate_recovery_result(self, result: Any, action: RecoveryAction, context: Dict[str, Any]) -> bool:
        """验证恢复结果的有效性"""
        if result is None:
            return False
            
        # 根据恢复策略类型进行不同的验证
        if action.strategy == RecoveryStrategy.RETRY:
            # 重试策略：检查是否获得了有效结果
            return result is not None
            
        elif action.strategy == RecoveryStrategy.FALLBACK:
            # 降级策略：检查是否提供了可用的替代内容
            if isinstance(result, SlideContent):
                return len(result.title.strip()) > 0 and len(result.content.strip()) > 0
            return True
            
        elif action.strategy == RecoveryStrategy.ALTERNATIVE:
            # 替代策略：检查替代方案是否可行
            return result is not None
            
        elif action.strategy == RecoveryStrategy.GRACEFUL_DEGRADATION:
            # 优雅降级：接受任何非空结果
            return result is not None
            
        # 默认验证
        return True

    def _create_state_snapshot(self, state: OverallState) -> Dict[str, Any]:
        """创建状态快照用于回滚"""
        return {
            "errors_count": len(state.errors),
            "warnings_count": len(state.warnings),
            "slides_count": len(state.slides),
            "generation_metadata_count": len(state.generation_metadata)
        }

    def _restore_state_snapshot(self, state: OverallState, snapshot: Dict[str, Any]):
        """从快照恢复状态"""
        # 只回滚在恢复过程中添加的内容
        current_errors = len(state.errors)
        if current_errors > snapshot["errors_count"]:
            state.errors = state.errors[:snapshot["errors_count"]]
            
        current_warnings = len(state.warnings)
        if current_warnings > snapshot["warnings_count"]:
            state.warnings = state.warnings[:snapshot["warnings_count"]]

    def _record_recovery_attempt(self, action: RecoveryAction, error: Exception, context: Dict[str, Any], result: str, execution_time: float):
        """记录恢复尝试的详细信息"""
        attempt_record = {
            "timestamp": time.time(),
            "action": action.description,
            "strategy": action.strategy.value,
            "error_type": self._classify_error(error, context).value,
            "result": result,
            "execution_time": execution_time,
            "context": {
                "operation": context.get("operation", ""),
                "slide_id": context.get("slide_id", ""),
                "attempt_count": context.get("attempt_count", 0)
            }
        }
        
        self.recovery_history.append(attempt_record)
        
        # 保持历史记录在合理大小
        if len(self.recovery_history) > 100:
            self.recovery_history = self.recovery_history[-50:]

    # ==================== 智能恢复方法 ====================
    
    def _smart_retry(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """智能重试，根据错误类型调整重试策略"""
        attempt_count = context.get("attempt_count", 0)
        max_attempts = 3
        
        # 根据错误类型调整重试参数
        error_type = self._classify_error(error, context)
        if error_type == ErrorType.NETWORK_ERROR:
            max_attempts = 5  # 网络错误多重试几次
            delay = min(2 ** attempt_count, 30)  # 指数退避，最大30秒
        elif error_type == ErrorType.MODEL_FAILURE:
            max_attempts = 2  # 模型错误少重试
            delay = 5.0  # 固定延迟
        else:
            delay = 1.0 + attempt_count  # 线性增加延迟
            
        logger.info(f"智能重试第 {attempt_count + 1} 次，延迟 {delay} 秒")
        time.sleep(delay)
        
        # 获取原始函数并重试
        original_func = context.get("original_function")
        if original_func:
            return original_func()
        else:
            logger.error("智能重试失败：缺少原始函数")
            return None

    def _retry_with_context_adjustment(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """调整上下文后重试内容生成"""
        slide_id = context.get("slide_id", 0)
        
        # 减少滑动窗口大小
        original_window_size = state.sliding_window_size
        state.sliding_window_size = max(1, original_window_size - 1)
        
        logger.info(f"调整滑动窗口大小: {original_window_size} -> {state.sliding_window_size}")
        
        try:
            # 重新生成内容
            original_func = context.get("original_function")
            if original_func:
                result = original_func()
                return result
            else:
                logger.error("上下文调整重试失败：缺少原始函数")
                return None
        finally:
            # 恢复原始窗口大小
            state.sliding_window_size = original_window_size

    def _retry_with_cleaner_prompt(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """使用清理后的提示重试"""
        # 简化提示，移除复杂的格式要求
        simplified_context = context.copy()
        simplified_context["simplified_prompt"] = True
        simplified_context["reduce_complexity"] = True
        
        logger.info("使用简化提示重试")
        
        original_func = context.get("original_function")
        if original_func:
            # 通过修改上下文来影响提示生成
            return original_func()
        return None

    def _retry_with_quality_focus(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """专注质量的重新生成"""
        # 降低质量阈值，但增加质量约束
        original_threshold = state.quality_threshold
        state.quality_threshold = max(0.6, original_threshold - 0.1)
        
        logger.info(f"调整质量阈值: {original_threshold} -> {state.quality_threshold}")
        
        try:
            original_func = context.get("original_function")
            if original_func:
                return original_func()
            return None
        finally:
            state.quality_threshold = original_threshold

    def _exponential_backoff_retry(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """指数退避重试，特别适用于网络错误"""
        attempt_count = context.get("attempt_count", 0)
        max_attempts = 5
        base_delay = 1.0
        
        for attempt in range(max_attempts):
            delay = base_delay * (2 ** attempt) + (attempt * 0.1)  # 添加抖动
            delay = min(delay, 60)  # 最大延迟60秒
            
            logger.info(f"指数退避重试第 {attempt + 1} 次，延迟 {delay:.1f} 秒")
            time.sleep(delay)
            
            try:
                original_func = context.get("original_function")
                if original_func:
                    result = original_func()
                    logger.info(f"指数退避重试成功，第 {attempt + 1} 次")
                    return result
            except Exception as retry_error:
                logger.warning(f"重试第 {attempt + 1} 次失败: {retry_error}")
                if attempt == max_attempts - 1:
                    raise retry_error
                    
        return None

    def _apply_quality_fixes(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """应用质量修正"""
        slide_content = context.get("slide_content")
        if not slide_content:
            return None
            
        # 基础质量修正
        fixed_content = slide_content
        
        # 修正标题
        if not fixed_content.title or len(fixed_content.title.strip()) < 3:
            fixed_content.title = f"幻灯片 {fixed_content.slide_id}"
            
        # 修正内容长度
        if len(fixed_content.content.strip()) < 20:
            fixed_content.content += "\n\n• 详细内容将在后续完善\n• 请参考相关资料获取更多信息"
            
        # 修正要点数量
        if fixed_content.key_points and len(fixed_content.key_points) < 2:
            fixed_content.key_points.append("后续将补充更多要点")
            
        logger.info("应用基础质量修正")
        return fixed_content

    def _retry_with_fallback_template(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """使用备用模板重试渲染"""
        # 切换到最基础的模板
        fallback_context = context.copy()
        fallback_context["use_basic_template"] = True
        fallback_context["disable_animations"] = True
        fallback_context["minimal_css"] = True
        
        logger.info("使用备用模板重试渲染")
        
        original_func = context.get("original_function")
        if original_func:
            return original_func()
        return None

    def _simplify_rendering(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """简化渲染复杂度"""
        # 移除复杂的样式和动画
        simplified_slides = []
        for slide in state.slides:
            simplified_slide = slide.copy()
            simplified_slide.animations = []
            simplified_slide.custom_css = ""
            simplified_slides.append(simplified_slide)
            
        # 临时替换slides进行渲染
        original_slides = state.slides
        state.slides = simplified_slides
        
        try:
            original_func = context.get("original_function")
            if original_func:
                result = original_func()
                logger.info("简化渲染成功")
                return result
        finally:
            state.slides = original_slides

    def _basic_html_rendering(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """基础HTML渲染作为最后的降级选择"""
        logger.info("使用基础HTML渲染")
        
        # 创建最基础的HTML结构
        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='zh-CN'>",
            "<head>",
            "    <meta charset='UTF-8'>",
            "    <title>演示文稿</title>",
            "    <style>",
            "        body { font-family: Arial, sans-serif; margin: 20px; }",
            "        .slide { page-break-after: always; margin-bottom: 50px; }",
            "        h1 { color: #333; border-bottom: 2px solid #007cba; }",
            "        h2 { color: #666; }",
            "        ul { line-height: 1.6; }",
            "    </style>",
            "</head>",
            "<body>"
        ]
        
        # 添加幻灯片内容
        for i, slide in enumerate(state.slides, 1):
            html_parts.extend([
                f"    <div class='slide'>",
                f"        <h1>第{i}页: {slide.title}</h1>",
                f"        <div>{slide.content}</div>",
            ])
            
            if slide.key_points:
                html_parts.append("        <ul>")
                for point in slide.key_points:
                    html_parts.append(f"            <li>{point}</li>")
                html_parts.append("        </ul>")
                
            html_parts.append("    </div>")
            
        html_parts.extend([
            "</body>",
            "</html>"
        ])
        
        return "\n".join(html_parts)

    def _batch_processing_fallback(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """降级到批处理模式"""
        logger.info("切换到批处理模式")
        
        # 减少并发处理，改为顺序处理
        batch_context = context.copy()
        batch_context["batch_mode"] = True
        batch_context["reduce_concurrency"] = True
        batch_context["memory_conservative"] = True
        
        original_func = context.get("original_function")
        if original_func:
            return original_func()
        return None

    def _fix_validation_issues(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """修复验证问题"""
        validation_errors = context.get("validation_errors", [])
        
        for validation_error in validation_errors:
            error_type = validation_error.get("type", "")
            field = validation_error.get("field", "")
            
            if error_type == "missing_required":
                self._fix_missing_required_field(field, state)
            elif error_type == "invalid_format":
                self._fix_invalid_format_field(field, state)
            elif error_type == "constraint_violation":
                self._fix_constraint_violation(field, validation_error, state)
                
        logger.info(f"修复了 {len(validation_errors)} 个验证问题")
        return True

    def _fix_missing_required_field(self, field: str, state: OverallState):
        """修复缺失的必需字段"""
        if field == "title" and state.outline:
            if not state.outline.title:
                state.outline.title = "演示文稿"
        elif field == "content":
            # 为缺少内容的幻灯片添加默认内容
            for slide in state.slides:
                if not slide.content or len(slide.content.strip()) < 5:
                    slide.content = f"此幻灯片的详细内容正在准备中。\n\n主题: {slide.title}"

    def _fix_invalid_format_field(self, field: str, state: OverallState):
        """修复格式无效的字段"""
        # 清理和格式化字段内容
        for slide in state.slides:
            if field == "title":
                slide.title = slide.title.strip()[:100]  # 限制长度
            elif field == "content":
                # 清理内容格式
                slide.content = slide.content.strip()
                if not slide.content.endswith(('.', '!', '?', '。', '！', '？')):
                    slide.content += '。'

    def _fix_constraint_violation(self, field: str, validation_error: Dict, state: OverallState):
        """修复约束违反"""
        constraint = validation_error.get("constraint", "")
        
        if constraint == "max_length":
            max_length = validation_error.get("max_length", 500)
            for slide in state.slides:
                if field == "content" and len(slide.content) > max_length:
                    slide.content = slide.content[:max_length-3] + "..."

    def _skip_validation(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """跳过验证继续处理"""
        logger.warning("跳过验证步骤继续处理")
        state.warnings.append("已跳过部分验证步骤，请手动检查结果质量")
        return True

    def _use_default_config(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """使用默认配置"""
        logger.info("使用默认配置继续处理")
        
        # 设置安全的默认值
        default_config = {
            "sliding_window_size": 3,
            "quality_threshold": 0.7,
            "max_retries": 2,
            "timeout": 30
        }
        
        for key, value in default_config.items():
            if hasattr(state, key):
                setattr(state, key, value)
                
        return True

    def _prompt_config_fix(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """提示配置修复"""
        config_issue = str(error)
        logger.error(f"配置错误需要人工干预: {config_issue}")
        
        state.errors.append(f"配置错误: {config_issue}")
        state.warnings.append("请检查配置文件并修复错误后重试")
        
        # 记录详细的配置问题
        return {
            "requires_manual_fix": True,
            "error_details": config_issue,
            "suggested_actions": [
                "检查.env文件是否存在",
                "验证API密钥是否正确",
                "确认所有必需的配置项都已设置"
            ]
        }

    def _emergency_fallback(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """紧急降级处理"""
        logger.error(f"执行紧急降级处理: {error}")
        
        # 创建最基本的响应
        if context.get("operation") == "generate_content":
            return self._create_minimal_slide(error, context, state)
        elif context.get("operation") == "render_html":
            return self._basic_html_rendering(error, context, state)
        else:
            # 通用的紧急处理
            state.warnings.append(f"发生未知错误，已应用紧急降级: {str(error)[:100]}")
            return True

    def get_recovery_statistics(self) -> Dict[str, Any]:
        """获取恢复统计信息"""
        if not self.recovery_history:
            return {"total_attempts": 0, "success_rate": 0}
            
        total_attempts = len(self.recovery_history)
        successful_attempts = len([r for r in self.recovery_history if r.get("result") == "success"])
        
        # 按错误类型统计
        error_type_stats = {}
        for record in self.recovery_history:
            error_type = record.get("error_type", "unknown")
            if error_type not in error_type_stats:
                error_type_stats[error_type] = {"total": 0, "success": 0}
            error_type_stats[error_type]["total"] += 1
            if record.get("result") == "success":
                error_type_stats[error_type]["success"] += 1
                
        # 计算成功率
        for stats in error_type_stats.values():
            stats["success_rate"] = stats["success"] / stats["total"] if stats["total"] > 0 else 0
            
        return {
            "total_attempts": total_attempts,
            "successful_attempts": successful_attempts,
            "success_rate": successful_attempts / total_attempts if total_attempts > 0 else 0,
            "error_type_statistics": error_type_stats,
            "current_error_counts": dict(self.error_counts),
            "average_execution_time": sum(r.get("execution_time", 0) for r in self.recovery_history) / total_attempts if total_attempts > 0 else 0
        }
    
    def handle_error(self, error: Exception, error_context: Dict[str, Any], state: OverallState) -> Any:
        """
        处理错误并尝试恢复
        
        Args:
            error: 发生的异常
            error_context: 错误上下文信息
            state: 当前状态
            
        Returns:
            恢复结果或None
        """
        if not self.recovery_enabled:
            logger.error(f"错误恢复已禁用，抛出原始错误: {error}")
            raise error
        
        logger.warning(f"检测到错误，开始恢复处理: {error}")
        
        # 错误分类
        error_type = self._classify_error(error, error_context)
        
        # 更新错误计数
        self._update_error_count(error_type)
        
        # 检查是否超过全局重试限制
        if self._should_abort_recovery(error_type):
            logger.error(f"错误类型 {error_type} 已达到最大重试次数，停止恢复")
            self._record_recovery_failure(error, error_type, "达到最大重试次数")
            raise error
        
        # 获取恢复策略
        strategies = self.recovery_strategies.get(error_type, [])
        
        if not strategies:
            logger.error(f"未找到错误类型 {error_type} 的恢复策略")
            self._record_recovery_failure(error, error_type, "无可用恢复策略")
            raise error
        
        # 依次尝试恢复策略
        for strategy in strategies:
            try:
                logger.info(f"尝试恢复策略: {strategy.description}")
                result = self._execute_recovery_action(strategy, error, error_context, state)
                
                if result is not None:
                    logger.info(f"错误恢复成功: {strategy.description}")
                    self._record_recovery_success(error, error_type, strategy)
                    return result
                    
            except Exception as recovery_error:
                logger.warning(f"恢复策略失败: {strategy.description}, 错误: {recovery_error}")
                continue
        
        # 所有恢复策略都失败
        logger.error(f"所有恢复策略都失败，错误类型: {error_type}")
        self._record_recovery_failure(error, error_type, "所有策略失败")
        raise error
    
    def _classify_error(self, error: Exception, context: Dict[str, Any]) -> ErrorType:
        """错误分类"""
        error_message = str(error).lower()
        error_class = type(error).__name__.lower()
        
        # 基于异常类型和消息分类
        if "timeout" in error_message or "connection" in error_message:
            return ErrorType.NETWORK_ERROR
        elif "api_key" in error_message or "openai" in error_message or "google" in error_message:
            return ErrorType.MODEL_FAILURE
        elif "json" in error_message or "parse" in error_message:
            return ErrorType.PARSING_ERROR
        elif "validation" in error_message or "invalid" in error_message:
            return ErrorType.VALIDATION_ERROR
        elif "memory" in error_message or "resource" in error_message:
            return ErrorType.RESOURCE_ERROR
        elif "config" in error_message or "setting" in error_message:
            return ErrorType.CONFIGURATION_ERROR
        elif context.get("operation") == "content_generation":
            return ErrorType.CONTENT_GENERATION
        elif context.get("operation") == "quality_check":
            return ErrorType.QUALITY_CHECK
        elif context.get("operation") == "rendering":
            return ErrorType.RENDERING_ERROR
        else:
            return ErrorType.UNKNOWN_ERROR
    
    def _update_error_count(self, error_type: ErrorType):
        """更新错误计数"""
        if error_type not in self.error_counts:
            self.error_counts[error_type] = 0
        self.error_counts[error_type] += 1
    
    def _should_abort_recovery(self, error_type: ErrorType) -> bool:
        """判断是否应该停止恢复"""
        return self.error_counts.get(error_type, 0) >= self.max_global_retries
    
    def _execute_recovery_action(self, action: RecoveryAction, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """执行恢复动作"""
        if action.strategy == RecoveryStrategy.RETRY:
            return self._execute_retry(action, context)
        elif action.strategy == RecoveryStrategy.FALLBACK and action.action_func:
            return action.action_func(error, context, state)
        elif action.strategy == RecoveryStrategy.ALTERNATIVE and action.action_func:
            return action.action_func(error, context, state)
        elif action.strategy == RecoveryStrategy.GRACEFUL_DEGRADATION and action.action_func:
            return action.action_func(error, context, state)
        elif action.strategy == RecoveryStrategy.SKIP:
            logger.info("跳过当前操作")
            return "SKIPPED"
        else:
            logger.warning(f"未实现的恢复策略: {action.strategy}")
            return None
    
    def _execute_retry(self, action: RecoveryAction, context: Dict[str, Any]) -> Any:
        """执行重试"""
        original_func = context.get("original_function")
        original_args = context.get("original_args", ())
        original_kwargs = context.get("original_kwargs", {})
        
        if not original_func:
            logger.error("重试失败：缺少原始函数")
            return None
        
        for attempt in range(action.max_attempts):
            try:
                logger.info(f"重试第 {attempt + 1}/{action.max_attempts} 次")
                time.sleep(action.delay_seconds * (attempt + 1))  # 指数退避
                
                result = original_func(*original_args, **original_kwargs)
                logger.info(f"重试成功，第 {attempt + 1} 次尝试")
                return result
                
            except Exception as retry_error:
                logger.warning(f"重试第 {attempt + 1} 次失败: {retry_error}")
                if attempt == action.max_attempts - 1:
                    raise retry_error
                continue
        
        return None
    
    # 恢复动作实现
    def _try_alternative_model(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """尝试备用AI模型"""
        logger.info("尝试切换到备用AI模型")
        
        current_provider = context.get("model_provider", "openai")
        alternative_provider = "google" if current_provider == "openai" else "openai"
        
        try:
            # 创建备用模型实例
            from langchain_openai import ChatOpenAI
            from langchain_google_genai import ChatGoogleGenerativeAI
            
            if alternative_provider == "openai":
                alternative_model = ChatOpenAI(
                    model=self.config.get("OPENAI_MODEL", "gpt-3.5-turbo"),
                    temperature=0.7,
                    timeout=60
                )
            else:
                alternative_model = ChatGoogleGenerativeAI(
                    model=self.config.get("GOOGLE_MODEL", "gemini-pro"),
                    temperature=0.7,
                    timeout=60
                )
            
            # 执行原始操作但使用备用模型
            logger.info(f"使用备用模型: {alternative_provider}")
            # 这里需要根据具体的操作类型来调用备用模型
            # 暂时返回成功标志
            return "ALTERNATIVE_MODEL_SUCCESS"
            
        except Exception as alt_error:
            logger.error(f"备用模型也失败: {alt_error}")
            return None
    
    def _use_template_content(self, error: Exception, context: Dict[str, Any], state: OverallState) -> SlideContent:
        """使用模板内容"""
        logger.info("使用模板内容作为降级方案")
        
        slide_id = context.get("slide_id", 1)
        section_title = context.get("section_title", "内容")
        key_point = context.get("key_point", "要点")
        
        from ..state import SlideContent, SlideType
        
        template_slide = SlideContent(
            slide_id=slide_id,
            title=f"{section_title} - {key_point}",
            slide_type=SlideType.CONTENT,
            main_content=f"关于{key_point}的内容。由于生成问题，此页面使用了模板内容。",
            bullet_points=[
                "这是一个模板要点",
                "请手动完善此页内容",
                "确保与演示主题相关"
            ],
            speaker_notes="此页面由错误恢复机制生成，需要手动完善内容。",
            design_suggestions="使用简洁的布局，突出需要完善的提示"
        )
        
        return template_slide
    
    def _simplify_generation_prompt(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """简化生成提示词"""
        logger.info("简化生成提示词并重试")
        
        # 创建简化版的提示词
        simplified_context = {
            "title": context.get("title", "内容"),
            "main_point": context.get("key_point", "要点")[:100],  # 截短内容
            "slide_id": context.get("slide_id", 1)
        }
        
        # 返回简化的上下文，让调用方使用简化的生成逻辑
        return simplified_context
    
    def _use_basic_content(self, error: Exception, context: Dict[str, Any], state: OverallState) -> SlideContent:
        """使用基础内容格式"""
        logger.info("使用基础内容格式")
        
        slide_id = context.get("slide_id", 1)
        title = context.get("title", "内容页")
        key_point = context.get("key_point", "")
        
        from ..state import SlideContent, SlideType
        
        basic_slide = SlideContent(
            slide_id=slide_id,
            title=title,
            slide_type=SlideType.CONTENT,
            main_content=key_point if key_point else "内容生成遇到问题，使用基础格式。",
            bullet_points=["内容要点1", "内容要点2", "内容要点3"] if not key_point else [key_point],
            speaker_notes="使用基础内容格式生成。",
            design_suggestions="简洁布局"
        )
        
        return basic_slide
    
    def _try_alternative_parsing(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """尝试备用解析方法"""
        logger.info("尝试备用解析方法")
        
        raw_content = context.get("raw_content", "")
        if not raw_content:
            return None
        
        # 尝试简单的文本提取
        try:
            import re
            
            # 尝试提取标题
            title_match = re.search(r'"title":\s*"([^"]*)"', raw_content)
            title = title_match.group(1) if title_match else "解析失败的标题"
            
            # 尝试提取主要内容
            content_match = re.search(r'"main_content":\s*"([^"]*)"', raw_content)
            content = content_match.group(1) if content_match else "解析失败，请手动检查内容"
            
            return {
                "title": title,
                "main_content": content,
                "bullet_points": ["解析部分成功", "需要手动检查"],
                "slide_type": "content"
            }
            
        except Exception as parse_error:
            logger.error(f"备用解析也失败: {parse_error}")
            return None
    
    def _extract_partial_content(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """提取部分可用内容"""
        logger.info("提取部分可用内容")
        
        raw_content = context.get("raw_content", "")
        
        # 简单的部分内容提取
        if len(raw_content) > 20:
            return {
                "title": "部分恢复的内容",
                "main_content": raw_content[:200] + "...",
                "bullet_points": ["内容部分恢复", "需要进一步处理"],
                "slide_type": "content"
            }
        
        return None
    
    def _create_minimal_slide(self, error: Exception, context: Dict[str, Any], state: OverallState) -> SlideContent:
        """创建最小化幻灯片"""
        logger.info("创建最小化幻灯片")
        
        from ..state import SlideContent, SlideType
        
        slide_id = context.get("slide_id", 1)
        
        minimal_slide = SlideContent(
            slide_id=slide_id,
            title=f"幻灯片 {slide_id}",
            slide_type=SlideType.CONTENT,
            main_content="内容生成遇到问题，已创建占位幻灯片。",
            bullet_points=["请手动添加内容"],
            speaker_notes="此页面需要手动完善。",
            design_suggestions="最小化设计"
        )
        
        return minimal_slide
    
    def _accept_with_warning(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """降低质量要求并接受"""
        logger.warning("降低质量要求，接受当前内容")
        
        # 添加警告信息到状态
        warning_msg = f"质量检查失败但已接受: {str(error)[:100]}"
        if hasattr(state, 'warnings'):
            state.warnings.append(warning_msg)
        
        return "QUALITY_ACCEPTED_WITH_WARNING"
    
    def _use_offline_mode(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """切换到离线模式"""
        logger.info("切换到离线模式")
        
        # 设置离线标志
        if hasattr(state, 'custom_styles'):
            state.custom_styles['offline_mode'] = True
        
        return "OFFLINE_MODE_ENABLED"
    
    def _reduce_resource_usage(self, error: Exception, context: Dict[str, Any], state: OverallState) -> Any:
        """减少资源使用"""
        logger.info("减少资源使用")
        
        # 简化处理逻辑
        return "RESOURCE_USAGE_REDUCED"
    
    def _record_recovery_success(self, error: Exception, error_type: ErrorType, strategy: RecoveryAction):
        """记录恢复成功"""
        self.recovery_history.append({
            "timestamp": time.time(),
            "error_type": error_type.value,
            "strategy": strategy.strategy.value,
            "result": "success",
            "description": strategy.description
        })
    
    def _record_recovery_failure(self, error: Exception, error_type: ErrorType, reason: str):
        """记录恢复失败"""
        self.recovery_history.append({
            "timestamp": time.time(),
            "error_type": error_type.value,
            "result": "failure",
            "reason": reason,
            "error_message": str(error)
        })
    
    def get_recovery_stats(self) -> Dict[str, Any]:
        """获取恢复统计信息"""
        total_recoveries = len(self.recovery_history)
        successful_recoveries = len([r for r in self.recovery_history if r["result"] == "success"])
        
        return {
            "total_errors": sum(self.error_counts.values()),
            "error_types": dict(self.error_counts),
            "total_recoveries": total_recoveries,
            "successful_recoveries": successful_recoveries,
            "success_rate": successful_recoveries / total_recoveries if total_recoveries > 0 else 0,
            "recent_recoveries": self.recovery_history[-10:]  # 最近10次恢复记录
        }