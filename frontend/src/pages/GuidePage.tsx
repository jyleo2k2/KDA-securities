export function GuidePage() {
  return (
    <section>
      <h1 style={{ fontSize: 20 }}>연금가이드</h1>
      <p style={{ color: "#555555", lineHeight: 1.6 }}>
        상품 설명·비교 챗봇 화면. 챗봇 백엔드는 별도 브랜치(chatbot-mvp)에서
        병합 예정이며, 성향·시뮬레이션 도구는 <code>/engine/profile</code>·
        <code>/engine/simulation</code>·<code>/engine/allocation-example</code>
        을 사용한다. 모든 수치에는 출처 칩이 붙는다.
      </p>
    </section>
  );
}
