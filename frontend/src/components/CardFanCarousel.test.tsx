// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CardFanCarousel, type CardFanCarouselItem } from "./CardFanCarousel";

const ITEMS: CardFanCarouselItem[] = [
  { id: "one", imageSrc: "/one.jpg", imageAlt: "첫 번째 풍경" },
  { id: "two", imageSrc: "/two.jpg", imageAlt: "두 번째 풍경" },
  { id: "three", imageSrc: "/three.jpg", imageAlt: "세 번째 풍경" },
];

afterEach(cleanup);

describe("CardFanCarousel", () => {
  it("moves with arrows and wraps at both ends", () => {
    const onIndexChange = vi.fn();
    render(<CardFanCarousel items={ITEMS} onIndexChange={onIndexChange} />);

    expect(screen.getByRole("button", { name: "1번째 카드 보기" })).toHaveAttribute("aria-current", "true");

    fireEvent.click(screen.getByRole("button", { name: "다음 카드" }));
    expect(screen.getByRole("button", { name: "2번째 카드 보기" })).toHaveAttribute("aria-current", "true");

    fireEvent.click(screen.getByRole("button", { name: "이전 카드" }));
    fireEvent.click(screen.getByRole("button", { name: "이전 카드" }));
    expect(screen.getByRole("button", { name: "3번째 카드 보기" })).toHaveAttribute("aria-current", "true");
    expect(onIndexChange).toHaveBeenLastCalledWith(2);
  });

  it("supports keyboard navigation and direct dot selection", () => {
    render(<CardFanCarousel items={ITEMS} ariaLabel="여행 사진" />);

    const carousel = screen.getByRole("region", { name: "여행 사진" });
    fireEvent.keyDown(carousel, { key: "ArrowRight" });
    expect(screen.getByRole("button", { name: "2번째 카드 보기" })).toHaveAttribute("aria-current", "true");

    fireEvent.click(screen.getByRole("button", { name: "3번째 카드 보기" }));
    expect(screen.getByText("3개 중 3번째 카드, 세 번째 풍경")).toBeInTheDocument();
  });

  it("changes cards after a horizontal swipe", () => {
    render(<CardFanCarousel items={ITEMS} />);

    const stage = document.querySelector(".card-fan-carousel__stage");
    expect(stage).not.toBeNull();

    fireEvent.pointerDown(stage!, { clientX: 160, pointerId: 1 });
    fireEvent.pointerUp(stage!, { clientX: 80, pointerId: 1 });

    expect(screen.getByRole("button", { name: "2번째 카드 보기" })).toHaveAttribute("aria-current", "true");
  });

  it("renders nothing when no cards are provided", () => {
    const { container } = render(<CardFanCarousel items={[]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
