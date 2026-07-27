# 이용자 Pick 팔로우 저장 계약

## 목적

이용자 Pick 포트폴리오의 하트 선택을 인증 이용자별로 저장하고, 모든 이용자의
팔로우 행을 합산한 수를 목록과 상세 화면에 동일하게 표시한다.

## 데이터 계약

- `benchmark_follow_targets`: 화면에 공개되는 포트폴리오 식별자, 서비스 도입 전
  기준 팔로우 수, 표시 순서를 보관한다.
- `user_benchmark_portfolio_follows`: `(owner_id, portfolio_id)`를 기본키로 사용한다.
  같은 이용자가 같은 포트폴리오를 중복 팔로우할 수 없다.
- 표시 팔로우 수는 `initial_follow_count + 저장된 팔로우 행 수`로 계산한다.
- 팔로우 해제는 해당 이용자의 행만 삭제한다.
- 두 테이블은 브라우저에서 직접 접근하지 않고 인증을 검증하는 FastAPI를 거친다.

## REST 계약

### `GET /me/benchmark-follows`

로그인 이용자에게 전체 팔로우 대상의 현재 상태를 표시 순서대로 반환한다.

```json
[
  {
    "portfolio_id": "꾸준한거북이",
    "follow_count": 1204,
    "is_following": false
  }
]
```

### `PUT /me/benchmark-follows/{portfolio_id}`

요청 본문:

```json
{
  "following": true
}
```

동일한 요청을 반복해도 결과가 바뀌지 않는 멱등 계약이다. 성공 시 해당
포트폴리오의 최신 누적 수와 현재 이용자의 팔로우 여부를 반환한다.

## 보안

- 두 엔드포인트 모두 유효한 Supabase Auth access token이 필요하다.
- `owner_id`는 요청 본문이 아니라 검증된 access token에서만 가져온다.
- DB 테이블은 RLS를 활성화하고 `anon`·`authenticated`의 직접 권한을 회수한다.
- FastAPI 서버의 DB 역할만 읽기·쓰기를 수행한다.
