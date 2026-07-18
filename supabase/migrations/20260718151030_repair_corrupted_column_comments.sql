comment on column public.pension_savings_provider_stats.fee_rate_1y is
    'FSS psCorpList feeRate1: 과거 1년 수수료율. 당기 수수료율로 해석하지 않는다.';
comment on column public.retirement_provider_stats.response_division is
    'FSS rpCorpResultList 실제 응답의 division 필드. 공식 문서의 sysType 응답 표기와 다르다.';
comment on column public.knowledge_chunks.embedding is
    '검증된 공식 지식 청크의 BGE-M3 1024차원 임베딩. 코사인 거리 HNSW 인덱스로 의미 검색에 사용한다.';
