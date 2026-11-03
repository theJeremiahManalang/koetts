"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

export function MangaShelf({ id, title, subtitle, children }: { id: string; title: string; subtitle: string; children: ReactNode }) {
  const row = useRef<HTMLDivElement>(null);
  const [edges, setEdges] = useState({ start: true, end: false });
  useEffect(() => {
    const element = row.current;
    if (!element) return;
    let target: number | null = null;
    const update = () => {
      if (target !== null && Math.abs(element.scrollLeft - target) <= 1) target = null;
      setEdges({ start: element.scrollLeft <= 1, end: element.scrollLeft >= element.scrollWidth - element.clientWidth - 1 });
    };
    function wheel(event: WheelEvent) {
      if (!window.matchMedia("(hover: hover) and (pointer: fine)").matches || event.ctrlKey || event.shiftKey || !event.cancelable || Math.abs(event.deltaX) >= Math.abs(event.deltaY)) { target = null; return; }
      const delta = event.deltaY * (event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? element!.clientWidth : 1);
      const max = element!.scrollWidth - element!.clientWidth;
      if (max <= 0 || (delta > 0 && element!.scrollLeft >= max - 1) || (delta < 0 && element!.scrollLeft <= 1)) return;
      event.preventDefault();
      // Accumulate wheel bursts against the destination, not the in-flight scroll position.
      target = Math.max(0, Math.min(max, (target ?? element!.scrollLeft) + delta));
      element!.scrollTo({ left: target, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
      update();
    }
    // React wheel handlers are passive; a local non-passive listener permits page-scroll handoff.
    element.addEventListener("wheel", wheel, { passive: false });
    element.addEventListener("scroll", update);
    const observer = new ResizeObserver(update);
    observer.observe(element);
    update();
    return () => { observer.disconnect(); element.removeEventListener("wheel", wheel); element.removeEventListener("scroll", update); };
  }, [children]);

  function move(direction: number) {
    const element = row.current;
    if (element) element.scrollBy({ left: direction * element.clientWidth * .85, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  }
  return <section className="browse-shelf-section" aria-labelledby={`${id}-title`}>
    <div className="browse-section-heading"><div><p className="browse-overline">{subtitle}</p><h2 id={`${id}-title`}>{title}</h2></div><div className="browse-shelf-controls"><button type="button" aria-label={`Scroll ${title} left`} aria-controls={id} disabled={edges.start} onClick={() => move(-1)}>←</button><button type="button" aria-label={`Scroll ${title} right`} aria-controls={id} disabled={edges.end} onClick={() => move(1)}>→</button></div></div>
    <div ref={row} id={id} className="browse-shelf" role="region" aria-label={`${title} manga`} tabIndex={0} onKeyDown={event => {
      if (event.target !== event.currentTarget) return;
      if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); move(event.key === "ArrowLeft" ? -1 : 1); }
    }}>{children}</div>
  </section>;
}
