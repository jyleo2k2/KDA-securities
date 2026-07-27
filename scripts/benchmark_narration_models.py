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
- cost: 응답 1,000건당 USD. 단가는 --pricing JSON으로 주입한다(하드코딩하면
  벤더 가격 개정 때 조용히 틀린다).

사용법
------
    uv run python scripts/benchmark_narration_models.py --dry-run
    uv run python scripts/benchmark_narration_models.py \
        --model anthropic:claude-haiku-4-5 \
        --model openai:gpt-5.2 \
        --repeat 5 --pricing scripts/data/model_pricing.json

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

# 운영 내레이터가 실제로 재서술하는 인텐트에서 뽑은 검증 답변 표본이다.
# 숫자, 단위, 계좌 규칙이 섞여 있어야 가드가 의미 있게 작동한다.
CASES: list[dict[str, str]] = [
    {
        "id": "account_rule_dc_limit",
        "verified": (
            "DC형 퇴직연금은 적립금의 70%까지 일반 위험자산으로 운용할 수 "
            "있어요. 나머지 30%는 원리금보장상품이나 적격 TDF 등으로 채워야 해요."
        ),
    },
    {
        "id": "account_rule_pension_savings",
        "verified": (
            "연금저축펀드에는 DC형이나 IRP와 같은 위험자산 총량 한도가 없어요. "
            "다만 상품 적격성 규칙은 별도로 적용돼요."
        ),
    },
    {
        "id": "pension_tax_credit",
        "verified": (
            "연금저축 납입액은 연 600만원까지, 개인형 IRP를 합치면 연 900만원까지 "
            "세액공제 대상이에요. 총급여 5,500만원 이하면 공제율은 16.5%예요."
        ),
    },
    {
        "id": "portfolio_diagnosis",
        "verified": (
            "보유 자산의 82%가 현금성 자산이에요. 계좌별 진단 기준인 80%를 넘어 "
            "운용 점검 대상으로 표시했어요."
        ),
    },
    {
        "id": "provider_disclosure",
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
            report.results.append(result)
    return report


def cost_per_1k(report: ModelReport, pricing: dict[str, Any]) -> float | None:
    entry = pricing.get(report.spec)
    if not entry:
        return None
    mean_in, mean_out = report.mean_tokens()
    per_call = mean_in / 1_000_000 * float(entry["input_per_mtok_usd"]) + (
        mean_out / 1_000_000 * float(entry["output_per_mtok_usd"])
    )
    return per_call * 1000


def main() -> int:
    parser = argparse.ArgumentParser(description="내레이터 모델 벤더 비교")
    parser.add_argument("--model", action="append", default=[], dest="models")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    models = args.models or [
        "anthropic:claude-haiku-4-5",
        "anthropic:claude-sonnet-5",
    ]
    pricing: dict[str, Any] = {}
    if args.pricing and args.pricing.exists():
        pricing = json.loads(args.pricing.read_text(encoding="utf-8"))

    print(f"케이스 {len(CASES)}개 x 반복 {args.repeat}회")
    print()
    reports = [run_model(s, args.repeat, dry_run=args.dry_run) for s in models]

    header = (
        f"{'모델':<34s} {'호출':>5s} {'p50(s)':>8s} "
        f"{'p95(s)':>8s} {'가드':>7s} {'$/1k':>10s}"
    )
    print(header)
    print("-" * 78)
    for report in reports:
        if report.skipped:
            print(f"{report.spec:<34s} {'skip':>5s}  ({report.skipped})")
            continue
        cost = cost_per_1k(report, pricing)
        cost_text = f"{cost:10.2f}" if cost is not None else f"{'단가없음':>10s}"
        print(
            f"{report.spec:<34s} {len(report.ok_results):5d} "
            f"{report.latency(0.5):8.2f} {report.latency(0.95):8.2f} "
            f"{report.guard_pass_rate() * 100:6.0f}% {cost_text}"
        )
        failures = [r for r in report.results if not r.ok]
        if failures:
            print(f"{'':<34s} 실패 {len(failures)}건: {failures[0].error[:70]}")

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
                "cost_per_1k_usd": cost_per_1k(r, pricing),
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
