import type { ReactNode } from "react";

type ChatIconName = "spark" | "send" | "book" | "database" | "chevron" | "shield" | "refresh" | "sun" | "chart" | "star" | "trash";

export function ChatIcon({ name, size = 20 }: { name: ChatIconName; size?: number }) {
  const paths: Record<ChatIconName, ReactNode> = {
    spark: <path d="M12 2l1.7 4.6L18 8.3l-4.3 1.7L12 14.5 10.3 10 6 8.3l4.3-1.7L12 2Zm6 10 .9 2.2L21 15l-2.1.8L18 18l-.9-2.2L15 15l2.1-.8L18 12ZM6 14l1.2 3.1L10 18.2l-2.8 1.1L6 22l-1.2-2.7L2 18.2l2.8-1.1L6 14Z" />,
    send: <path d="m21 3-7.6 18-4.2-7.1L2 9.7 21 3Zm0 0L9.2 13.9" />,
    book: <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 19.5A2.5 2.5 0 0 0 6.5 22H20V3H6.5A2.5 2.5 0 0 0 4 5.5v14Z" />,
    database: <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></>,
    chevron: <path d="m9 18 6-6-6-6" />,
    shield: <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Zm-3-10 2 2 4-4" />,
    refresh: <path d="M20 11a8.1 8.1 0 1 0 2 5M20 4v7h-7" />,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9 7 7M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1" /></>,
    chart: <><path d="M4 20V4M4 20h16" /><path d="m8 15 3-4 3 2 5-6" /></>,
    star: <path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9L12 3Z" />,
    trash: <path d="M4 7h16M9 7V4h6v3M7 7l1 14h8l1-14M10 11v6M14 11v6" />,
  };
  return <svg aria-hidden="true" viewBox="0 0 24 24" width={size} height={size}>{paths[name]}</svg>;
}
