import { useEffect, useRef, type JSX } from "react";
import { useNavigate } from "react-router-dom";

/**
 * 사용자가 제공한 슬랑이 HTML을 React 라우트 안에서 원형 그대로 표시한다.
 * 화면의 스타일·상호작용은 정적 HTML이 전적으로 소유한다.
 */
export function SlangiTouchPage(): JSX.Element {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    function handleMessage(event: MessageEvent): void {
      if (
        event.source !== iframeRef.current?.contentWindow
        || event.origin !== window.location.origin
      ) return;
      if ((event.data as { type?: string } | null)?.type === "slangi-back") {
        navigate("/main-home");
      }
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [navigate]);

  return (
    <iframe
      ref={iframeRef}
      src={`${import.meta.env.BASE_URL}slangi/index.html`}
      style={{ border: 0, display: "block", height: "100vh", width: "100%" }}
      title="연그미를 만져 보세요"
    />
  );
}
