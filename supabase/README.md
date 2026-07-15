# Supabase 원격 프로젝트

이 저장소의 Supabase 원격 작업 대상은 아래 프로젝트로 고정한다.

- 조직: `jyleo2k2's Org`
- 프로젝트: `KDA-securities`
- 프로젝트 참조값: `fdltrpabebayuwcnqqfy`
- 프로젝트 URL: `https://fdltrpabebayuwcnqqfy.supabase.co`
- 리전: `ap-south-1`

## 작업 규칙

- Supabase MCP 작업에는 `project_id="fdltrpabebayuwcnqqfy"`를 명시한다.
- 원격 스키마 변경은 반드시 `supabase/migrations/`의 마이그레이션으로 관리한다.
- 스키마 변경 전후 대상 프로젝트와 보안·성능 Advisor 결과를 확인한다.
- DB 비밀번호, Secret/Service Role 키 등 시크릿은 Git에 기록하지 않는다.
- `supabase/config.toml`의 `project_id`는 로컬 개발 인스턴스 식별자이므로 원격 프로젝트 참조값으로 사용하지 않는다.
