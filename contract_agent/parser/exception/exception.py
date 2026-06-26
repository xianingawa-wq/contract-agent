class ParserError(Exception):
    """Base exception for parser package errors."""


class UnsupportedFileType(ParserError):
    """Raised when a file suffix is not supported by the parser."""


class DocumentLoadError(ParserError):
    """Raised when input content cannot be loaded or decoded."""


class DocumentParseError(ParserError):
    """Raised when loaded content cannot form a valid parsed document."""


class ReviewInputError(ParserError):
    """Raised when review input cannot be normalized."""
