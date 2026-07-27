"""내레이터 모델 벤더 비교 - 비용/속도/가드 통과율 실측.

왜 이 스크립트가 있나
---------------------
`ANTHROPIC_MODEL` 기본값을 Haiku로 둔 근거가 문서에만 문장으로 남아 있고
재현할 방법이 없었다. Claude 채택 자체도 초기 선택 이후 재검토된 적이 없어
"왜 OpenAI나 Gemini가 아닌가"에 답할 자료가 없다.

공정 비교를 위해 고정하는 것
---------------------------
- 같은 SYSTEM_PROMPT(운영 내레이터와 동일 문자열)
- 같은 입력(검증 답변)
- 같은 판정 함수(_adds_unverified_content, contains_unsafe_financial_claim)

즉 모델만 바꾼다. thinking 같은 벤더 고유 옵션은 켜지 않는다. 이전 측정이
모델과 thinking을 동시에 바꿔 해석 불가능해진 전례를 반복하지 않기 위해서다.

측정 지표
---------
- latency: 호출 왕복 실측(초). p50/p95를 함께 본다.
- guard_pass: 원문에 없는 숫자나 위험 표현을 만들지 않은 비율.
- cost: 응답 1건당 USD. 단가는 --pricing JSON으로 주입한다(하드코딩하면
  벤더 가격 개정 때 조용히 틀린다). 1건 단가가 $0.0004~0.007 범위라
  자릿수 비교가 어려워 1,000건 환산값을 함께 출력한다. 환산값은 계산
  결과일 뿐 실제 호출 횟수가 아니다.

사용법
------
    uv run python scripts/benchmark_narration_models.py --dry-run
    uv run python scripts/benchmark_narration_models.py \
        --model anthropic:claude-haiku-4-5 \
        --model openai:gpt-5.6-luna \
        --pricing scripts/data/model_pricing.json \
        --answers-out scripts/data/vendor_answers.md

기본은 모델당 10응답(케이스 10개 x 반복 1회)이다. --repeat를 올리면
호출 수와 비용이 그만큼 배로 늘어난다.

API 키는 벤더별 환경변수(ANTHROPIC_API_KEY / OPENAI_API_KEY /
GOOGLE_API_KEY)에서 읽는다. 키가 없는 벤더는 건너뛰고 사유를 남긴다.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.chat.narration_guard import (  # noqa: E402
    _adds_unverified_content,
    contains_unsafe_financial_claim,
)
from backend.app.chat.narrator import SYSTEM_PROMPT  # noqa: E402

# 운영 내레이터가 실제로 재서술하는 4개 인텐트(ACCOUNT_RULE, PENSION_TAX,
# MOCK_PORTFOLIO, PROVIDER_DISCLOSURE)에서 뽑은 대표질문 10개다. 실제 챗봇이
# 받는 질문과 그때 규칙 엔진이 내놓는 검증 답변을 짝으로 둔다.
#
# 가드는 "검증 답변에 없는 숫자를 만들지 않았는가"로 판정하므로, 케이스에는
# 숫자·단위·계좌 규칙이 실제로 들어 있어야 변별력이 생긴다.
CASES: list[dict[str, str]] = [
    {
        "id": "q01_dc_risk_limit",
        "intent": "account_rule",
        "question": "DC형 계좌에서 위험자산은 얼마까지 담을 수 있나요?",
        "verified": (
            "DC형 퇴직연금은 적립금의 70%까지 일반 위험자산으로 운용할 수 "
            "있어요. 나머지 30%는 원리금보장상품이나 적격 TDF 등으로 채워야 해요."
        ),
    },
    {
        "id": "q02_pension_savings_no_limit",
        "intent": "account_rule",
        "question": "연금저축도 위험자산 한도가 70%인가요?",
        "verified": (
            "연금저축펀드에는 DC형이나 IRP와 같은 위험자산 총량 한도가 없어요. "
            "다만 상품 적격성 규칙은 별도로 적용돼요."
        ),
    },
    {
        "id": "q03_irp_vs_dc",
        "intent": "account_rule",
        "question": "IRP와 DC형은 운용 규칙이 어떻게 다른가요?",
        "verified": (
            "IRP와 DC형은 모두 적립금의 70%까지만 일반 위험자산으로 운용할 수 "
            "있어요. 두 계좌 모두 나머지 30%는 원리금보장상품이나 적격 TDF로 "
            "채워야 해요."
        ),
    },
    {
        "id": "q04_tax_credit_limit",
        "intent": "pension_tax",
        "question": "연금저축이랑 IRP 세액공제 한도가 얼마예요?",
        "verified": (
            "연금저축 납입액은 연 600만원까지, 개인형 IRP를 합치면 연 900만원"
            "까지 세액공제 대상이에요. 총급여 5,500만원 이하면 공제율은 16.5%예요."
        ),
    },
    {
        "id": "q05_tax_credit_rate",
        "intent": "pension_tax",
        "question": "총급여 6천만원이면 공제율이 어떻게 되나요?",
        "verified": (
            "총급여 5,500만원을 넘으면 세액공제율은 13.2%가 적용돼요. "
            "5,500만원 이하일 때의 16.5%보다 낮아요."
        ),
    },
    {
        "id": "q06_non_pension_withdrawal",
        "intent": "pension_tax",
        "question": "중간에 연금을 깨면 세금이 어떻게 되나요?",
        "verified": (
            "연금 외 수령으로 인출하면 기타소득세 16.5%가 원천징수돼요. "
            "부득이한 사유에 해당하면 연금소득세율이 적용될 수 있어요."
        ),
    },
    {
        "id": "q07_receiving_tax_rate",
        "intent": "pension_tax",
        "question": "연금을 받을 때 세율은 나이에 따라 다른가요?",
        "verified": (
            "연금 수령 시 세율은 나이에 따라 달라져요. 70세 미만은 5.5%, "
            "70세 이상 80세 미만은 4.4%, 80세 이상은 3.3%가 적용돼요."
        ),
    },
    {
        "id": "q08_cash_concentration",
        "intent": "mock_portfolio",
        "question": "제 계좌 상태 점검해 주세요.",
        "verified": (
            "보유 자산의 82%가 현금성 자산이에요. 계좌별 진단 기준인 80%를 "
            "넘어 운용 점검 대상으로 표시했어요."
        ),
    },
    {
        "id": "q09_asset_concentration",
        "intent": "mock_portfolio",
        "question": "제 포트폴리오가 한쪽에 쓸려 있나요?",
        "verified": (
            "비현금 자산 중 국내주식 비중이 63%예요. 단일 자산군 편중 기준인 "
            "50%를 넘어 분산 점검 대상이에요."
        ),
    },
    {
        "id": "q10_provider_count",
        "intent": "provider_disclosure",
        "question": "퇴직연금 DC형 사업자는 몇 곳이나 되나요?",
        "verified": (
            "2026년 1분기 기준 퇴직연금 DC형을 운용하는 사업자는 42개사예요. "
            "공시 데이터는 금융감독원 통합연금포털에서 수집했어요."
        ),
    },
]


@dataclass
class CallResult:
    ok: bool
    latency_s: float
    text: str = ""
    source: str = ""
    case_id: str = ""
    question: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    error: str = ""

    def guard_ok(self) -> bool:
        if not self.text:
            return False
        if _adds_unverified_content(self.text, self.source):
            return False
        return not contains_unsafe_financial_claim(self.text)


@dataclass
class ModelReport:
    spec: str
    results: list[CallResult] = field(default_factory=list)
    skipped: str = ""

    @property
    def ok_results(self) -> list[CallResult]:
        return [r for r in self.results if r.ok]

    def latency(self, pct: float) -> float:
        values = sorted(r.latency_s for r in self.ok_results)
        if not values:
            return 0.0
        index = min(len(values) - 1, int(round((len(values) - 1) * pct)))
        return values[index]

    def guard_pass_rate(self) -> float:
        rows = self.ok_results
        if not rows:
            return 0.0
        return sum(1 for r in rows if r.guard_ok()) / len(rows)

    def mean_tokens(self) -> tuple[float, float]:
        rows = self.ok_results
        if not rows:
            return 0.0, 0.0
        return (
            statistics.fmean(r.input_tokens for r in rows),
            statistics.fmean(r.output_tokens for r in rows),
        )


def _build_prompt(verified: str) -> str:
    return "다음 검증 답변을 규칙에 맞게 다시 써라.\n\n[검증 답변]\n" + verified


def _call_anthropic(model: str, prompt: str, api_key: str) -> CallResult:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    started = time.perf_counter()
    try:
        message = client.messages.create(
            model=model,
            max_tokens=2500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:  # 벤더 오류는 비교 대상이 아니라 기록 대상이다.
        return CallResult(False, time.perf_counter() - started, error=str(exc))
    elapsed = time.perf_counter() - started
    text = "".join(
        b.text for b in message.content if getattr(b, "type", "") == "text"
    )
    return CallResult(
        True,
        elapsed,
        text=text,
        input_tokens=message.usage.input_tokens,
        output_tokens=message.usage.output_tokens,
    )


def _call_openai(model: str, prompt: str, api_key: str) -> CallResult:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    started = time.perf_counter()
    try:
        completion = client.chat.completions.create(
            model=model,
            max_completion_tokens=2500,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        )
    except Exception as exc:
        return CallResult(False, time.perf_counter() - started, error=str(exc))
    elapsed = time.perf_counter() - started
    usage = completion.usage
    return CallResult(
        True,
        elapsed,
        text=completion.choices[0].message.content or "",
        input_tokens=getattr(usage, "prompt_tokens", 0),
        output_tokens=getattr(usage, "completion_tokens", 0),
    )


def _call_google(model: str, prompt: str, api_key: str) -> CallResult:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    started = time.perf_counter()
    try:
        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                max_output_tokens=2500,
            ),
        )
    except Exception as exc:
        return CallResult(False, time.perf_counter() - started, error=str(exc))
    elapsed = time.perf_counter() - started
    usage = response.usage_metadata
    return CallResult(
        True,
        elapsed,
        text=response.text or "",
        input_tokens=getattr(usage, "prompt_token_count", 0),
        output_tokens=getattr(usage, "candidates_token_count", 0),
    )


VENDORS = {
    "anthropic": ("ANTHROPIC_API_KEY", _call_anthropic),
    "openai": ("OPENAI_API_KEY", _call_openai),
    "google": ("GOOGLE_API_KEY", _call_google),
}


def run_model(spec: str, repeat: int, *, dry_run: bool) -> ModelReport:
    report = ModelReport(spec=spec)
    if ":" not in spec:
        report.skipped = "형식 오류: <vendor>:<model>로 지정한다"
        return report
    vendor, model = spec.split(":", 1)
    if vendor not in VENDORS:
        report.skipped = "지원하지 않는 벤더: " + vendor
        return report
    env_name, caller = VENDORS[vendor]
    if dry_run:
        report.skipped = "dry-run"
        return report
    api_key = os.environ.get(env_name, "").strip()
    if not api_key:
        report.skipped = env_name + " 없음"
        return report

    for case in CASES:
        prompt = _build_prompt(case["verified"])
        for _ in range(repeat):
            result = caller(model, prompt, api_key)
            result.source = case["verified"]
            result.case_id = case["id"]
            result.question = case["question"]
            report.results.append(result)
    return report


def cost_per_call(report: ModelReport, pricing: dict[str, Any]) -> float | None:
    """응답 1건당 USD. 단가 미등록 모델은 None을 돌려 '단가없음'으로 표시한다."""

    entry = pricing.get(report.spec)
    if not entry:
        return None
    mean_in, mean_out = report.mean_tokens()
    return mean_in / 1_000_000 * float(entry["input_per_mtok_usd"]) + (
        mean_out / 1_000_000 * float(entry["output_per_mtok_usd"])
    )


def _write_answers(path: Path, reports: list[ModelReport]) -> None:
    """질문별로 모델 답변을 나란히 적는다.

    수치만으로는 안 보이는 문체·길이·군더더기 차이를 사람이 직접 읽고
    판단하기 위한 산출물이다.
    """

    lines = ["# 모델별 답변 비교", ""]
    live = [r for r in reports if not r.skipped]
    for case in CASES:
        lines.append(f"## {case['id']} ({case['intent']})")
        lines.append("")
        lines.append(f"**질문**: {case['question']}")
        lines.append("")
        lines.append(f"**검증 답변(엔진)**: {case['verified']}")
        lines.append("")
        for report in live:
            first = next(
                (
                    r
                    for r in report.results
                    if r.case_id == case["id"] and r.ok and r.text
                ),
                None,
            )
            if first is None:
                lines.append(f"- `{report.spec}`: (응답 없음)")
                continue
            flag = "OK" if first.guard_ok() else "가드위반"
            body = " ".join(first.text.split())
            lines.append(f"- `{report.spec}` [{flag}, {first.latency_s:.2f}s]")
            lines.append(f"  - {body}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="내레이터 모델 벤더 비교")
    parser.add_argument("--model", action="append", default=[], dest="models")
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="케이스당 반복 호출 수(기본 1 = 모델당 10응답). 올리면 비용도 배로 늘다",
    )
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument(
        "--answers-out",
        type=Path,
        help="모델별 실제 답변 텍스트를 마크다운으로 저장한다(질문별 나란히 비교용)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    models = args.models or [
        "anthropic:claude-haiku-4-5",
        "anthropic:claude-sonnet-5",
    ]
    pricing: dict[str, Any] = {}
    if args.pricing and args.pricing.exists():
        pricing = json.loads(args.pricing.read_text(encoding="utf-8"))

    calls = len(CASES) * args.repeat
    print(
        f"케이스 {len(CASES)}개 x 반복 {args.repeat}회 = 모델당 {calls}회 호출"
        f" (총 {calls * len(models)}회)"
    )
    print()
    reports = [run_model(s, args.repeat, dry_run=args.dry_run) for s in models]

    header = (
        f"{'모델':<34s} {'호출':>5s} {'p50(s)':>8s} "
        f"{'p95(s)':>8s} {'가드':>7s} {'$/응답':>11s} {'$/1k환산':>10s}"
    )
    print(header)
    print("-" * 92)
    for report in reports:
        if report.skipped:
            print(f"{report.spec:<34s} {'skip':>5s}  ({report.skipped})")
            continue
        cost = cost_per_call(report, pricing)
        if cost is None:
            cost_text = f"{'단가없음':>11s}"
            scaled_text = f"{'-':>10s}"
        else:
            cost_text = f"{cost:11.6f}"
            scaled_text = f"{cost * 1000:10.2f}"
        print(
            f"{report.spec:<34s} {len(report.ok_results):5d} "
            f"{report.latency(0.5):8.2f} {report.latency(0.95):8.2f} "
            f"{report.guard_pass_rate() * 100:6.0f}% {cost_text} {scaled_text}"
        )
        failures = [r for r in report.results if not r.ok]
        if failures:
            print(f"{'':<34s} 실패 {len(failures)}건: {failures[0].error[:70]}")

    if args.answers_out:
        _write_answers(args.answers_out, reports)
        print(f"\n답변 비교를 {args.answers_out}에 저장했다.")

    if args.json_out:
        payload = [
            {
                "spec": r.spec,
                "skipped": r.skipped,
                "calls": len(r.ok_results),
                "latency_p50_s": round(r.latency(0.5), 3),
                "latency_p95_s": round(r.latency(0.95), 3),
                "guard_pass_rate": round(r.guard_pass_rate(), 4),
                "mean_input_tokens": round(r.mean_tokens()[0], 1),
                "mean_output_tokens": round(r.mean_tokens()[1], 1),
                "cost_per_call_usd": cost_per_call(r, pricing),
            }
            for r in reports
        ]
        args.json_out.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\n결과를 {args.json_out}에 저장했다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
