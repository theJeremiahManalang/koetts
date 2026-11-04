"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

export function MangaShelf({
  id,
  title,
  subtitle,
  children,
}: {
  id: string;
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  const row = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: true, end: false });
  useEffect(() => {
    const element = row.current;
    if (!element) return;
    let target: number | null = null;
    const update = () => {
      if (target !== null && Math.abs(element.scrollLeft - target) <= 1)
        target = null;
      setEdges({
        start: element.scrollLeft <= 1,
        end:
          element.scrollLeft >= element.scrollWidth - element.clientWidth - 1,
      });
    };
    function wheel(event: WheelEvent) {
      if (
        !window.matchMedia("(hover: hover) and (pointer: fine)").matches ||
        event.ctrlKey ||
        event.shiftKey ||
        !event.cancelable ||
        Math.abs(event.deltaX) >= Math.abs(event.deltaY)
      ) {
        target = null;
        return;
      }
      const delta =
        event.deltaY *
        (event.deltaMode === 1
          ? 16
          : event.deltaMode === 2
            ? element!.clientWidth
            : 1);
      const max = element!.scrollWidth - element!.clientWidth;
      if (
        max <= 0 ||
        (delta > 0 && element!.scrollLeft >= max - 1) ||
        (delta < 0 && element!.scrollLeft <= 1)
      )
        return;
      event.preventDefault();
      // Accumulate wheel bursts against the destination, not the in-flight scroll position.
      target = Math.max(
        0,
        Math.min(max, (target ?? element!.scrollLeft) + delta),
      );
      element!.scrollTo({
        left: target,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
      update();
    }
    // React wheel handlers are passive; a local non-passive listener permits page-scroll handoff.
    element.addEventListener("wheel", wheel, { passive: false });
    element.addEventListener("scroll", update);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    update();
    return () => {
      observer.disconnect();
      element.removeEventListener("wheel", wheel);
      element.removeEventListener("scroll", update);
    };
  }, [children]);

  function move(direction: number) {
    const element = row.current;
    if (element)
      element.scrollBy({
        left: direction * element.clientWidth * 0.85,
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
          ? "instant"
          : "smooth",
      });
  }
  return (
    <section className="browse-shelf-section" aria-labelledby={`${id}-title`}>
      <div className="browse-section-heading [&>span]:text-[11px] [&>span]:text-[var(--muted)] [&>a]:text-[11px] [&>a]:text-[var(--muted)] mt-[34px] mr-0 mb-[18px] ml-0 flex items-end justify-between gap-[16px]">
        <div>
          <p className="browse-overline mt-0 mr-0 mb-[9px] ml-0 text-[9px] tracking-[1.8px] text-[var(--muted)]">
            {subtitle}
          </p>
          <h2
            className="m-0 text-[22px] font-[650] tracking-[-.6px]"
            id={`${id}-title`}
          >
            {title}
          </h2>
        </div>
        <div className="browse-shelf-controls [&_button:hover:not(:disabled)]:border-[var(--accent)] [&_button:hover:not(:disabled)]:text-[var(--accent)] flex gap-[8px]">
          <button
            className="size-[34px] rounded-[50%] border border-[var(--line)] bg-[var(--surface)]"
            type="button"
            aria-label={`Scroll ${title} left`}
            aria-controls={id}
            disabled={edges.start}
            onClick={() => move(-1)}
          >
            ←
          </button>
          <button
            className="size-[34px] rounded-[50%] border border-[var(--line)] bg-[var(--surface)]"
            type="button"
            aria-label={`Scroll ${title} right`}
            aria-controls={id}
            disabled={edges.end}
            onClick={() => move(1)}
          >
            →
          </button>
        </div>
      </div>
      <div
        ref={row}
        id={id}
        className="browse-shelf mt-[-5px] mr-[-4px] mb-0 ml-[-4px] grid auto-cols-[clamp(160px,18vw,220px)] grid-flow-col gap-[18px] overflow-x-auto px-[4px] pt-[5px] pb-[12px] [scrollbar-width:none] [@media(max-width:700px)]:auto-cols-[145px] [@media(hover:none),(pointer:coarse)]:[scroll-snap-type:x_proximity]"
        role="region"
        aria-label={`${title} manga`}
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.target !== event.currentTarget) return;
          if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
            event.preventDefault();
            move(event.key === "ArrowLeft" ? -1 : 1);
          }
        }}
      >
        {children}
      </div>
    </section>
  );
}
