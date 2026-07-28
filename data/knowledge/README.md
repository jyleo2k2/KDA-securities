# 승인 RAG 코퍼스 운영

RAG 전용 복사본을 따로 두지 않는다. 사용자 대상 원문은
`docs/20_리서치`, `docs/40_규제`에 두고,
`approved_documents.json`을 단일 승인 목록으로 사용한다.

## 현재 운영 상태 (2026-07-28)

- PR #56으로 거버넌스 스키마 v2와 공식 문서 5종을 main에 반영했다.
- 로컬 승인 매니페스트는 문서 16개·청크 69개다. 원격 실제 문서·청크 수는
  적재 후 DB 조회로 별도 확인하며 로컬 수치를 원격 수치로 간주하지 않는다.
- 원격 `knowledge_chunks.embedding`은 `vector(1024)`이며 HNSW 인덱스가 적용돼 있다.
- 문서별 대표 질의 18케이스는 로컬 Hit@5=1·Hit@1=1·MRR@5=1을 통과했다.
- `uv run python scripts/ingest_knowledge.py --validate-only`는 PR과 `main` push CI에서 실행된다.
- 매주 월요일 09:15 KST에 `rag-governance.yml`이 검토기한과 공식 출처 60개의
  정규화 지문을 점검한다. 변경·조회실패·검토 임박/만료가 있으면 GitHub 이슈를
  생성하거나 갱신하며 문서와 엔진 규칙은 자동 변경하지 않는다.

## 역할

- 자동화: 스키마, 공식 출처 도메인, SHA-256, 개인정보, 숨은 제어문구,
  검토 기한을 로더와 CI가 검사한다.
- 사람(`project_owner`): 공식 페이지를 읽고 내용 변경 여부와 서비스 설명 범위를
  판단한다. 자동화가 법령의 의미 변화까지 대신 판단하지 않는다.

규제·세금·공식 안내 문서는 확인일부터 최대 90일, 리서치 문서는 최대 180일 안에
다시 검토한다. `review_due_date`가 지나면 로컬 로딩, CI, 원격 적재가 모두 실패한다.

## 등록과 갱신

1. 허용 루트에 출처 링크와 기준일이 명확한 Markdown 후보를 작성한다.
2. 공식 페이지와 문장을 대조하고 개인정보·내부 전략·목데이터가 없는지 사람이
   확인한다.
3. 매니페스트 v2 메타데이터와 UTF-8 `.strip()` 기준 SHA-256을 등록한다.
4. `uv run python scripts/ingest_knowledge.py --validate-only`와 검색 품질 테스트를
   통과시킨다.
5. PR 리뷰 후 원격 적재와 임베딩을 실행한다.

정기 검토에서 내용이 같으면 `verified_at`, `review_due_date`만 갱신한다. 내용이
달라졌으면 Markdown, `as_of_date`, SHA-256, 질문 벤치마크를 함께 갱신한다.
근거를 확인할 수 없거나 범위가 애매하면 승인 목록에서 제거해 검색 대상에서
제외한다.

## 검토 일정

| 검토 기한 | 문서 ID |
|---|---|
| 2026-10-14 | `default-option`, `pension-tax-credit` |
| 2026-10-16 | `pension-deposit-protection`, `pension-receipt-taxation`, `retirement-pension-in-kind-transfer` |
| 2026-10-18 | `retirement-benefit-irp-transfer-exceptions`, `retirement-pension-participant-education`, `retirement-pension-receipt-withdrawal`, `retirement-pension-unpaid-contributions`, `small-business-retirement-pension-fund` |
| 2027-01-12 | `pension-basics`, `provider-disclosure-reading` |
| 2027-01-14 | `etf-comparison-metrics`, `retirement-pension-2025-performance` |
| 2027-01-16 | `etf-theme-23-approved-basis` |
| 2027-01-17 | `approved-etf-product-database` |

가장 가까운 기한은 2026-10-14다. 정기 실행은 검토 신호만 만들며,
`project_owner`가 공식 원문을 대조하고 갱신 PR에서 `--validate-only` 결과를
확인해야 한다. 세금·한도 등 계산 규칙에 영향이 있으면 RAG 문서만 바꾸지 않고
규칙 엔진 버전과 골든 테스트를 같은 변경에서 갱신한다.

## 원격 동기화와 복구

승인 후 다음 순서로 실행한다.

```powershell
uv run python scripts/ingest_knowledge.py
uv run --group embeddings python scripts/embed_knowledge_chunks.py
uv run --group embeddings python scripts/measure_search_quality.py
```

원격 적재는 문서·청크를 갱신하고 변경된 청크의 임베딩만 비운다. 임베딩 작업이
그 청크만 다시 계산한다. 잘못된 변경은 이전 커밋의 원문과 매니페스트를 복원한 뒤
같은 순서로 재적재한다.
