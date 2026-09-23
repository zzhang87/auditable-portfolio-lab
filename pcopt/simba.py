from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Sequence
from xml.etree import ElementTree as ET

import pandas as pd

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

NS = {
    "m": MAIN_NS,
    "rel": REL_NS,
}


DEFAULT_PORTFOLIO_CHARTS_ASSET_CODES = (
    "DEV-ITT",
    "DEV-LCB",
    "DEV-LCG",
    "DEV-LCV",
    "DEV-SCB",
    "DEV-SCG",
    "DEV-SCV",
    "EMT-LCB",
    "EUR-BIL",
    "EUR-ITT",
    "EUR-LCB",
    "EUR-LCG",
    "EUR-LCV",
    "EUR-LTT",
    "EUR-SCB",
    "EUR-SCG",
    "EUR-SCV",
    "EUR-STT",
    "GLO-COM",
    "GLO-GLD",
    "USA-BIL",
    "USA-ITT",
    "USA-LCB",
    "USA-LCG",
    "USA-LCV",
    "USA-LTT",
    "USA-REI",
    "USA-SCB",
    "USA-SCG",
    "USA-SCV",
    "USA-STT",
    "XUS-ITT",
    "XUS-LCB",
    "XUS-LCG",
    "XUS-LCV",
    "XUS-SCB",
    "XUS-SCG",
    "XUS-SCV",
)


SIMBA_SERIES_MAPPING: dict[str, str] = {
    "DEV-ITT": "Global Bd",
    "EMT-LCB": "Emerging",
    "EUR-LCB": "Europe",
    "GLO-COM": "Commodity Futures",
    "GLO-GLD": "Gold",
    "USA-BIL": "T-Bill",
    "USA-ITT": "ITT",
    "USA-LCB": "LCB",
    "USA-LCG": "LCG",
    "USA-LCV": "LCV",
    "USA-LTT": "LTT",
    "USA-REI": "REIT",
    "USA-SCB": "SCB",
    "USA-SCG": "SCG",
    "USA-SCV": "SCV",
    "USA-STT": "STT",
    "XUS-ITT": "Int'l Bd",
    "XUS-LCB": "Int'l Dev",
    "XUS-LCV": "Int'l Value",
    "XUS-SCB": "Int'l Small",
    "XUS-SCV": "Int'l Small Value",
}


def load_simba_data_series(workbook_path: str | Path, sheet_name: str = "Data_Series") -> pd.DataFrame:
    """Load annual percent returns from Simba's `Data_Series` worksheet.

    The workbook is parsed directly from OOXML cached cell values so no Excel
    engine dependency is required. Returned values are annual percentages, as
    displayed by Simba, and metadata is attached in `df.attrs["series_metadata"]`.
    """

    rows = _read_sheet_rows(Path(workbook_path), sheet_name)
    if 1 not in rows:
        raise ValueError(f"{sheet_name!r} is missing header row 1")

    headers = {col: str(value).strip() for col, value in rows[1].items() if col > 1 and str(value).strip()}
    metadata: dict[str, dict[str, object]] = {}
    for col, name in headers.items():
        metadata[name] = {
            "ticker": _blank_to_none(rows.get(2, {}).get(col)),
            "expense_ratio": _to_optional_float(rows.get(3, {}).get(col)),
            "first_year": _to_optional_int(rows.get(4, {}).get(col)),
            "raw_data_index": _to_optional_int(rows.get(5, {}).get(col)),
        }

    records: dict[int, dict[str, float | None]] = {}
    for row_num, row in rows.items():
        if row_num < 8:
            continue
        year = _to_optional_int(row.get(1))
        if year is None:
            continue
        values: dict[str, float | None] = {}
        for col, name in headers.items():
            values[name] = _to_optional_float(row.get(col))
        records[year] = values

    if not records:
        raise ValueError(f"{sheet_name!r} contains no annual return rows")

    df = pd.DataFrame.from_dict(records, orient="index").sort_index()
    df.index.name = "year"
    df.attrs["series_metadata"] = metadata
    return df


def build_simba_proxy_returns(
    workbook_path: str | Path,
    *,
    asset_codes: Sequence[str] | None = None,
    inflation_series: str = "Inflation US",
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build decimal real returns for mapped Portfolio Charts-style asset codes."""

    series = load_simba_data_series(workbook_path)
    codes = list(asset_codes or DEFAULT_PORTFOLIO_CHARTS_ASSET_CODES)
    if inflation_series not in series.columns:
        raise KeyError(f"Simba inflation series {inflation_series!r} not found")
    inflation = series[inflation_series] / 100.0

    out: dict[str, pd.Series] = {}
    mapped: dict[str, dict[str, object]] = {}
    missing: dict[str, str] = {}
    metadata = series.attrs.get("series_metadata", {})

    for code in codes:
        source_series = SIMBA_SERIES_MAPPING.get(code)
        if source_series is None:
            missing[code] = "no Simba Data_Series mapping configured"
            continue
        if source_series not in series.columns:
            missing[code] = f"Simba Data_Series column {source_series!r} not found"
            continue

        nominal = series[source_series] / 100.0
        real = ((1.0 + nominal) / (1.0 + inflation) - 1.0).dropna()
        real.name = code
        out[code] = real
        mapped[code] = {
            "source_series": source_series,
            "ticker": metadata.get(source_series, {}).get("ticker"),
            "first_year": metadata.get(source_series, {}).get("first_year"),
            "raw_data_index": metadata.get(source_series, {}).get("raw_data_index"),
            "method": "Simba Data_Series annual nominal return deflated by Inflation US.",
        }

    if not out:
        raise ValueError("none of the requested asset codes could be mapped")

    df = pd.DataFrame(out).sort_index()
    coverage = {
        "source_workbook": str(workbook_path),
        "sheet": "Data_Series",
        "inflation_series": inflation_series,
        "mapped": mapped,
        "missing": missing,
        "notes": [
            "Values are built from Simba workbook cached annual percentage returns.",
            "Nominal returns are converted to real returns with the workbook's Inflation US series.",
            "Only explicitly mapped Portfolio Charts-style asset codes are emitted.",
        ],
    }
    return df, coverage


def write_simba_proxy_returns(
    workbook_path: str | Path,
    output_csv: str | Path,
    coverage_json: str | Path,
    *,
    asset_codes: Sequence[str] | None = None,
) -> None:
    df, coverage = build_simba_proxy_returns(workbook_path, asset_codes=asset_codes)
    out = Path(output_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.reset_index(names="year").to_csv(out, index=False)

    coverage_out = Path(coverage_json)
    coverage_out.parent.mkdir(parents=True, exist_ok=True)
    coverage_out.write_text(json.dumps(coverage, indent=2, sort_keys=True), encoding="utf-8")


def _read_sheet_rows(workbook_path: Path, sheet_name: str) -> dict[int, dict[int, object]]:
    with zipfile.ZipFile(workbook_path) as zf:
        shared_strings = _read_shared_strings(zf)
        sheet_path = _sheet_path(zf, sheet_name)
        root = ET.fromstring(zf.read(sheet_path))

    rows: dict[int, dict[int, object]] = {}
    for row in root.findall("m:sheetData/m:row", NS):
        row_number = int(row.attrib["r"])
        values: dict[int, object] = {}
        for cell in row.findall("m:c", NS):
            col = _column_number(cell.attrib["r"])
            values[col] = _cell_value(cell, shared_strings)
        if values:
            rows[row_number] = values
    return rows


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []

    strings: list[str] = []
    for item in root.findall("m:si", NS):
        strings.append("".join(text.text or "" for text in item.findall(".//m:t", NS)))
    return strings


def _sheet_path(zf: zipfile.ZipFile, sheet_name: str) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    targets = {rel.attrib["Id"]: rel.attrib["Target"] for rel in rels.findall("rel:Relationship", NS)}

    for sheet in workbook.findall("m:sheets/m:sheet", NS):
        if sheet.attrib.get("name") != sheet_name:
            continue
        rel_id = sheet.attrib[f"{{{OFFICE_REL_NS}}}id"]
        target = targets[rel_id]
        return f"xl/{target}" if not target.startswith("/") else target.lstrip("/")

    raise KeyError(f"workbook sheet {sheet_name!r} not found")


def _cell_value(cell: ET.Element, shared_strings: Sequence[str]) -> object:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//m:t", NS))

    value = cell.find("m:v", NS)
    if value is None or value.text is None:
        return ""

    raw = value.text
    if cell_type == "s":
        return shared_strings[int(raw)]
    if cell_type == "b":
        return raw == "1"
    if cell_type in {"str", "e"}:
        return raw

    try:
        return float(raw)
    except ValueError:
        return raw


def _column_number(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref)
    if match is None:
        raise ValueError(f"invalid cell reference: {cell_ref!r}")

    out = 0
    for char in match.group(1):
        out = out * 26 + ord(char) - ord("A") + 1
    return out


def _blank_to_none(value: object) -> object | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _to_optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped in {"#N/A", "#VALUE!", "#REF!", "#DIV/0!", "#NAME?"}:
            return None
        value = stripped
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_optional_int(value: object) -> int | None:
    numeric = _to_optional_float(value)
    if numeric is None:
        return None
    return int(numeric)
