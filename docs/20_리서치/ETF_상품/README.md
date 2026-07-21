# ETF 상품 설명 승인 근거와 운영 경계

> 상태: 사용자 제공 조사자료와 그 안의 공식 상품 자료를 교차 검토한 프로젝트 승인 데이터
> 기준일: 2026-07-21
> 구조화 단일 원본: `data/reference/etf_product_descriptions.json`
> 검토 승인: 이호연(조장), 이재용(총괄)

## 범위

ETF 상품별 전체 설명과 챗봇 답변용 `one_line_description`을 보존한다. 조사자료에 종목코드가 없는 상품이 있으므로 상품명을 연결 키로 사용한다. 상품명은 NFKC 정규화, 대소문자 통일, 공백 제거만 적용하며 정규화 결과가 충돌하면 자동 연결하지 않는다.

현재 구조화 원본에는 사용자 제공 상세 조사 대화에서 확인한 자동차·모빌리티, 소비재·음식료, 조선 관련 ETF 27개와 화면 재현 상품 중 운용사 공식 자료로 보강한 12개, 총 39개의 설명이 들어 있다. 이후 승인 설명을 추가할 때도 같은 스키마와 충돌 검사를 적용한다.

## 답변 경계

- 거래대금 중앙값과 총보수는 계좌별 ETF 실데이터 마스터를 사용한다.
- 상품 순위는 거래대금 중앙값 내림차순, 총보수 오름차순 동률 해소 규칙을 사용한다.
- 상품 특징 LLM은 통합 원문에서 선택된 상품 구간만 읽고 `one_line_description`, 검증된 기초·비교지수, KIS 상위 구성종목을 함께 사용한다.
- LLM 문장은 종목코드·길이·금지 표현·입력 근거 직접 인용을 검증하며, 실패하면 승인 한 줄 설명 또는 기초지수·구성종목 기반 결정론 문장을 사용한다.
- `full_description`은 승인 원문 보존과 상품별 제한 입력에 사용하며 전체 문서를 매 요청마다 전달하지 않는다.
- 어떤 실패 경로에서도 `상품 설명 확인 필요` 문구를 사용자에게 노출하지 않는다.
- 공유 대화 URL 자체를 공식 발행기관 출처로 표시하지 않는다.
- ETF 설명은 교육용 상품 비교 정보이며 매수 지시나 미래 수익률 예측이 아니다.

## 승인 조사 계보

- <https://chatgpt.com/share/6a5d9df1-9eb0-83e8-a285-0d2aec036054>
- <https://chatgpt.com/share/6a5dbc9e-9d78-83e8-bb9c-5c2007c15d35>
- <https://chatgpt.com/share/6a5dbca9-74bc-83e8-9f83-7f105074a7be>

## 공식 상품 자료 진입점

- [삼성자산운용 KODEX](https://www.samsungfund.com/etf/main.do)
- [미래에셋자산운용 TIGER ETF](https://www.tigeretf.com)
- [신한자산운용 SOL ETF](https://www.soletf.com)
- [NH-Amundi자산운용](https://www.nh-amundi.com)
- [한국투자신탁운용 ACE ETF](https://www.aceetf.co.kr)
- [한화자산운용 PLUS ETF](https://www.plusetf.co.kr)
- [KB자산운용 RISE ETF](https://www.riseetf.co.kr)

상품별 세부 출처 계보와 승인 문구는 구조화 원본의 버전과 원격 `etf_product_descriptions` 행 해시로 관리한다.
