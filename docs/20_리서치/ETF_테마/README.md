# ETF 테마 1~23 프로젝트 승인 근거

> 상태: 사용자 제공 조사자료와 그 안의 공식 링크를 교차 검토한 **프로젝트 승인 근거**
> 기준일: 2026-07-20
> 런타임 단일 원본: `data/reference/etf_theme_catalog.json`
> 승인 범위: 카탈로그 `2026-07-20.3`의 23개 테마와 질문 유형 5종
> 검토 승인: 이호연(조장), 이재용(총괄)

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

챗봇은 테마 질문을 `개요`, `대표기업`, `투자 고려사항`, `성과 관찰요인`, `고유 위험`으로 구분한다. 대표기업은 테마를 이해시키는 교육용 예시이고, 실제 ETF의 구성종목·비중은 한국투자증권 API 스냅샷에서 별도로 조회한다.

## 검증 경계

- 이 문서는 사용자가 제공한 다섯 개의 ChatGPT 공유 대화를 구조화한 서비스 해석이다.
- 공유 대화 자체를 공식 발행기관 출처로 표시하지 않는다. 대화에 포함된 공식 링크와 해당 링크가 뒷받침하는 문장의 교차 검토가 완료됐다는 이호연 조장과 이재용 총괄의 승인을 2026-07-20에 전달받았다.
- 승인 대상 문구의 단일 원본은 카탈로그 `2026-07-20.3`이다. 이 문서는 승인 범위·출처 계보·운영 경계를 기록하며 승인 RAG 매니페스트에 등록한다.
- 챗봇은 이 내용을 `서비스 설명`으로 표시하고, 사실 확정이나 미래 수익 전망으로 표현하지 않는다.
- 대표기업 정보는 각 기업 공식 홈페이지 URL과 기준일을 함께 표시하되, ETF 편입 사실이나 투자 추천을 뜻하지 않는다.
- 공식 교차 검증은 질문 유형별 카탈로그 payload SHA-256과 승인 지식 문서·청크를 Supabase의 `etf_theme_content_reviews`·`etf_theme_content_evidence`에 연결해 관리한다. URL만 있다는 이유로 검증 완료로 보지 않는다.
- 구성종목과 비중은 이 문서에 복사하지 않는다. 한국투자증권 API의 기준일별 구조화 스냅샷을 조회해 별도 출처 칩과 함께 표시한다.
- 카탈로그 문구·버전·질문 유형별 payload 해시가 바뀌면 이 승인을 자동 재사용하지 않고 재검토한다.

## 승인 및 배포 절차

1. 완료: 테마별 정의·포함 분야·대표기업·기회 요인·위험·관찰 요인을 공식 자료와 교차 검토했다.
2. 완료: 이호연 조장과 이재용 총괄의 승인 범위를 카탈로그 버전과 기준일에 고정했다.
3. 로컬 반영: 이 문서를 승인 지식 매니페스트에 추가하고 문서 해시·청킹 검증을 통과시킨다.
4. 원격 반영: 승인 지식 적재·임베딩 후 115개 질문 유형의 payload 해시와 실제 지식 청크·공식 URL을 검증 장부에 연결한다.
5. ETF 편입종목·거래대금·총보수는 계속 동적 데이터로 유지하며 RAG 문서에 고정하지 않는다.

## 공통 공식 근거

- [한국거래소 ETF 기본 개념](https://open.krx.co.kr/contents/OPN/01/01030100/OPN01030100.jsp)
- [한국거래소 ETF 순자산가치와 시장가격](https://open.krx.co.kr/contents/OPN/01/01030203/OPN01030203T2.jsp)
- [한국거래소 ETF 추적오차와 괴리율](https://open.krx.co.kr/contents/OPN/01/01030203/OPN01030203T3.jsp)
- [한국거래소 ETF 상장·관리 규정](https://regulation.krx.co.kr/contents/RGL/03/03060101/RGL03060101.jsp)

위 링크는 ETF의 공통 구조와 비교지표를 뒷받침한다. 23개 테마별 산업 설명의 출처 계보는 아래 다섯 조사자료에 포함된 공식 링크와 카탈로그의 대표기업 공식 홈페이지 URL로 보존한다. 공유 대화 URL 자체는 공식 발행기관 출처 칩으로 사용하지 않는다.

## 테마별 공식 근거 연결

아래 표식은 원격 검증 장부가 실제 RAG 청크를 찾는 안정적인 키다. 각 링크는 승인 대화에 포함되어 교차 검토된 공식 발행기관 자료이며, 질문 유형별 답변 문구의 정확성은 카탈로그 payload SHA-256으로 별도 잠근다.

### [theme:ai_software] AI·소프트웨어
[국가법령정보센터 인공지능기본법](https://www.law.go.kr/lsInfoP.do?ancYnChk=0&lsId=014820)

### [theme:semiconductor] 반도체
[대한민국 정책브리핑 반도체 정책자료](https://www.korea.kr/special/policyCurationView.do?newsId=148868225)

### [theme:renewable_green] 신재생·친환경
[국가법령정보센터 신에너지 및 재생에너지 법령](https://www.law.go.kr/LSW/lsLawLinkInfo.do?ancYnChk=&chrClsCd=010202&lsJoLnkSeq=1012697749)

### [theme:bio_healthcare] 바이오·헬스케어
[국가법령정보센터 보건의료기술 진흥법](https://www.law.go.kr/LSW/lsLawLinkInfo.do?chrClsCd=010202&lsId=000219&lsJoLnkSeq=1001084480&print=print)

### [theme:secondary_battery] 2차전지·배터리
[대한민국 정책브리핑 이차전지 정책자료](https://www.korea.kr/news/policyNewsView.do?newsId=156689142)

### [theme:construction_machinery_infra] 건설·기계·인프라
[국가법령정보센터 건설산업기본법](https://www.law.go.kr/lsInfoP.do?ancYnChk=0&lsId=001808)

### [theme:automotive_mobility] 자동차·모빌리티
[한국교통안전공단 모빌리티지원센터](https://main.kotsa.or.kr/portal/contents.do?menuCode=12080100)

### [theme:business_groups] 그룹주
[국가법령정보센터 공정거래법 기업집단 정의](https://www.law.go.kr/LSW/lsSideInfoP.do?docCls=jo&joBrNo=00&joNo=0002&lsiSeq=285951&urlMode=lsScJoRltInfoR)

### [theme:energy_refining] 에너지·정유
[국가법령정보센터 에너지법 정의](https://www.law.go.kr/LSW/lsLawLinkInfo.do?chrClsCd=010202&lsJoLnkSeq=900473007)

### [theme:media_entertainment_gaming] 미디어·엔터·게임
[국가법령정보센터 게임산업진흥법](https://law.go.kr/LSW/lsInfoP.do?ancYnChk=0&lsId=010196)

### [theme:nuclear_power_grid] 원자력·전력
[전력거래소 전력시장 안내](https://www.kpx.or.kr/menu.es?mid=a10301010000)

### [theme:reit_real_estate] 리츠·부동산
[국토교통부 리츠정보시스템](https://reits.molit.go.kr/pub/intro/info/infoReits01?pmn=4)

### [theme:robotics] 로봇
[산업통상자원부 지능형로봇 기본계획](https://www.motir.go.kr/kor/article/ATCLc01b2801b/69079/view)

### [theme:bank_finance] 은행·금융
[금융위원회 금융기관 안내](https://www.fsc.go.kr/kids/kd020101)

### [theme:defense_space] 방산·우주
[방위사업청 방위산업발전 기본계획](https://www.dapa.go.kr/dapa/na/ntt/selectNttInfo.do?bbsId=243&menuId=757&nttSn=45959)

### [theme:consumer_food] 소비재·음식료
[S&P Dow Jones Indices GICS 소비재 분류](https://www.spglobal.com/spdji/en/landing/topic/gics/)

### [theme:gold_commodities] 금·원자재
[한국거래소 KRX금시장 안내](https://open.krx.co.kr/contents/OPN/01/01050201/OPN01050201.jsp)

### [theme:korea_value_up] 코리아밸류업
[한국거래소 기업 밸류업 안내](https://kind.krx.co.kr/valueup/intro.do?method=valueupIntroMain)

### [theme:esg] ESG
[한국거래소 ESG 포털](https://esg.krx.co.kr/contents/01/01010100/ESG01010100.jsp)

### [theme:steel_materials] 철강·소재
[대한민국 정책브리핑 철강산업 고도화 방안](https://www.korea.kr/news/policyNewsView.do?newsId=148953928)

### [theme:quantum_computing] 양자컴퓨팅
[NIST Quantum Computing Explained](https://www.nist.gov/quantum-information-science/quantum-computing-explained)

### [theme:metaverse] 메타버스
[국가법령정보센터 가상융합산업 진흥법](https://www.law.go.kr/lsInfoP.do?lsiSeq=260801)

### [theme:shipbuilding] 조선
[산업통상자원부 K-조선 미래비전](https://www.motir.go.kr/kor/article/ATCL3f49a5a8c/171828/view)

## 사용자 제공 조사 링크

- <https://chatgpt.com/share/6a5dbc76-9c4c-83ee-9b7f-7729b384befe> — 1~12번 테마 소개
- <https://chatgpt.com/share/6a5dbc89-8868-83ee-8d75-2f68d6e1bffc> — 13~23번 테마 소개
- <https://chatgpt.com/share/6a5d9df1-9eb0-83e8-a285-0d2aec036054> — 1~7번 테마 상세 조사
- <https://chatgpt.com/share/6a5dbc9e-9d78-83e8-bb9c-5c2007c15d35> — 8~16번 테마 상세 조사
- <https://chatgpt.com/share/6a5dbca9-74bc-83e8-9f83-7f105074a7be> — 17~23번 테마 상세 조사
