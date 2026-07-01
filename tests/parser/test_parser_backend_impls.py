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
    def test_docling_supports_configured_structured_suffixes(self):
        backend = DoclingParserImpl()
        config = ParserConfig(docling_enabled=True)

        with patch("importlib.util.find_spec", return_value=_module_spec("docling")):
            supports = {
                suffix: backend.supports(
                    ParserSource.from_bytes(f"contract{suffix}", b"fake"), config
                )
                for suffix in (
                    ".pdf",
                    ".docx",
                    ".md",
                    ".markdown",
                    ".html",
                    ".htm",
                    ".csv",
                    ".xlsx",
                    ".txt",
                )
            }
            text_support = backend.supports(ParserSource.from_text("body"), config)

        self.assertTrue(supports[".pdf"].supported)
        self.assertFalse(supports[".pdf"].can_fallback)
        for suffix in (".docx", ".md", ".markdown", ".html", ".htm", ".csv", ".xlsx"):
            with self.subTest(suffix=suffix):
                self.assertTrue(supports[suffix].supported)
                self.assertTrue(supports[suffix].can_fallback)
        for suffix in (".txt",):
            with self.subTest(suffix=suffix):
                self.assertFalse(supports[suffix].supported)
                self.assertTrue(supports[suffix].can_fallback)
        self.assertFalse(text_support.supported)
        self.assertTrue(text_support.can_fallback)

    def test_docling_support_normalizes_dotted_file_type(self):
        backend = DoclingParserImpl()
        config = ParserConfig(docling_enabled=True)
        source = ParserSource.from_bytes("contract.pdf", b"fake")
        source.file_type = " .PDF "

        with patch("importlib.util.find_spec", return_value=_module_spec("docling")):
            support = backend.supports(source, config)

        self.assertTrue(support.supported)

    def test_docling_support_respects_allowed_suffix_intersection(self):
        backend = DoclingParserImpl()
        config = ParserConfig(
            docling_enabled=True,
            allowed_suffixes=[".pdf"],
            docling_supported_suffixes=[".pdf", ".docx"],
        )

        with patch("importlib.util.find_spec", return_value=_module_spec("docling")):
            support = backend.supports(ParserSource.from_bytes("contract.docx", b"fake"), config)

        self.assertFalse(support.supported)
        self.assertTrue(support.can_fallback)

    def test_docling_sources_can_fallback_when_dependency_missing_except_pdf(self):
        backend = DoclingParserImpl()
        config = ParserConfig(docling_enabled=True)

        with patch("importlib.util.find_spec", return_value=None):
            pdf_support = backend.supports(ParserSource.from_bytes("contract.pdf", b"fake"), config)
            text_support = backend.supports(ParserSource.from_text("body"), config)
            docx_support = backend.supports(
                ParserSource.from_bytes("contract.docx", b"fake"), config
            )

        self.assertFalse(pdf_support.supported)
        self.assertFalse(pdf_support.can_fallback)
        self.assertFalse(text_support.supported)
        self.assertTrue(text_support.can_fallback)
        self.assertFalse(docx_support.supported)
        self.assertTrue(docx_support.can_fallback)

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

        result = _run_docling_fake(
            FakeDocumentConverter,
            ParserConfig(
                docling_enabled=True,
                docling_enable_ocr=True,
                docling_ocr_lang=["chinese"],
                docling_force_full_page_ocr=True,
                docling_bitmap_area_threshold=0.02,
                docling_text_score=0.35,
                docling_do_table_structure=True,
                docling_compact_tables=True,
            ),
        )

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
        self.assertIn("allowed_formats", converter_kwargs[0])
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

    def test_docling_convertor_uses_allowed_formats_for_non_pdf_without_pdf_pipeline(self):
        converter_kwargs: list[dict] = []
        markdown = "# DOCX\n\nBody\n\n"

        class FakeDoclingDocument:
            pages = {}
            tables = []

            def export_to_markdown(self, **kwargs: object) -> str:
                return markdown

        class FakeBackendResult:
            document = FakeDoclingDocument()

        class FakeDocumentConverter:
            def __init__(self, **kwargs: object) -> None:
                converter_kwargs.append(kwargs)

            def convert(self, source: str) -> FakeBackendResult:
                self.source = source
                return FakeBackendResult()

        result = _run_docling_fake(
            FakeDocumentConverter,
            ParserConfig(docling_enabled=True),
            file_name="project.docx",
        )

        self.assertEqual(result.markdown_content, markdown)
        self.assertEqual(result.conversion_metadata["docling_input_format"], "DOCX")
        self.assertEqual(
            result.conversion_metadata["docling_supported_suffixes"],
            [".pdf", ".docx", ".md", ".markdown", ".html", ".htm", ".csv", ".xlsx"],
        )
        self.assertTrue(converter_kwargs)
        kwargs = converter_kwargs[0]
        self.assertIn("allowed_formats", kwargs)
        self.assertIn("format_options", kwargs)
        self.assertEqual(
            [fmt.name for fmt in kwargs["allowed_formats"]],
            ["PDF", "DOCX", "MD", "HTML", "CSV", "XLSX"],
        )
        self.assertEqual([fmt.name for fmt in kwargs["format_options"]], ["PDF"])

    def test_docling_convertor_allows_non_pdf_when_pdf_options_are_unavailable(self):
        converter_kwargs: list[dict] = []
        markdown = "# DOCX\n\nBody\n\n"

        class FakeDoclingDocument:
            pages = {}
            tables = []

            def export_to_markdown(self, **kwargs: object) -> str:
                return markdown

        class FakeBackendResult:
            document = FakeDoclingDocument()

        class FakeDocumentConverter:
            def __init__(self, **kwargs: object) -> None:
                converter_kwargs.append(kwargs)

            def convert(self, source: str) -> FakeBackendResult:
                self.source = source
                return FakeBackendResult()

        result = _run_docling_fake(
            FakeDocumentConverter,
            ParserConfig(
                docling_enabled=True,
                allowed_suffixes=[".docx"],
                docling_supported_suffixes=[".docx"],
            ),
            file_name="project.docx",
            include_pdf_options=False,
            fail_pipeline_options_import=True,
        )

        self.assertEqual(result.markdown_content, markdown)
        self.assertEqual(result.conversion_metadata["docling_input_format"], "DOCX")
        self.assertTrue(converter_kwargs)
        self.assertEqual([fmt.name for fmt in converter_kwargs[0]["allowed_formats"]], ["DOCX"])
        self.assertEqual(converter_kwargs[0]["format_options"], {})

    def test_docling_convertor_maps_text_structured_suffixes_to_input_format_metadata(self):
        class FakeDoclingDocument:
            pages = {}
            tables = []

            def export_to_markdown(self, **kwargs: object) -> str:
                return "# Structured\n\nBody"

        class FakeBackendResult:
            document = FakeDoclingDocument()

        class FakeDocumentConverter:
            def __init__(self, **kwargs: object) -> None:
                pass

            def convert(self, source: str) -> FakeBackendResult:
                return FakeBackendResult()

        cases = {
            "project.md": "MD",
            "project.markdown": "MD",
            "project.html": "HTML",
            "project.htm": "HTML",
            "project.csv": "CSV",
            "project.xlsx": "XLSX",
        }
        for file_name, expected in cases.items():
            with self.subTest(file_name=file_name):
                result = _run_docling_fake(
                    FakeDocumentConverter,
                    ParserConfig(docling_enabled=True),
                    file_name=file_name,
                )

                self.assertEqual(result.conversion_metadata["docling_input_format"], expected)

    def test_docling_convertor_rejects_sources_blocked_by_parser_policy(self):
        class FakeDoclingDocument:
            pages = {}
            tables = []

            def export_to_markdown(self, **kwargs: object) -> str:
                return "# Structured\n\nBody"

        class FakeBackendResult:
            document = FakeDoclingDocument()

        class FakeDocumentConverter:
            def __init__(self, **kwargs: object) -> None:
                pass

            def convert(self, source: str) -> FakeBackendResult:
                return FakeBackendResult()

        cases = [
            (
                ParserSource.from_text("body", file_name="inline.md"),
                ParserConfig(docling_enabled=True),
                "inline text input",
            ),
            (
                ParserSource.from_bytes("contract", b"fake"),
                ParserConfig(docling_enabled=True),
                "requires a file suffix",
            ),
            (
                ParserSource.from_bytes("contract.docx", b"fake"),
                ParserConfig(
                    docling_enabled=True,
                    allowed_suffixes=[".pdf"],
                    docling_supported_suffixes=[".pdf", ".docx"],
                ),
                "parser.allowed_suffixes",
            ),
            (
                ParserSource.from_bytes("contract.docx", b"fake"),
                ParserConfig(
                    docling_enabled=True,
                    allowed_suffixes=[".pdf", ".docx"],
                    docling_supported_suffixes=[".pdf"],
                ),
                "not configured as supported",
            ),
        ]
        for source, config, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(DocumentLoadError, message):
                    _run_docling_fake(
                        FakeDocumentConverter,
                        config,
                        source=source,
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
            value = (
                '<p>ok</p><script>alert("x")</script>'
                '<img src="x" onerror="bad">'
                '<a href="javascript:alert(1)">bad</a>'
                '<a href="jav&#x61;script:alert(2)">encoded</a>'
                '<svg><a href="https://safe.example">bad</a></svg>'
                '<math><mi onclick="bad">x</mi></math>'
                '<iframe src="https://evil.example"></iframe>'
                '<object data="https://evil.example"></object>'
                '<embed src="https://evil.example">hidden</embed>'
                "</p><span/>"
                '<p>safe <a href="https://example.com" title="ok">link</a></p>'
            )

        def fake_convert_to_html(stream: BytesIO) -> FakeMammothResult:
            return FakeMammothResult()

        module = types.ModuleType("mammoth")
        module.convert_to_html = fake_convert_to_html

        with patch.dict(sys.modules, {"mammoth": module}):
            html = builtin_converter._docx_to_html(b"fake")  # noqa: SLF001

        self.assertIn("<p>ok</p>", html)
        self.assertIn('<img src="x">', html)
        self.assertIn("<a>bad</a>", html)
        self.assertIn("<a>encoded</a>", html)
        self.assertIn("<span></span>", html)
        self.assertIn(
            '<p>safe <a href="https://example.com" title="ok">link</a></p>',
            html,
        )
        self.assertNotIn("<script", html)
        self.assertNotIn("onerror", html)
        self.assertNotIn("javascript:", html)
        self.assertNotIn("<svg", html)
        self.assertNotIn("<math", html)
        self.assertNotIn("<iframe", html)
        self.assertNotIn("<object", html)
        self.assertNotIn("<embed", html)


def _run_docling_fake(
    document_converter_cls: type,
    parser_config: ParserConfig | None = None,
    *,
    file_name: str = "project.pdf",
    source: ParserSource | None = None,
    include_pdf_options: bool = True,
    fail_pipeline_options_import: bool = False,
) -> object:
    package = types.ModuleType("docling")
    module = types.ModuleType("docling.document_converter")
    base_models = types.ModuleType("docling.datamodel.base_models")
    pipeline_options = types.ModuleType("docling.datamodel.pipeline_options")

    class FakeInputFormatValue:
        def __init__(self, name: str) -> None:
            self.name = name
            self.value = name.lower()

        def __repr__(self) -> str:
            return f"InputFormat.{self.name}"

    class FakeInputFormat:
        PDF = FakeInputFormatValue("PDF")
        DOCX = FakeInputFormatValue("DOCX")
        MD = FakeInputFormatValue("MD")
        HTML = FakeInputFormatValue("HTML")
        CSV = FakeInputFormatValue("CSV")
        XLSX = FakeInputFormatValue("XLSX")

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
    if include_pdf_options:
        module.PdfFormatOption = FakePdfFormatOption
    base_models.InputFormat = FakeInputFormat
    if include_pdf_options:
        pipeline_options.PdfPipelineOptions = FakePdfPipelineOptions
        pipeline_options.RapidOcrOptions = RapidOcrOptions

    original_import_module = importlib.import_module

    def fake_import_module(name: str) -> object:
        if fail_pipeline_options_import and name == "docling.datamodel.pipeline_options":
            raise ImportError(name)
        return original_import_module(name)

    if source is not None:
        with patch.dict(
            sys.modules,
            {
                "docling": package,
                "docling.document_converter": module,
                "docling.datamodel.base_models": base_models,
                "docling.datamodel.pipeline_options": pipeline_options,
            },
        ):
            with (
                patch("importlib.import_module", side_effect=fake_import_module),
                patch("importlib.util.find_spec", return_value=_module_spec("docling")),
            ):
                return DoclingParserImpl().convert(
                    source,
                    parser_config or ParserConfig(docling_enabled=True),
                )

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / file_name
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
            with (
                patch("importlib.import_module", side_effect=fake_import_module),
                patch("importlib.util.find_spec", return_value=_module_spec("docling")),
            ):
                return DoclingParserImpl().convert(
                    ParserSource.from_path(path),
                    parser_config or ParserConfig(docling_enabled=True),
                )


def _module_spec(name: str) -> importlib.machinery.ModuleSpec:
    return importlib.machinery.ModuleSpec(name, loader=None)


if __name__ == "__main__":
    unittest.main()
