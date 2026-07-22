# 연금 코파일럿 — 데이터 ERD / 구조도 (Appendix)

> 작성일: 2026-07-22 · Supabase PostgreSQL public 스키마(49개 기본 테이블, 마이그레이션 27개) 기준.
> 근거: `supabase/migrations/*` 실제 정의. 모든 public 테이블은 RLS 활성화, 내부 전용 테이블은 `service_role`만 grant.
> 가독성을 위해 논리 그룹별로 분할했다. 컬럼은 대표 키·식별자 위주로 축약(전체 컬럼은 마이그레이션 SQL 참조).

---

## 1. 전체 그룹 지도

```mermaid
flowchart TB
    G1["① 출처·수집\ndata_sources · ingestion_runs"]
    G2["② 기관·공시\nfinancial_institutions · *_provider_stats"]
    G3["③ 목데이터·목계좌\nmock_scenarios · mock_accounts · mock_holdings"]
    G4["④ 사용자 도메인(Auth)\nuser_profiles · pension_accounts · 성향진단"]
    G5["⑤ 규칙·감사\nrule_sets · pension_rules · engine_runs"]
    G6["⑥ RAG·콘텐츠\nknowledge_documents · chunks · news_items"]
    G7["⑦ 챗봇\nchat_sessions · chat_messages · evidence"]
    G8["⑧ ETF 유니버스·시장\netf_universe_products · etf_return_histories · etf_daily_market_snapshots"]

    G1 --> G2
    G1 --> G6
    G1 --> G8
    G3 --> G5
    G4 --> G5
    G5 --> G7
    G6 --> G7
```

---

## 2. 출처·수집 + 기관·공시

```mermaid
erDiagram
    data_sources ||--o{ ingestion_runs : "수집 이력"
    data_sources ||--o{ pension_savings_provider_stats : source_id
    data_sources ||--o{ retirement_provider_stats : source_id
    financial_institutions ||--o{ institution_aliases : "별칭"
    financial_institutions ||--o{ pension_savings_provider_stats : institution_id
    financial_institutions ||--o{ retirement_provider_stats : institution_id

    data_sources {
        bigint id PK
        text code UK
        text authority
        text base_url
    }
    ingestion_runs {
        uuid id PK
        bigint source_id FK
        text status
        int fetched_count
    }
    financial_institutions {
        bigint id PK
        text name
        text institution_type
    }
    pension_savings_provider_stats {
        bigint id PK
        bigint institution_id FK
        numeric reserve
        numeric return_rate
    }
    retirement_provider_stats {
        bigint id PK
        bigint institution_id FK
        text account_type
    }
```

---

## 3. 목데이터·목계좌 + 공개 포트폴리오

```mermaid
erDiagram
    mock_scenarios ||--o{ mock_accounts : "계좌 3종"
    mock_accounts ||--o{ mock_holdings : "보유"
    asset_classes ||--o{ mock_holdings : asset_class_id
    mock_public_profiles ||--o{ mock_public_portfolios : "공개 포트폴리오"
    mock_public_portfolios ||--o{ mock_public_portfolio_holdings : "구성"

    mock_scenarios {
        bigint id PK
        text scenario_code UK
        text risk_profile
        int age
    }
    mock_accounts {
        bigint id PK
        bigint scenario_id FK
        text account_type "dc/irp/pension_savings"
    }
    mock_holdings {
        bigint id PK
        bigint account_id FK
        bigint asset_class_id FK
        numeric weight
    }
    asset_classes {
        bigint id PK
        text code UK
    }
```

---

## 4. 사용자 도메인 (Auth 연동 · 성향진단)

```mermaid
erDiagram
    user_profiles ||--o{ pension_accounts : "소유(owner_id=auth.uid)"
    pension_accounts ||--o{ account_snapshots : "시점 스냅샷"
    pension_accounts ||--o{ account_cash_flows : "현금흐름"
    account_snapshots ||--o{ account_holding_snapshots : "보유 스냅샷"
    financial_products ||--o{ account_holding_snapshots : product_id
    profile_question_sets ||--o{ profile_questions : "문항"
    profile_questions ||--o{ profile_question_options : "선택지"
    investment_profile_assessments ||--o{ investment_profile_answers : "응답"
    investment_profile_assessments ||--o| investment_profile_confirmations : "확인 이력"

    user_profiles {
        uuid id PK "auth.users 참조"
    }
    pension_accounts {
        uuid id PK
        uuid owner_id FK
        text account_type
        bigint institution_id FK
    }
    account_snapshots {
        uuid id PK
        uuid account_id FK
        date as_of
    }
    investment_profile_assessments {
        uuid id PK
        uuid owner_id
        text risk_profile
        date assessed_on
    }
    investment_profile_confirmations {
        uuid id PK
        uuid assessment_id FK "unique"
    }
```

> 규칙: 소유자 정책 `(select auth.uid()) = owner_id`, real/mock 상호배타 CHECK. 목데이터는 여전히 `mock_scenarios` 계열이 SSOT(신규 사용자 테이블은 병행).

---

## 5. 규칙·감사 + 챗봇

```mermaid
erDiagram
    rule_sets ||--o{ pension_rules : "버전 규칙"
    rule_sets ||--o{ engine_runs : rule_set_id
    pension_rules ||--o{ engine_runs : rule_id
    engine_runs ||--o{ engine_run_evidence : "근거"
    chat_sessions ||--o{ chat_messages : "메시지"
    chat_messages ||--o{ chat_message_evidence : "근거 연결"
    engine_runs ||--o{ chat_message_evidence : engine_run_id
    knowledge_chunks ||--o{ chat_message_evidence : chunk_id
    news_items ||--o{ chat_message_evidence : news_item_id

    rule_sets {
        bigint id PK
        text version
    }
    pension_rules {
        bigint id PK
        bigint rule_set_id FK
        numeric limit_percent "70.00"
    }
    engine_runs {
        uuid id PK
        bigint rule_set_id FK
        uuid owner_id
        jsonb inputs
        jsonb outputs
    }
    chat_sessions {
        uuid id PK
        uuid owner_id
    }
    chat_messages {
        uuid id PK
        uuid session_id FK
        text role
        jsonb payload "schema_version=1"
    }
    chat_message_evidence {
        uuid id PK
        uuid message_id FK
    }
```

---

## 6. RAG·콘텐츠 + ETF 유니버스·시장

```mermaid
erDiagram
    knowledge_documents ||--o{ knowledge_chunks : "청킹"
    data_sources ||--o{ knowledge_documents : source_id
    data_sources ||--o{ news_items : source_id
    etf_dataset_versions ||--o{ etf_universe_products : "버전 상품"
    etf_dataset_versions ||--o{ etf_return_histories : "총수익 이력"

    knowledge_documents {
        uuid id PK
        text title
        text doc_type
    }
    knowledge_chunks {
        bigint id PK
        uuid document_id FK
        vector embedding "1024 · HNSW"
        boolean is_active
    }
    news_items {
        uuid id PK
        text market_region
        vector selection_embedding "1024"
        jsonb summary_lines
    }
    etf_universe_products {
        bigint id PK
        bigint version_id FK
        text account_type
        jsonb payload
    }
    etf_return_histories {
        bigint id PK
        bigint version_id FK
        date as_of
        numeric total_return_index
    }
    etf_daily_market_snapshots {
        date base_date PK
        text isu_code PK
        numeric trade_value
        numeric nav
    }
```

---

## 7. 원격 주요 행 수 (2026-07-21 기준, `supabase/DB_HANDOFF.md`)

| 테이블 | 행 수 |
|---|---:|
| pension_savings_provider_stats | 88 |
| retirement_provider_stats | 126 |
| financial_institutions | 102 |
| knowledge_documents / 활성 임베딩 chunks | 15 / 56 |
| news_items | 15 |
| etf_daily_market_snapshots | 1,147 |
| etf_theme_content_reviews / evidence | 230 / 230 |
| mock_scenarios / accounts / holdings | 6 / 13 / 86 |
| benchmark_mock_users / accounts / holdings | 10,000 / 16,900 / 79,381 |
| profile_question_sets / questions / options | 1 / 6 / 30 |

> ETF 유니버스 원격 적재: 상품 2,507행(DC 823·IRP 823·연금저축 861), 총수익 이력 217,833행(기준일 2026-07-16).
