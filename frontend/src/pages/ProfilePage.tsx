export function ProfilePage() {
  return (
    <section>
      <h1 style={{ fontSize: 20 }}>프로필</h1>
      <p style={{ color: "#555555", lineHeight: 1.6 }}>
        투자성향 설문(<code>/engine/profile</code>, 금투협 5단계)과 시나리오
        계좌 선택이 들어오는 화면. 성향 밖 상품 제안은 차단된다.
      </p>
    </section>
  );
}
