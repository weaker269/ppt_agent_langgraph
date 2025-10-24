"""PPT Agent 高级工作流。"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from src.rag.index import IndexBuilder
from src.rag.models import DocumentMetadata, DocumentSection, LoadedDocument
from src.rag.retriever import HybridRetriever
from src.rag.metrics import RetrievalMetricsLogger


from .ai_client import AIConfig, AIModelClient
from .domain import PresentationOutline, SlideContent
from .evaluators import QualityEvaluator
from .generators.content import SlidingWindowContentGenerator
from .generators.outline import OutlineGenerator
from .generators.style import StyleSelector
from .renderers.html import HTMLRenderer
from .state import OverallState
from .utils import logger, result_saver, snapshot_manager
from .validators import ConsistencyChecker


class PPTAgentGraph:
    """整合 LLM、质量评估、样式与一致性检查的工作流。"""

    def __init__(
        self,
        model_provider: str = "openai",
        model_name: str = "gpt-3.5-turbo",
        use_stub: bool = False,
    ) -> None:
        config = AIConfig(provider=model_provider, model=model_name, enable_stub=use_stub)
        self.client = AIModelClient(config)
        self.quality_evaluator = QualityEvaluator(self.client)
        self.outline_generator = OutlineGenerator(self.client)
        self.style_selector = StyleSelector(self.client)
        self.content_generator = SlidingWindowContentGenerator(self.client, self.quality_evaluator)
        self.consistency_checker = ConsistencyChecker(self.client)
        self.renderer = HTMLRenderer()

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def run(self, input_text: str = "", input_file_path: str = "") -> OverallState:
        state = OverallState(

            input_text=input_text,

            input_file_path=input_file_path,

            model_provider=self.client.config.provider,

            model_name=self.client.config.model,

        )

        logger.info("启动 PPT 生成流程：RunId=%s", state.run_id)

        snapshot_manager.write_json(state.run_id, "00_run/config", {

            "provider": state.model_provider,

            "model": state.model_name,

            "quality_reflection": state.enable_quality_reflection,

        })

        start_time = time.time()
        self._load_input(state)
        if state.errors:
            return state

        self._prepare_rag(state)

        self.outline_generator.generate_outline(state)
        if state.errors:
            return state

        self.style_selector.select_style_theme(state)
        self.content_generator.generate_all_slides(state)
        if state.errors:
            return state

        state.consistency_report = self.consistency_checker.check(state)
        self.renderer.render_presentation(state)
        if state.errors:
            return state

        self._persist(state)
        logger.info("完整流程完成，耗时 %.2fs", time.time() - start_time)
        return state

    # ------------------------------------------------------------------
    # 辅助步骤
    # ------------------------------------------------------------------

    def _prepare_rag(self, state: OverallState) -> None:
        if state.rag_index is not None or not state.input_text.strip():
            return

        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
        except ImportError:
            warning = "RAG 嵌入模型依赖 sentence-transformers 未安装，已跳过证据索引构建"
            logger.warning(warning)
            state.record_warning(warning)
            return

        model_source = self._resolve_embedding_model_source()
        device = os.getenv("RAG_EMBEDDING_DEVICE", "cpu")
        try:
            embedding_model = SentenceTransformer(model_source, device=device)
        except Exception as exc:  # pragma: no cover - 取决于运行环境
            warning = f"RAG 嵌入模型加载失败: {exc}"
            logger.warning(warning)
            state.record_warning(warning)
            return

        # 检查是否启用索引缓存
        cache_enabled = os.getenv("RAG_INDEX_CACHE_ENABLED", "true").lower() in ("true", "1", "yes")
        cache_base_dir = Path(os.getenv("RAG_INDEX_CACHE_DIR", "cache/rag_index"))
        
        clean_text = state.input_text.strip()
        if not clean_text:
            return

        # 生成缓存键（基于输入文本的哈希）
        import hashlib
        cache_key = hashlib.md5(clean_text.encode("utf-8")).hexdigest()
        cache_dir = cache_base_dir / cache_key

        # 尝试从缓存加载索引
        if cache_enabled and cache_dir.exists():
            try:
                from src.rag.index import ChunkIndex
                index = ChunkIndex.load(cache_dir, embedding_model)
                logger.info("从缓存加载 RAG 索引成功，chunk=%s，缓存路径=%s", len(index.chunks), cache_dir)
                state.rag_index = index
                
                # 创建检索器
                from src.rag.metrics import RetrievalMetricsLogger
                from src.rag.retriever import HybridRetriever
                metrics_logger = RetrievalMetricsLogger()
                state.retriever = HybridRetriever(
                    index,
                    dense_top_k=20,
                    bm25_top_k=30,
                    alpha=0.6,
                    metrics_logger=metrics_logger,
                )
                
                snapshot_manager.write_json(
                    state.run_id,
                    "02_rag/index_stats",
                    {
                        "chunk_count": len(index.chunks),
                        "embedding_model": getattr(index, "embedding_model_name", "unknown"),
                        "bm25_vocabulary_size": len(index.bm25_tokens),
                        "device": device,
                        "loaded_from_cache": True,
                        "cache_key": cache_key,
                    },
                )
                return
            except Exception as exc:
                warning = f"从缓存加载索引失败: {exc}，将重新构建"
                logger.warning(warning)
                state.record_warning(warning)

        # 构建新索引
        builder = IndexBuilder(embedding_model, chunk_size=280, sentence_overlap=1)
        document = LoadedDocument(
            metadata=DocumentMetadata(
                document_id=state.run_id,
                source_path=state.input_file_path or "input_text",
                media_type="text/plain",
            ),
            sections=[
                DocumentSection(
                    section_id="sec_000",
                    title="输入资料",
                    level=1,
                    text=clean_text,
                    start_char=0,
                    end_char=len(clean_text),
                )
            ],
            full_text=clean_text,
        )

        try:
            index = builder.build_from_documents([document])
        except ValueError as exc:
            warning = f"RAG 索引构建失败: {exc}"
            logger.warning(warning)
            state.record_warning(warning)
            return

        # 保存索引到缓存
        if cache_enabled:
            try:
                index.save(cache_dir)
                logger.info("RAG 索引已保存到缓存: %s", cache_dir)
            except Exception as exc:
                warning = f"保存索引到缓存失败: {exc}"
                logger.warning(warning)
                state.record_warning(warning)

        state.rag_index = index
        metrics_logger = RetrievalMetricsLogger()
        state.retriever = HybridRetriever(
            index,
            dense_top_k=20,
            bm25_top_k=30,
            alpha=0.6,
            metrics_logger=metrics_logger,
        )
        snapshot_manager.write_json(
            state.run_id,
            "02_rag/index_stats",
            {
                "chunk_count": len(index.chunks),
                "embedding_model": getattr(index, "embedding_model_name", "unknown"),
                "bm25_vocabulary_size": len(index.bm25_tokens),
                "device": device,
                "loaded_from_cache": False,
                "cache_key": cache_key if cache_enabled else None,
            },
        )
        logger.info("RAG 索引构建完成，chunk=%s，embedding=%s", len(index.chunks), getattr(index, "embedding_model_name", "unknown"))

    def _resolve_embedding_model_source(self) -> str:
        preferred_path = os.getenv("RAG_EMBEDDING_MODEL_PATH")
        if preferred_path and Path(preferred_path).exists():
            return preferred_path

        preferred_name = os.getenv("RAG_EMBEDDING_MODEL")
        if preferred_name:
            return preferred_name

        default_local = Path("E:/hf_cache/models--shibing624--text2vec-base-chinese")
        if default_local.exists():
            return str(default_local)

        return "shibing624/text2vec-base-chinese"

    def _load_input(self, state: OverallState) -> None:
        if state.input_text.strip():
            return
        if not state.input_file_path:
            state.record_error("请提供文本输入或文件路径")
            return
        path = Path(state.input_file_path)
        if not path.exists():
            state.record_error(f"找不到输入文件: {path}")
            return
        state.input_text = path.read_text(encoding="utf-8")
        logger.info("已从文件读取输入: %s", path)

    def _persist(self, state: OverallState) -> None:

        if not state.html_output:

            return

        title = state.outline.title if state.outline else "presentation"

        safe_name = title.replace(" ", "_")[:50] or "presentation"

        html_path = result_saver.save_html(state.html_output, safe_name)

        metadata = {

            "run_id": state.run_id,

            "title": state.outline.title if state.outline else "",

            "slide_count": len(state.slides),

            "quality": {slide_id: score.total_score for slide_id, score in state.slide_quality.items()},

            "consistency": state.consistency_report.overall_score if state.consistency_report else None,

            "theme": state.selected_style.theme.value if state.selected_style else "",

            "chart_colors": state.selected_style.chart_colors if state.selected_style else [],

        }

        result_saver.save_json(metadata, f"{safe_name}_metadata")

        snapshot_manager.write_json(state.run_id, "05_output/metadata", metadata)

        state.output_file_path = str(html_path)




# ----------------------------------------------------------------------


# ----------------------------------------------------------------------
# 便捷函数
# ----------------------------------------------------------------------

def create_ppt_agent(model_provider: str = "openai", model_name: str = "gpt-3.5-turbo", use_stub: bool = False) -> PPTAgentGraph:
    return PPTAgentGraph(model_provider=model_provider, model_name=model_name, use_stub=use_stub)


def generate_ppt_from_text(text: str, model_provider: str = "openai", model_name: str = "gpt-3.5-turbo", use_stub: bool = False) -> OverallState:
    return create_ppt_agent(model_provider, model_name, use_stub).run(input_text=text)


def generate_ppt_from_file(file_path: str, model_provider: str = "openai", model_name: str = "gpt-3.5-turbo", use_stub: bool = False) -> OverallState:
    return create_ppt_agent(model_provider, model_name, use_stub).run(input_file_path=file_path)


__all__ = [
    "PPTAgentGraph",
    "create_ppt_agent",
    "generate_ppt_from_text",
    "generate_ppt_from_file",
]
