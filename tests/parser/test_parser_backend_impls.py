import importlib.machinery
import sys
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.exception import DocumentLoadError
from contract_agent.parser.convertor import builtin_markdown_converter as builtin_converter
from contract_agent.parser.convertor.docling_parser_impl import DoclingParserImpl
from contract_agent.parser.convertor.markitdown_parser_impl import MarkitdownParserImpl
from contract_agent.parser.parser_source import ParserSource


class ParserBackendImplTests(unittest.TestCase):
    def test_docling_supports_only_pdf_sources(self):
        backend = DoclingParserImpl()
        config = ParserConfig(docling_enabled=True)

        with patch("importlib.util.find_spec", return_value=_module_spec("docling")):
            pdf_support = backend.supports(ParserSource.from_bytes("contract.pdf", b"fake"), config)
            text_support = backend.supports(ParserSource.from_text("body"), config)
            docx_support = backend.supports(
                ParserSource.from_bytes("contract.docx", b"fake"), config
            )

        self.assertTrue(pdf_support.supported)
        self.assertFalse(text_support.supported)
        self.assertFalse(docx_support.supported)

    def test_docling_convertor_returns_exact_backend_markdown(self):
        calls: list[str] = []
        converter_kwargs: list[dict] = []
        markdown = "# Docling Project\n\nStructured body\n\n"

        class FakeBBox:
            coord_origin = "TOPLEFT"

            def __init__(
                self,
                *,
                top: float,
                bottom: float,
                left: float = 0,
                right: float = 100,
            ) -> None:
                self.l = left
                self.t = top
                self.r = right
                self.b = bottom

        class FakeProvenance:
            def __init__(
                self,
                *,
                page_no: int,
                top: float,
                bottom: float,
                left: float = 0,
                right: float = 100,
            ) -> None:
                self.page_no = page_no
                self.bbox = FakeBBox(top=top, bottom=bottom, left=left, right=right)

        class FakePageSize:
            width = 100
            height = 100

        class FakePage:
            size = FakePageSize()

        class FakeTable:
            def __init__(
                self,
                *,
                page_no: int,
                top: float,
                bottom: float,
                left: float = 0,
                right: float = 100,
            ) -> None:
                self.prov = [
                    FakeProvenance(
                        page_no=page_no,
                        top=top,
                        bottom=bottom,
                        left=left,
                        right=right,
                    )
                ]

        class FakeDoclingDocument:
            pages = {1: FakePage(), 2: FakePage()}
            tables = [
                FakeTable(page_no=1, top=80, bottom=96),
                FakeTable(page_no=2, top=3, bottom=20, left=90, right=10),
            ]

            def export_to_markdown(self, **kwargs: object) -> str:
                calls.append(f"export:{kwargs}")
                return markdown

            def export_to_html(self) -> str:
                return "<h1>Docling Project</h1>"

        class FakeBackendResult:
            document = FakeDoclingDocument()

        class FakeDocumentConverter:
            def __init__(self, **kwargs: object) -> None:
                converter_kwargs.append(kwargs)

            def convert(self, source: str) -> FakeBackendResult:
                calls.append(source)
                return FakeBackendResult()

        result = _run_docling_fake(FakeDocumentConverter)

        self.assertEqual(result.backend_name, "docling")
        self.assertEqual(result.markdown_content, markdown)
        self.assertEqual(result.html_content, "<h1>Docling Project</h1>")
        self.assertEqual(len([call for call in calls if not call.startswith("export:")]), 1)
        self.assertIn("project.pdf", calls[0])
        self.assertEqual(result.conversion_metadata["parser_backend"], "docling")
        self.assertEqual(result.conversion_metadata["docling_ocr_engine"], "rapidocr")
        self.assertEqual(result.conversion_metadata["docling_ocr_lang"], ["chinese"])
        self.assertEqual(result.conversion_metadata["docling_compact_tables"], True)
        self.assertTrue(result.conversion_metadata["docling_force_full_page_ocr"])
        self.assertEqual(result.conversion_metadata["docling_bitmap_area_threshold"], 0.02)
        self.assertEqual(result.conversion_metadata["docling_text_score"], 0.35)
        self.assertEqual(
            result.conversion_metadata["docling_tables"],
            [
                {
                    "index": 0,
                    "page": 1,
                    "bbox": {"left": 0.0, "top": 0.8, "right": 1.0, "bottom": 0.96},
                },
                {
                    "index": 1,
                    "page": 2,
                    "bbox": {"left": 0.1, "top": 0.03, "right": 0.9, "bottom": 0.2},
                },
            ],
        )
        self.assertTrue(converter_kwargs)
        format_options = converter_kwargs[0]["format_options"]
        pdf_option = next(iter(format_options.values()))
        pipeline_options = pdf_option.pipeline_options
        self.assertTrue(pipeline_options.do_ocr)
        self.assertEqual(type(pipeline_options.ocr_options).__name__, "RapidOcrOptions")
        self.assertEqual(pipeline_options.ocr_options.lang, ["chinese"])
        self.assertTrue(pipeline_options.ocr_options.force_full_page_ocr)
        self.assertEqual(pipeline_options.ocr_options.bitmap_area_threshold, 0.02)
        self.assertEqual(pipeline_options.ocr_options.text_score, 0.35)
        self.assertEqual(pipeline_options.ocr_batch_size, 1)
        self.assertEqual(pipeline_options.layout_batch_size, 1)
        self.assertEqual(pipeline_options.table_batch_size, 1)
        self.assertTrue(
            any(
                call == "export:{'compact_tables': True}"
                for call in calls
                if call.startswith("export:")
            )
        )

    def test_docling_convertor_rejects_tiny_partial_success_output(self):
        class FakeDoclingDocument:
            pages = {}
            tables = []

            def export_to_markdown(self, **kwargs: object) -> str:
                return "# Title"

        class FakeError:
            error_message = "OCR bad allocation"

        class FakeStatus:
            value = "partial_success"

        class FakeBackendResult:
            document = FakeDoclingDocument()
            status = FakeStatus()
            errors = [FakeError()]

        class FakeDocumentConverter:
            def __init__(self, **kwargs: object) -> None:
                pass

            def convert(self, source: str) -> FakeBackendResult:
                return FakeBackendResult()

        with self.assertRaisesRegex(DocumentLoadError, "Docling"):
            _run_docling_fake(FakeDocumentConverter)

    def test_docling_convertor_rejects_failure_even_with_long_markdown(self):
        class FakeDoclingDocument:
            pages = {}
            tables = []

            def export_to_markdown(self, **kwargs: object) -> str:
                return "Long partial output. " * 20

        class FakeError:
            error_message = "conversion failed"

        class FakeStatus:
            value = "failure"

        class FakeBackendResult:
            document = FakeDoclingDocument()
            status = FakeStatus()
            errors = [FakeError()]

        class FakeDocumentConverter:
            def __init__(self, **kwargs: object) -> None:
                pass

            def convert(self, source: str) -> FakeBackendResult:
                return FakeBackendResult()

        with self.assertRaisesRegex(DocumentLoadError, "Docling conversion failed"):
            _run_docling_fake(FakeDocumentConverter)

    def test_markitdown_convertor_returns_exact_backend_markdown(self):
        calls: list[str] = []
        markdown = "# Project\n\n| Key | Value |\n| --- | --- |\n"

        class FakeResult:
            text_content = markdown

        class FakeMarkItDown:
            def convert(self, source: str) -> FakeResult:
                calls.append(source)
                return FakeResult()

        module = types.ModuleType("markitdown")
        module.MarkItDown = FakeMarkItDown

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.docx"
            path.write_bytes(b"fake")
            with patch.dict(sys.modules, {"markitdown": module}):
                with patch("importlib.util.find_spec", return_value=_module_spec("markitdown")):
                    result = MarkitdownParserImpl().convert(
                        ParserSource.from_path(path),
                        ParserConfig(markitdown_enabled=True),
                    )

        self.assertEqual(result.backend_name, "markitdown")
        self.assertEqual(calls, [str(path.resolve())])
        self.assertEqual(result.markdown_content, markdown)
        self.assertEqual(result.conversion_metadata["parser_backend"], "markitdown")

    def test_markitdown_convertor_wraps_conversion_failures(self):
        class FakeMarkItDown:
            def convert(self, source: str) -> object:
                raise RuntimeError("third-party failure")

        module = types.ModuleType("markitdown")
        module.MarkItDown = FakeMarkItDown

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.docx"
            path.write_bytes(b"fake")
            with patch.dict(sys.modules, {"markitdown": module}):
                with patch("importlib.util.find_spec", return_value=_module_spec("markitdown")):
                    with self.assertRaisesRegex(DocumentLoadError, "MarkItDown backend"):
                        MarkitdownParserImpl().convert(
                            ParserSource.from_path(path),
                            ParserConfig(markitdown_enabled=True),
                        )

    def test_markitdown_convertor_rejects_unexpected_result_objects(self):
        class FakeMarkItDown:
            def convert(self, source: str) -> object:
                return object()

        module = types.ModuleType("markitdown")
        module.MarkItDown = FakeMarkItDown

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.docx"
            path.write_bytes(b"fake")
            with patch.dict(sys.modules, {"markitdown": module}):
                with patch("importlib.util.find_spec", return_value=_module_spec("markitdown")):
                    with self.assertRaisesRegex(DocumentLoadError, "unexpected result"):
                        MarkitdownParserImpl().convert(
                            ParserSource.from_path(path),
                            ParserConfig(markitdown_enabled=True),
                        )

    def test_docx_html_output_is_sanitized_before_exposure(self):
        class FakeMammothResult:
            value = '<p>ok</p><script>alert("x")</script><img src="x" onerror="bad">'

        def fake_convert_to_html(stream: BytesIO) -> FakeMammothResult:
            return FakeMammothResult()

        module = types.ModuleType("mammoth")
        module.convert_to_html = fake_convert_to_html

        with patch.dict(sys.modules, {"mammoth": module}):
            html = builtin_converter._docx_to_html(b"fake")  # noqa: SLF001

        self.assertEqual(html, '<p>ok</p><img src="x">')


def _run_docling_fake(document_converter_cls: type) -> object:
    package = types.ModuleType("docling")
    module = types.ModuleType("docling.document_converter")
    base_models = types.ModuleType("docling.datamodel.base_models")
    pipeline_options = types.ModuleType("docling.datamodel.pipeline_options")

    class FakeInputFormat:
        PDF = "pdf"

    class RapidOcrOptions:
        def __init__(
            self,
            *,
            lang: list[str],
            force_full_page_ocr: bool,
            bitmap_area_threshold: float,
            text_score: float,
        ) -> None:
            self.lang = lang
            self.force_full_page_ocr = force_full_page_ocr
            self.bitmap_area_threshold = bitmap_area_threshold
            self.text_score = text_score

    class FakePdfPipelineOptions:
        def __init__(
            self,
            *,
            do_ocr: bool,
            ocr_options: RapidOcrOptions,
            do_table_structure: bool,
            ocr_batch_size: int,
            layout_batch_size: int,
            table_batch_size: int,
        ) -> None:
            self.do_ocr = do_ocr
            self.ocr_options = ocr_options
            self.do_table_structure = do_table_structure
            self.ocr_batch_size = ocr_batch_size
            self.layout_batch_size = layout_batch_size
            self.table_batch_size = table_batch_size

    class FakePdfFormatOption:
        def __init__(self, *, pipeline_options: FakePdfPipelineOptions) -> None:
            self.pipeline_options = pipeline_options

    module.DocumentConverter = document_converter_cls
    module.PdfFormatOption = FakePdfFormatOption
    base_models.InputFormat = FakeInputFormat
    pipeline_options.PdfPipelineOptions = FakePdfPipelineOptions
    pipeline_options.RapidOcrOptions = RapidOcrOptions

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "project.pdf"
        path.write_bytes(b"fake")
        with patch.dict(
            sys.modules,
            {
                "docling": package,
                "docling.document_converter": module,
                "docling.datamodel.base_models": base_models,
                "docling.datamodel.pipeline_options": pipeline_options,
            },
        ):
            with patch("importlib.util.find_spec", return_value=_module_spec("docling")):
                return DoclingParserImpl().convert(
                    ParserSource.from_path(path),
                    ParserConfig(docling_enabled=True),
                )


def _module_spec(name: str) -> importlib.machinery.ModuleSpec:
    return importlib.machinery.ModuleSpec(name, loader=None)


if __name__ == "__main__":
    unittest.main()
