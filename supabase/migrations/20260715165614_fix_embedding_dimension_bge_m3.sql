-- BGE-M3(1024차원) 확정에 따른 embedding 차원 고정 + ANN 인덱스 (아키텍처.md §10, 2026-07-15)
-- 기존 embedding 값은 전부 null이므로 타입 변경은 데이터 이동 없이 적용된다.

alter table public.knowledge_chunks
    alter column embedding type extensions.vector(1024)
    using embedding::extensions.vector(1024);

-- 코사인 거리(<=>) 기준 HNSW 인덱스. 코퍼스가 작아도 미리 만들어 두면
-- 이후 적재분부터 자동으로 인덱싱된다.
create index if not exists knowledge_chunks_embedding_hnsw_idx
    on public.knowledge_chunks
    using hnsw (embedding extensions.vector_cosine_ops);
