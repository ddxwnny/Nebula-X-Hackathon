import { useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";

export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, ReactNode> = {
    train: (
      <>
        <rect x="5" y="3" width="14" height="15" rx="4" />
        <path d="M5 11h14M9 18l-2 3m8-3 2 3M9 7h6" />
        <path d="M8 15h1m6 0h1" />
      </>
    ),
    pin: (
      <>
        <path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z" />
        <circle cx="12" cy="10" r="2" />
      </>
    ),
    arrow: <path d="M4 12h15m-6-6 6 6-6 6" />,
    swap: <path d="M8 3v17m-4-4 4 4 4-4M16 21V4m-4 4 4-4 4 4" />,
    location: (
      <>
        <circle cx="12" cy="12" r="6" />
        <circle cx="12" cy="12" r="2" />
        <path d="M12 2v4m0 12v4M2 12h4m12 0h4" />
      </>
    ),
    bell: (
      <>
        <path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5Zm5 3h4" />
      </>
    ),
    cloud: (
      <>
        <path d="M6 16a4 4 0 0 1-1-8 6 6 0 0 1 11-1 4.5 4.5 0 1 1 2 9H6Z" />
        <path d="m8 19-1 2m6-2-1 2m6-2-1 2" />
      </>
    ),
    walk: (
      <>
        <circle cx="13" cy="4" r="2" />
        <path d="m8 10 4-3 3 4 4 1m-7-5-2 8-4 6m4-6 5 1 2 5M8 10l-2 4" />
      </>
    ),
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 6v6l4 2" />
      </>
    ),
    close: <path d="m6 6 12 12M6 18 18 6" />,
    access: (
      <>
        <circle cx="12" cy="4" r="2" />
        <path d="M5 8h14m-7 0v6m0-2-5 9m5-9 5 9" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m8 5 7 7-7 7" />,
    bus: (
      <>
        <rect x="4" y="3" width="16" height="16" rx="3" />
        <path d="M4 11h16M8 19v2m8-2v2M8 15h1m6 0h1M8 7h8" />
      </>
    ),
    map: (
      <>
        <path d="m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2Zm6-2v16m6-14v16" />
      </>
    ),
    info: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 11v6m0-10v1" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] ?? paths.info}
    </svg>
  );
}
export function Loading({ children }: { children: ReactNode }) {
  return (
    <span className="loading" role="status">
      <span className="spinner" aria-hidden="true" />
      {children}
    </span>
  );
}
export function InfoCard({
  icon,
  title,
  children,
  tone = "",
}: {
  icon: string;
  title: string;
  children: ReactNode;
  tone?: string;
}) {
  return (
    <article className={`info-card ${tone}`}>
      <span className="card-icon">
        <Icon name={icon} />
      </span>
      <div>
        <h3>{title}</h3>
        {children}
      </div>
    </article>
  );
}
export function Announcement({ messages }: { messages: string[] }) {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [interacting, setInteracting] = useState(false);
  const [reduced, setReduced] = useState(
    () => window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const items = messages.slice(0, 5);
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(media.matches);
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (paused || interacting || reduced || items.length < 2) return;
    const timer = window.setInterval(
      () => setIndex((i) => (i + 1) % items.length),
      5000,
    );
    return () => window.clearInterval(timer);
  }, [paused, interacting, reduced, items.length]);
  if (!items.length) return null;
  const selected = index % items.length;
  return (
    <aside
      className="announcement"
      aria-label="Service announcements"
      onMouseEnter={() => setInteracting(true)}
      onMouseLeave={() => setInteracting(false)}
      onFocus={() => setInteracting(true)}
      onBlur={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget)) setInteracting(false);
      }}
    >
      <Icon name="info" size={17} />
      <span>{items[selected]}</span>
      {items.length > 1 && (
        <div className="announcement-controls">
          <button
            aria-label="Previous announcement"
            onClick={() =>
              setIndex((selected + items.length - 1) % items.length)
            }
          >
            ‹
          </button>
          <small>
            {selected + 1}/{items.length}
          </small>
          <button
            aria-label="Next announcement"
            onClick={() => setIndex((selected + 1) % items.length)}
          >
            ›
          </button>
          {!reduced && (
            <button
              onClick={() => setPaused(!paused)}
              aria-label={
                paused ? "Resume announcements" : "Pause announcements"
              }
            >
              {paused ? "▶" : "Ⅱ"}
            </button>
          )}
        </div>
      )}
    </aside>
  );
}

const SHEET_STOPS = [25, 60, 85];
const nearestStop = (value: number) =>
  SHEET_STOPS.reduce((best, stop) =>
    Math.abs(stop - value) < Math.abs(best - value) ? stop : best,
  );

export function SheetHandle({
  value,
  onChange,
  containerRef,
}: {
  value: number;
  onChange: (value: number) => void;
  containerRef: RefObject<HTMLElement | null>;
}) {
  const drag = useRef<{
    y: number;
    start: number;
    height: number;
    current: number;
  } | null>(null);
  const dragged = useRef(false);
  const clamp = (height: number) => Math.min(85, Math.max(25, height));
  return (
    <div
      className="sheet-handle"
      role="slider"
      tabIndex={0}
      aria-label="Journey panel size"
      aria-orientation="vertical"
      aria-valuemin={25}
      aria-valuemax={85}
      aria-valuenow={Math.round(value)}
      aria-valuetext={`${Math.round(value)} percent details. Drag up for more details or down for more map.`}
      onPointerDown={(event) => {
        if (event.button !== 0) return;
        const height = containerRef.current?.clientHeight;
        if (!height) return;
        drag.current = {
          y: event.clientY,
          start: value,
          height,
          current: value,
        };
        dragged.current = false;
        event.currentTarget.setPointerCapture(event.pointerId);
      }}
      onPointerMove={(event) => {
        if (!drag.current) return;
        const delta = drag.current.y - event.clientY;
        if (Math.abs(delta) > 3) dragged.current = true;
        if (!dragged.current) return;
        const next = clamp(
          drag.current.start + (delta / drag.current.height) * 100,
        );
        drag.current.current = next;
        onChange(next);
      }}
      onPointerUp={(event) => {
        if (!drag.current) return;
        if (dragged.current) onChange(nearestStop(drag.current.current));
        drag.current = null;
        event.currentTarget.releasePointerCapture(event.pointerId);
      }}
      onPointerCancel={() => {
        if (drag.current) onChange(nearestStop(drag.current.current));
        drag.current = null;
        dragged.current = true;
      }}
      onLostPointerCapture={() => {
        drag.current = null;
      }}
      onClick={() => {
        if (dragged.current) {
          dragged.current = false;
          return;
        }
        const next =
          SHEET_STOPS.find((stop) => stop > value + 1) ?? SHEET_STOPS[0];
        onChange(next);
      }}
      onKeyDown={(event) => {
        let next: number | undefined;
        if (event.key === "ArrowUp" || event.key === "ArrowRight")
          next = SHEET_STOPS.find((stop) => stop > value + 1) ?? 85;
        if (event.key === "ArrowDown" || event.key === "ArrowLeft")
          next =
            [...SHEET_STOPS].reverse().find((stop) => stop < value - 1) ?? 25;
        if (event.key === "Home") next = 25;
        if (event.key === "End") next = 85;
        if (event.key === "Enter" || event.key === " ")
          next = SHEET_STOPS.find((stop) => stop > value + 1) ?? 25;
        if (next !== undefined) {
          event.preventDefault();
          onChange(next);
        }
      }}
    >
      <span />
      <small>Drag to resize</small>
    </div>
  );
}
