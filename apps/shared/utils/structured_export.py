"""Shared helpers for tabular exports (CSV and future formats)."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator, Sequence
from typing import Any

_CSV_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def sanitize_csv_cell(value: Any) -> Any:
    """Prefix spreadsheet formula trigger characters so Excel/Sheets will not evaluate the cell."""
    if not isinstance(value, str) or not value:
        return value
    if value[0] in _CSV_FORMULA_PREFIXES:
        return "'" + value
    return value


class CsvTableExporter:
    """Buffered CSV writer that can flush UTF-8 byte chunks for streaming responses."""

    def __init__(self, *, encoding: str = "utf-8") -> None:
        self._encoding = encoding
        self._buffer = io.StringIO()
        self._writer = csv.writer(self._buffer, lineterminator="\n")

    def write_header(self, headers: Sequence[str]) -> None:
        self._writer.writerow(headers)

    def append_row(self, cells: Sequence[Any]) -> None:
        self._writer.writerow(sanitize_csv_cell(cell) for cell in cells)

    def flush_chunk(self) -> bytes | None:
        """Encode accumulated rows and clear the internal text buffer."""
        text = self._buffer.getvalue()
        if not text:
            return None
        encoded = text.encode(self._encoding)
        self._buffer.seek(0)
        self._buffer.truncate(0)
        return encoded

    def iter_byte_chunks(self) -> Iterator[bytes]:
        """Yield a single chunk from any remaining buffered rows (e.g. final partial page)."""
        chunk = self.flush_chunk()
        if chunk:
            yield chunk

    def materialize(self) -> bytes:
        """Return the full export as bytes (for tests and small in-memory use)."""
        return b"".join(self.iter_byte_chunks())
