# ETF 테마 1~23 리서치 초안

> 상태: 사용자 제공 조사자료를 서비스 분류체계로 정리한 **검증 대기 초안**
> 기준일: 2026-07-20
> 런타임 단일 원본: `data/reference/etf_theme_catalog.json`

## 범위

| 번호 | 테마 | 런타임 ID | 기본 역할 |
|---:|---|---|---|
| 1 | AI·소프트웨어 | `ai_software` | 전술 테마 |
| 2 | 반도체 | `semiconductor` | 전술 테마 |
| 3 | 신재생·친환경 | `renewable_green` | 전술 테마 |
| 4 | 바이오·헬스케어 | `bio_healthcare` | 전술 테마 |
| 5 | 2차전지·배터리 | `secondary_battery` | 전술 테마 |
| 6 | 건설·기계·인프라 | `construction_machinery_infra` | 전술 테마 |
| 7 | 자동차·모빌리티 | `automotive_mobility` | 전술 테마 |
| 8 | 그룹주 | `business_groups` | 전술 테마 |
| 9 | 에너지·정유 | `energy_refining` | 전술 테마 |
| 10 | 미디어·엔터·게임 | `media_entertainment_gaming` | 전술 테마 |
| 11 | 원자력·전력 | `nuclear_power_grid` | 전술 테마 |
| 12 | 리츠·부동산 | `reit_real_estate` | 실물자산 |
| 13 | 로봇 | `robotics` | 전술 테마 |
| 14 | 은행·금융 | `bank_finance` | 전술 테마 |
| 15 | 방산·우주 | `defense_space` | 전술 테마 |
| 16 | 소비재·음식료 | `consumer_food` | 전술 테마 |
| 17 | 금·원자재 | `gold_commodities` | 실물자산 |
| 18 | 코리아밸류업 | `korea_value_up` | 핵심주식 |
| 19 | ESG | `esg` | 핵심주식 |
| 20 | 철강·소재 | `steel_materials` | 전술 테마 |
| 21 | 양자컴퓨팅 | `quantum_computing` | 전술 테마 |
| 22 | 메타버스 | `metaverse` | 전술 테마 |
| 23 | 조선 | `shipbuilding` | 전술 테마 |

각 테마의 쉬운 설명, 포함 분야, 관찰 요인, 한 줄 비유, 정의, 동의어, 분류 포함·제외어, 장점과 위험은 JSON 카탈로그에서 관리한다. 카탈로그 스키마 v3부터는 테마별 대표기업 3곳의 역할·초보자용 설명·선정 이유·기업 공식 홈페이지·기준일도 함께 관리한다. ETF 하나가 여러 테마 조건에 맞을 수 있으므로 분류는 다대다 관계다.

챗봇은 테마 질문을 `개요`, `대표기업`, `투자 고려사항`으로 구분한다. 대표기업은 테마를 이해시키는 교육용 예시이고, 실제 ETF의 구성종목·비중은 한국투자증권 API 스냅샷에서 별도로 조회한다.

## 검증 경계

- 이 문서는 사용자가 제공한 다섯 개의 ChatGPT 공유 대화를 구조화한 서비스 해석이다.
- 공유 대화는 조사 출처일 뿐 공식 근거가 아니다. 대화에 포함된 공식 링크와
  해당 링크가 뒷받침하는 문장을 별도로 대조한 뒤에만 승인 지식으로 승격한다.
- 아직 공식 발행기관 문서로 교차 검증하지 않았으므로 `data/knowledge/approved_documents.json`에 등록하지 않으며 승인 RAG 지식으로 사용하지 않는다.
- 챗봇은 이 내용을 `서비스 설명`으로 표시하고, 사실 확정이나 미래 수익 전망으로 표현하지 않는다.
- 대표기업 정보는 각 기업 공식 홈페이지 URL과 기준일을 함께 표시하되, ETF 편입 사실이나 투자 추천을 뜻하지 않는다.
- 공식 교차 검증은 질문 유형별 카탈로그 payload SHA-256과 승인 지식 문서·청크를 Supabase의 `etf_theme_content_reviews`·`etf_theme_content_evidence`에 연결해 관리한다. URL만 있다는 이유로 검증 완료로 보지 않는다.
- 구성종목과 비중은 이 문서에 복사하지 않는다. 한국투자증권 API의 기준일별 구조화 스냅샷을 조회해 별도 출처 칩과 함께 표시한다.

## 승인 절차

1. 테마별 정의와 위험을 금융위원회·거래소·지수사업자·운용사 등 공식 자료로 교차 검증한다.
2. 검증된 문장만 별도 근거 문서로 작성하고 기준일과 원문 URL을 기록한다.
3. 문서 검증 스크립트와 리뷰를 통과한 뒤 승인 지식 매니페스트에 추가한다.
4. ETF 편입종목은 계속 동적 데이터로 유지하며 RAG 문서에 고정하지 않는다.

## 사용자 제공 조사 링크

- <https://chatgpt.com/share/6a5dbc76-9c4c-83ee-9b7f-7729b384befe> — 1~12번 테마 소개
- <https://chatgpt.com/share/6a5dbc89-8868-83ee-8d75-2f68d6e1bffc> — 13~23번 테마 소개
- <https://chatgpt.com/share/6a5d9df1-9eb0-83e8-a285-0d2aec036054> — 1~7번 테마 상세 조사
- <https://chatgpt.com/share/6a5dbc9e-9d78-83e8-bb9c-5c2007c15d35> — 8~16번 테마 상세 조사
- <https://chatgpt.com/share/6a5dbca9-74bc-83e8-9f83-7f105074a7be> — 17~23번 테마 상세 조사
