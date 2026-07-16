from datetime import datetime

from backend.app.ingestion.kind_distribution_client import (
    parse_disclosure_search,
    parse_distribution_events,
    parse_distribution_ex_date_event,
    parse_document_url,
    parse_main_document_number,
)


def test_kind_search_and_viewer_parsers_preserve_identifiers() -> None:
    search_html = """
    <table><tr>
      <td>1</td><td>2026-07-13 17:05</td>
      <td><a onclick="etfisusummary_open('40297')" title="테스트 ETF">ETF</a></td>
      <td><a onclick="openDisclsViewer('20260713000448','')"
             title="ETF이익금분배신고">공시</a></td>
      <td>신한펀드파트너스</td>
    </tr></table>
    """
    viewer_html = """
    <select id="mainDoc"><option value="">선택</option>
    <option value="20260713001049|Y" selected>본문</option></select>
    """
    path_html = """
    <script>parent.setPath('',
    'https://kind.krx.co.kr/external/2026/a.htm','/external/a','04','30');</script>
    """

    rows = parse_disclosure_search(search_html)

    assert rows[0].isu_code == "040297"
    assert rows[0].receipt_number == "20260713000448"
    assert rows[0].submitter == "신한펀드파트너스"
    assert parse_main_document_number(viewer_html) == "20260713001049"
    assert parse_document_url(path_html).endswith("/external/2026/a.htm")


def test_kind_distribution_table_parser_extracts_alphanumeric_code() -> None:
    filing_html = """
    <table>
      <tr><th>종목코드</th><th>종목약명</th>
          <th>투자신탁 분배금 지급기준일</th>
          <th>투자신탁 분배금 지급예정일</th>
          <th>분배금(원)</th><th>기타</th></tr>
      <tr><td>KR70015E0001</td><td>테스트 ETF</td>
          <td>2026-07-15</td><td>2026-07-20</td>
          <td>1,234</td><td>-</td></tr>
    </table>
    """

    events = parse_distribution_events(
        filing_html,
        receipt_number="20260713000448",
        submitted_at=datetime(2026, 7, 13, 17, 5),
        source_url="https://kind.krx.co.kr/external/sample.htm",
    )

    assert len(events) == 1
    assert events[0].isu_code == "0015E0"
    assert str(events[0].distribution_per_share_krw) == "1234"
    assert events[0].record_date.isoformat() == "2026-07-15"
    assert events[0].payment_date is not None
    assert events[0].payment_date.isoformat() == "2026-07-20"


def test_kind_distribution_parser_supports_historical_name_header() -> None:
    filing_html = """
    <table><tr><th>종목코드</th><th>종목명</th>
    <th>분배금 지급기준일</th><th>분배금 지급예정일</th>
    <th>분배금(원)</th></tr>
    <tr><td>KR7069500007</td><td>KODEX 200</td>
    <td>2020-01-31</td><td>2020-02-04</td><td>50</td></tr></table>
    """

    events = parse_distribution_events(
        filing_html,
        receipt_number="20200129000268",
        submitted_at=datetime(2020, 1, 29, 17, 5),
        source_url="https://kind.krx.co.kr/external/historical.htm",
    )

    assert len(events) == 1
    assert events[0].isu_code == "069500"


def test_kind_ex_distribution_parser_uses_official_effective_date() -> None:
    filing_html = """
    <table>
      <tr><td>1. 종목명</td><td>KODEX 200</td></tr>
      <tr><td>2. 기준가격(원)</td><td>31,245</td></tr>
      <tr><td>3. 사유</td><td>분배락</td></tr>
      <tr><td>4. 적용일</td><td>2026-04-29</td></tr>
      <tr><td>5. 근거규정</td><td>업무규정시행세칙 제30조</td></tr>
    </table>
    """

    event = parse_distribution_ex_date_event(
        filing_html,
        isu_code="6950",
        isu_name="KODEX 200",
        receipt_number="20260428000001",
        submitted_at=datetime(2026, 4, 28, 18, 30),
        source_url="https://kind.krx.co.kr/external/ex-date.htm",
    )

    assert event.isu_code == "069500"
    assert event.effective_date.isoformat() == "2026-04-29"
    assert str(event.reference_price_krw) == "31245"
