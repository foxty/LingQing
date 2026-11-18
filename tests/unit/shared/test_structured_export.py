"""Tests for structured export utilities."""

import csv
import io

from apps.shared.utils.structured_export import CsvTableExporter, sanitize_csv_cell


def test_csv_table_exporter_materialize_round_trip():
    exporter = CsvTableExporter()
    exporter.write_header(["a", "b"])
    exporter.append_row([1, "x"])
    data = exporter.materialize()
    parsed = list(csv.reader(io.StringIO(data.decode())))
    assert parsed == [["a", "b"], ["1", "x"]]


def test_csv_table_exporter_flush_chunk_clears_buffer():
    exporter = CsvTableExporter()
    exporter.write_header(["h"])
    first = exporter.flush_chunk()
    assert first is not None
    assert exporter.flush_chunk() is None

    exporter.append_row(["r"])
    second = exporter.flush_chunk()
    assert second == b"r\n"


def test_sanitize_csv_cell_prefixes_formula_triggers():
    assert sanitize_csv_cell("=cmd|'/c calc'!A0") == "'=cmd|'/c calc'!A0"
    assert sanitize_csv_cell("+123") == "'+123"
    assert sanitize_csv_cell("normal") == "normal"


def test_csv_exporter_escapes_formula_cells_in_output():
    exporter = CsvTableExporter()
    exporter.write_header(["user_agent"])
    exporter.append_row(["=HYPERLINK(\"http://evil/\",\"click\")"])
    rows = list(csv.reader(io.StringIO(exporter.materialize().decode())))
    assert rows[1][0].startswith("'=")
