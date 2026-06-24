import importlib.machinery
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from contract_agent.config.config_parser import ParserConfig
from contract_agent.parser.converters.base import ParseSource
from contract_agent.parser.converters.docling import DoclingConverter
from contract_agent.parser.converters.markitdown import MarkItDownConverter


class ConverterAdapterTests(unittest.TestCase):
    def test_markitdown_converter_calls_lazy_api_and_returns_markdown_document(self):
        calls: list[str] = []

        class FakeResult:
            text_content = (
                "# Project\n\n| Key | Value |\n| --- | --- |\n| Project Name | Contract Review |"
            )

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
                    result = MarkItDownConverter().convert(
                        ParseSource.from_path(path),
                        ParserConfig(markitdown_enabled=True),
                    )

        self.assertEqual(result.converter_name, "markitdown")
        self.assertEqual(calls, [str(path.resolve())])
        self.assertIn("Project Name", result.document.raw_text)
        self.assertIn("| Project Name | Contract Review |", result.document.markdown_content)
        self.assertEqual(result.metadata["converter"], "markitdown")

    def test_docling_converter_calls_lazy_api_and_returns_markdown_document(self):
        calls: list[str] = []

        class FakeDoclingDocument:
            def export_to_markdown(self) -> str:
                return "# Docling Project\n\nStructured body"

        class FakeConversionResult:
            document = FakeDoclingDocument()

        class FakeDocumentConverter:
            def convert(self, source: str) -> FakeConversionResult:
                calls.append(source)
                return FakeConversionResult()

        package = types.ModuleType("docling")
        module = types.ModuleType("docling.document_converter")
        module.DocumentConverter = FakeDocumentConverter

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "project.pdf"
            path.write_bytes(b"fake")
            with patch.dict(
                sys.modules,
                {"docling": package, "docling.document_converter": module},
            ):
                with patch("importlib.util.find_spec", return_value=_module_spec("docling")):
                    result = DoclingConverter().convert(
                        ParseSource.from_path(path),
                        ParserConfig(docling_enabled=True),
                    )

        self.assertEqual(result.converter_name, "docling")
        self.assertEqual(calls, [str(path.resolve())])
        self.assertIn("Docling Project", result.document.raw_text)
        self.assertEqual(result.document.markdown_content, "# Docling Project\n\nStructured body")
        self.assertEqual(result.metadata["converter"], "docling")


def _module_spec(name: str) -> importlib.machinery.ModuleSpec:
    return importlib.machinery.ModuleSpec(name, loader=None)


if __name__ == "__main__":
    unittest.main()
