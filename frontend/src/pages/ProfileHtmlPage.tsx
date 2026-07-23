import { useEffect, useRef, type JSX } from "react";

interface ProfileHtmlPageProps {
  onBack: () => void;
}

export function ProfileHtmlPage({ onBack }: ProfileHtmlPageProps): JSX.Element {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const onBackRef = useRef(onBack);

  useEffect(() => {
    onBackRef.current = onBack;
  }, [onBack]);

  useEffect(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    let frameDocument: Document | null = null;
    const handleFrameClick = (event: Event): void => {
      const target = event.target as { closest?: (selector: string) => Element | null } | null;
      if (target?.closest?.("[data-profile-html-back]")) onBackRef.current();
    };
    const connectFrame = (): void => {
      frameDocument?.removeEventListener("click", handleFrameClick);
      frameDocument = iframe.contentDocument;
      frameDocument?.addEventListener("click", handleFrameClick);
    };

    iframe.addEventListener("load", connectFrame);
    if (iframe.contentDocument?.readyState === "complete") connectFrame();

    return () => {
      iframe.removeEventListener("load", connectFrame);
      frameDocument?.removeEventListener("click", handleFrameClick);
    };
  }, []);

  return (
    <iframe
      ref={iframeRef}
      src={`${import.meta.env.BASE_URL}profile-html/index.html`}
      style={{ border: 0, display: "block", height: "100vh", width: "100%" }}
      title="내 프로필"
    />
  );
}
