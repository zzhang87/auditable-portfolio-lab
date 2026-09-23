import json
import zipfile
from pathlib import Path

import math


def _cell_ref(col: int, row: int) -> str:
    out = ""
    while col:
        col, rem = divmod(col - 1, 26)
        out = chr(65 + rem) + out
    return f"{out}{row}"


def _write_minimal_simba_workbook(path: Path) -> None:
    rows = {
        1: ["ER-adjusted spliced returns", "LCB", "Gold", "Inflation US", "Europe", "Int'l Value"],
        2: ["2025", "VFIAX", "IAU", "Inflation US", "VEUSX", "EFV"],
        3: ["Expense Ratio:", "0.04", "0.25", "0", "0.09", "0.31"],
        4: ["Year 1st return:", "1871", "1969", "1871", "1970", "1975"],
        5: ["Raw data index:", "25", "283", "446", "144", "150"],
        7: ["Nominal returns", "", "", "", ""],
        8: ["2020", "12.0", "20.0", "2.0", "7.0", "9.0"],
        9: ["2021", "-4.0", "-8.0", "3.0", "5.0", "6.0"],
    }
    sheet_rows = []
    for row_num, values in rows.items():
        cells = []
        for col_num, value in enumerate(values, start=1):
            ref = _cell_ref(col_num, row_num)
            if col_num == 1 or row_num in {1, 2, 3, 4, 5, 7}:
                cells.append(
                    f'<c r="{ref}" t="inlineStr"><is><t>{value}</t></is></c>'
                )
            else:
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
        sheet_rows.append(f'<row r="{row_num}">{"".join(cells)}</row>')

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows)}</sheetData>'
        "</worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Data_Series" sheetId="1" r:id="rId1"/></sheets>'
        "</workbook>"
    )
    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet7.xml"/>'
        "</Relationships>"
    )
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("xl/workbook.xml", workbook_xml)
        zf.writestr("xl/_rels/workbook.xml.rels", rels_xml)
        zf.writestr("xl/worksheets/sheet7.xml", sheet_xml)


def test_load_simba_data_series_extracts_headers_metadata_and_annual_returns(tmp_path):
    from pcopt.simba import load_simba_data_series

    workbook_path = tmp_path / "simba.xlsx"
    _write_minimal_simba_workbook(workbook_path)

    data = load_simba_data_series(workbook_path)

    assert list(data.index) == [2020, 2021]
    assert data.loc[2020, "LCB"] == 12.0
    assert data.attrs["series_metadata"]["LCB"]["ticker"] == "VFIAX"
    assert data.attrs["series_metadata"]["LCB"]["first_year"] == 1871


def test_build_simba_proxy_returns_maps_known_assets_and_reports_gaps(tmp_path):
    from pcopt.simba import build_simba_proxy_returns

    workbook_path = tmp_path / "simba.xlsx"
    _write_minimal_simba_workbook(workbook_path)

    returns, coverage = build_simba_proxy_returns(
        workbook_path,
        asset_codes=["USA-LCB", "GLO-GLD", "EUR-LCB", "XUS-LCV", "EUR-LTT"],
    )

    assert list(returns.columns) == ["USA-LCB", "GLO-GLD", "EUR-LCB", "XUS-LCV"]
    assert math.isclose(returns.loc[2020, "USA-LCB"], (1.12 / 1.02) - 1.0)
    assert math.isclose(returns.loc[2021, "GLO-GLD"], (0.92 / 1.03) - 1.0)
    assert coverage["mapped"]["EUR-LCB"]["source_series"] == "Europe"
    assert coverage["mapped"]["XUS-LCV"]["source_series"] == "Int'l Value"
    assert coverage["missing"] == {"EUR-LTT": "no Simba Data_Series mapping configured"}


def test_write_simba_proxy_returns_writes_csv_and_coverage_json(tmp_path):
    from pcopt.simba import write_simba_proxy_returns

    workbook_path = tmp_path / "simba.xlsx"
    output_csv = tmp_path / "simba_returns.csv"
    coverage_json = tmp_path / "coverage.json"
    _write_minimal_simba_workbook(workbook_path)

    write_simba_proxy_returns(
        workbook_path,
        output_csv,
        coverage_json,
        asset_codes=["USA-LCB", "GLO-GLD", "EUR-LTT"],
    )

    assert output_csv.read_text(encoding="utf-8").splitlines()[0] == "year,USA-LCB,GLO-GLD"
    coverage = json.loads(coverage_json.read_text(encoding="utf-8"))
    assert coverage["missing"] == {"EUR-LTT": "no Simba Data_Series mapping configured"}
