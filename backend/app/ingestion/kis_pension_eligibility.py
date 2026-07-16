import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"main": MAIN_NS}
PRODUCT_CODE_PATTERN = re.compile(r"[0-9A-Z]{6}")


def _shared_strings(archive: ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(node.text or "" for node in item.findall(".//main:t", NS))
        for item in root.findall("main:si", NS)
    ]


def _cell_value(cell: ElementTree.Element, shared: list[str]) -> str:
    cell_type = cell.get("t")
    if cell_type == "inlineStr":
        return "".join(
            node.text or "" for node in cell.findall(".//main:t", NS)
        )
    value = cell.find("main:v", NS)
    if value is None or value.text is None:
        return ""
    if cell_type == "s":
        index = int(value.text)
        try:
            return shared[index]
        except IndexError as exc:
            raise ValueError("XLSX shared-string index is out of range") from exc
    return value.text


def _row_values(
    row: ElementTree.Element,
    shared: list[str],
) -> dict[str, str]:
    values = {}
    for cell in row.findall("main:c", NS):
        reference = cell.get("r") or ""
        column = "".join(character for character in reference if character.isalpha())
        if column:
            values[column] = _cell_value(cell, shared).strip()
    return values


def _limit_percent(raw: str, code: str) -> int:
    try:
        value = Decimal(raw) * Decimal("100")
    except InvalidOperation as exc:
        raise ValueError(f"KIS retirement limit is invalid for ETF {code}") from exc
    if value != value.to_integral_value() or not 0 < value <= 100:
        raise ValueError(f"KIS retirement limit is invalid for ETF {code}")
    return int(value)


def _decimal_string(raw: str) -> str | None:
    if not raw or raw == "-":
        return None
    try:
        value = Decimal(raw.replace(",", ""))
    except InvalidOperation as exc:
        raise ValueError(f"KIS workbook numeric field is invalid: {raw}") from exc
    if not value.is_finite():
        raise ValueError(f"KIS workbook numeric field is invalid: {raw}")
    if value.as_tuple().exponent < -8:
        value = value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
    return format(value.normalize(), "f")


def _excel_date(raw: str) -> str | None:
    if not raw:
        return None
    try:
        serial = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError(f"KIS workbook listing date is invalid: {raw}") from exc
    if serial != serial.to_integral_value() or serial <= 0:
        raise ValueError(f"KIS workbook listing date is invalid: {raw}")
    return (date(1899, 12, 30) + timedelta(days=int(serial))).isoformat()


def _net_assets_krw(raw: str) -> int | None:
    normalized = _decimal_string(raw)
    if normalized is None:
        return None
    value = Decimal(normalized) * Decimal("100000000")
    if value < 0:
        raise ValueError(f"KIS workbook net assets are invalid: {raw}")
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def load_kis_retirement_etfs(path: Path) -> list[dict[str, object]]:
    """Read the official KIS retirement ETF sheet without an XLSX dependency."""

    try:
        with ZipFile(path) as archive:
            shared = _shared_strings(archive)
            sheet = ElementTree.fromstring(
                archive.read("xl/worksheets/sheet1.xml")
            )
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise ValueError(f"invalid KIS retirement ETF workbook: {path}") from exc

    categories = {"A": "", "B": "", "C": ""}
    products: list[dict[str, object]] = []
    for row in sheet.findall(".//main:sheetData/main:row", NS):
        values = _row_values(row, shared)
        code = values.get("E", "").upper()
        name = values.get("D", "")
        limit = values.get("G", "")
        if not PRODUCT_CODE_PATTERN.fullmatch(code) or not name or not limit:
            continue
        for column in categories:
            if values.get(column):
                categories[column] = values[column]
        products.append(
            {
                "isu_code": code,
                "isu_name": name,
                "major_category": categories["A"],
                "middle_category": categories["B"],
                "minor_category": categories["C"],
                "retirement_investment_limit_percent": _limit_percent(
                    limit, code
                ),
                "asset_manager": values.get("F", "") or None,
                "monthly_distribution_target": bool(values.get("H", "")),
                "monthly_distribution_label": values.get("H", "") or None,
                "total_expense_ratio_percent": _decimal_string(
                    values.get("I", "")
                ),
                "listing_date": _excel_date(values.get("J", "")),
                "net_assets_krw": _net_assets_krw(values.get("K", "")),
                "provider_reported_returns_percent": {
                    "1m": _decimal_string(values.get("L", "")),
                    "3m": _decimal_string(values.get("M", "")),
                    "6m": _decimal_string(values.get("N", "")),
                    "1y": _decimal_string(values.get("O", "")),
                    "2y": _decimal_string(values.get("P", "")),
                    "3y": _decimal_string(values.get("Q", "")),
                    "ytd": _decimal_string(values.get("R", "")),
                },
            }
        )

    codes = [str(product["isu_code"]) for product in products]
    if not products:
        raise ValueError("KIS retirement ETF workbook contains no product rows")
    if len(codes) != len(set(codes)):
        raise ValueError("KIS retirement ETF workbook contains duplicate codes")
    return products
