import { useEffect, useRef, type JSX } from "react";

import "./UserPickBenchmarkScreen.css";

interface UserPickBenchmarkScreenProps {
  onBack: () => void;
}

// 상세 화면의 뒤로가기는 iframe 내부에서 목록으로 복귀한다(closeDetail).
// 목록 화면의 뒤로가기만 이 메시지로 부모에게 홈 이탈을 요청한다.
export function UserPickBenchmarkScreen({ onBack }: UserPickBenchmarkScreenProps): JSX.Element {
  const onBackRef = useRef(onBack);
  useEffect(() => { onBackRef.current = onBack; }, [onBack]);

  const iframeRef = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    function handleMessage(event: MessageEvent): void {
      if (event.source !== iframeRef.current?.contentWindow) return;
      if ((event.data as { type?: string } | null)?.type === "benchmark-html-back") onBackRef.current();
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  return (
    <main className="benchmark-html-stage">
      <section className="benchmark-html-frame-wrap" aria-label="투자 벤치마킹하기">
        <iframe
          ref={iframeRef}
          className="benchmark-html-frame"
          src="/benchmark-html/투자 벤치마킹.dc.html"
          title="투자 벤치마킹하기"
        />
      </section>
    </main>
  );
}
