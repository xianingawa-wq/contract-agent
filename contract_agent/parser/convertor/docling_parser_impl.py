from __future__ import annotations

import importlib
import importlib.util

from contract_agent.config.config_parser import ParserConfig
from contract_agent.logger.base import ComponentLogger
from contract_agent.parser.convertor.local_file_source import local_parser_source
from contract_agent.parser.exception import DocumentLoadError
from contract_agent.parser.logger import get_parser_logger, parser_log_event
from contract_agent.parser.markdown_document import MarkdownDocument
from contract_agent.parser.parser_backend_contract import ParserBackendSupport
from contract_agent.parser.parser_source import ParserSource


class DoclingParserImpl:
    name = "docling"

    def __init__(self, logger: ComponentLogger | None = None) -> None:
        self.logger = logger or get_parser_logger()

    def supports(self, source: ParserSource, config: ParserConfig) -> ParserBackendSupport:
        if not config.docling_enabled:
            return ParserBackendSupport(supported=False, reason="docling backend disabled")
        if config.docling_enable_remote_services:
            return ParserBackendSupport(
                supported=False,
                reason="docling remote services are disabled by parser safety policy",
            )
        suffix = f".{source.file_type}" if source.file_type else ""
        if source.kind == "text" or suffix.lower() != ".pdf":
            return ParserBackendSupport(
                supported=False,
                reason=f"docling backend supports PDF input only: {suffix or source.kind}",
                can_fallback=True,
            )
        if importlib.util.find_spec("docling") is None:
            return ParserBackendSupport(supported=False, reason="docling package is not installed")
        return ParserBackendSupport(supported=True, confidence=0.85, reason="docling available")

    def convert(self, source: ParserSource, config: ParserConfig) -> MarkdownDocument:
        self.logger.handle(
            parser_log_event(
                "DoclingImpl",
                "开始转换 Markdown source=%s kind=%s",
                source.source_path,
                source.kind,
            )
        )
        try:
            module = importlib.import_module("docling.document_converter")
            base_models = importlib.import_module("docling.datamodel.base_models")
            pipeline_options_module = importlib.import_module("docling.datamodel.pipeline_options")
        except Exception as exc:
            raise DocumentLoadError(f"Docling 依赖不可用：{exc}") from exc

        converter_cls = getattr(module, "DocumentConverter", None)
        pdf_format_option_cls = getattr(module, "PdfFormatOption", None)
        input_format_cls = getattr(base_models, "InputFormat", None)
        pdf_pipeline_options_cls = getattr(pipeline_options_module, "PdfPipelineOptions", None)
        rapid_ocr_options_cls = getattr(pipeline_options_module, "RapidOcrOptions", None)
        if converter_cls is None:
            raise DocumentLoadError("Docling 未找到 DocumentConverter 入口。")
        if (
            pdf_format_option_cls is None
            or input_format_cls is None
            or pdf_pipeline_options_cls is None
            or rapid_ocr_options_cls is None
        ):
            raise DocumentLoadError("Docling 未找到 PDF/RapidOCR 配置入口。")

        pipeline_options = pdf_pipeline_options_cls(
            do_ocr=config.docling_enable_ocr,
            ocr_options=rapid_ocr_options_cls(
                lang=config.docling_ocr_lang,
                force_full_page_ocr=config.docling_force_full_page_ocr,
                bitmap_area_threshold=config.docling_bitmap_area_threshold,
                text_score=config.docling_text_score,
            ),
            do_table_structure=config.docling_do_table_structure,
            ocr_batch_size=1,
            layout_batch_size=1,
            table_batch_size=1,
        )
        format_options = {
            input_format_cls.PDF: pdf_format_option_cls(pipeline_options=pipeline_options)
        }
        converter = converter_cls(format_options=format_options)

        with local_parser_source(source) as input_path:
            result = converter.convert(input_path)

        status = _docling_status_value(getattr(result, "status", None))
        errors = _docling_error_messages(getattr(result, "errors", None))
        document_obj = getattr(result, "document", None)
        if document_obj is None:
            raise DocumentLoadError("Docling 未返回 document。")
        export_to_markdown = getattr(document_obj, "export_to_markdown", None)
        if export_to_markdown is None:
            raise DocumentLoadError("Docling document 不支持 export_to_markdown。")

        markdown = str(export_to_markdown(compact_tables=config.docling_compact_tables))
        if not markdown.strip():
            raise DocumentLoadError("Docling 未返回可解析内容。")
        if status == "failure":
            raise DocumentLoadError("Docling conversion failed: " + ("; ".join(errors) or status))
        if status == "partial_success" and errors:
            raise DocumentLoadError(
                "Docling conversion only partially succeeded: " + "; ".join(errors)
            )
        self.logger.handle(
            parser_log_event(
                "DoclingImpl",
                "markdown 导出完成 chars=%s",
                len(markdown),
            )
        )

        return MarkdownDocument(
            markdown_content=markdown,
            file_name=source.file_name,
            file_type=source.file_type,
            source_path=source.source_path,
            backend_name=self.name,
            html_content=_export_html(document_obj),
            conversion_metadata={
                "parser_backend": self.name,
                "source_kind": source.kind,
                "docling_status": status,
                "docling_errors": errors,
                "docling_table_count": len(getattr(document_obj, "tables", None) or []),
                "docling_tables": _extract_docling_tables(document_obj),
                "docling_ocr_engine": "rapidocr",
                "docling_ocr_lang": list(config.docling_ocr_lang),
                "docling_force_full_page_ocr": config.docling_force_full_page_ocr,
                "docling_bitmap_area_threshold": config.docling_bitmap_area_threshold,
                "docling_text_score": config.docling_text_score,
                "docling_do_table_structure": config.docling_do_table_structure,
                "docling_compact_tables": config.docling_compact_tables,
            },
        )

    parse = convert


def _docling_status_value(status: object) -> str:
    raw = getattr(status, "value", status)
    return str(raw) if raw is not None else "unknown"


def _docling_error_messages(errors: object) -> list[str]:
    if not errors:
        return []
    if not isinstance(errors, list):
        errors = [errors]
    messages: list[str] = []
    for error in errors:
        message = getattr(error, "error_message", None) or str(error)
        message = str(message).strip()
        if message:
            messages.append(message)
    return messages


def _export_html(document_obj: object) -> str:
    export_to_html = getattr(document_obj, "export_to_html", None)
    if export_to_html is None:
        return ""
    try:
        return str(export_to_html()).strip()
    except Exception:
        return ""


def _extract_docling_tables(document_obj: object) -> list[dict[str, object]]:
    tables = getattr(document_obj, "tables", None) or []
    pages = getattr(document_obj, "pages", None) or {}
    result: list[dict[str, object]] = []
    for index, table in enumerate(tables):
        table_layout = _extract_docling_table_layout(index, table, pages)
        if table_layout:
            result.append(table_layout)
    return result


def _extract_docling_table_layout(
    index: int,
    table: object,
    pages: object,
) -> dict[str, object] | None:
    provenance = _first_provenance(table)
    if provenance is None:
        return None
    page_no = getattr(provenance, "page_no", None)
    bbox = getattr(provenance, "bbox", None)
    if page_no is None or bbox is None:
        return None
    normalized_bbox = _normalize_bbox(bbox, _page_size(pages, int(page_no)))
    if normalized_bbox is None:
        return None
    return {
        "index": index,
        "page": int(page_no),
        "bbox": normalized_bbox,
    }


def _first_provenance(table: object) -> object | None:
    provenance = getattr(table, "prov", None) or []
    if not provenance:
        return None
    return provenance[0]


def _page_size(pages: object, page_no: int) -> tuple[float, float] | None:
    page = None
    if isinstance(pages, dict):
        page = pages.get(page_no)
    else:
        page = getattr(pages, str(page_no), None)
    if page is None:
        return None
    size = getattr(page, "size", None)
    if size is None:
        return None
    width = float(getattr(size, "width", 0) or 0)
    height = float(getattr(size, "height", 0) or 0)
    if width <= 0 or height <= 0:
        return None
    return width, height


def _normalize_bbox(
    bbox: object,
    page_size: tuple[float, float] | None,
) -> dict[str, float] | None:
    left = _float_attr(bbox, "l")
    top = _float_attr(bbox, "t")
    right = _float_attr(bbox, "r")
    bottom = _float_attr(bbox, "b")
    if left is None or top is None or right is None or bottom is None:
        return None
    if page_size is not None:
        width, height = page_size
        left = left / width
        right = right / width
        top = top / height
        bottom = bottom / height
    return {
        "left": _clamp_unit(min(left, right)),
        "top": _clamp_unit(min(top, bottom)),
        "right": _clamp_unit(max(left, right)),
        "bottom": _clamp_unit(max(top, bottom)),
    }


def _float_attr(value: object, name: str) -> float | None:
    raw = getattr(value, name, None)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _clamp_unit(value: float) -> float:
    return max(0.0, min(1.0, value))
