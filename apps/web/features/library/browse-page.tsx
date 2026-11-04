"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AccountNav } from "../identity/account-nav";
import { useAuth } from "../identity/auth-provider";
import {
  manga,
  browseShelves,
  type DemoManga,
  type DemoChapter,
} from "../temp-data/manga";
import "./browse.css";
import { RequestPreviewModal } from "./request-preview-modal";
import { MangaShelf } from "./manga-shelf";

function Cover({ title }: { title: string }) {
  return (
    <div
      className="browse-cover flex aspect-[2/3] flex-col justify-between overflow-hidden rounded-[8px] border border-[#496158] bg-[#293d38] p-[15px] text-left text-[#c6d9d3]"
      aria-hidden="true"
    >
      <span className="text-[7px] leading-[1.5] tracking-[1.5px]">
        KOETTS · AUDIO EDITION
      </span>
      <svg
        className="m-auto w-[35%] opacity-[.65]"
        viewBox="0 0 48 48"
        fill="none"
      >
        <path
          d="M10 27v-5a14 14 0 0 1 28 0v5M10 25H7v13h8V25h-5Zm28 0h3v13h-8V25h5Z"
          stroke="currentColor"
          strokeWidth="2"
        />
      </svg>
      <strong className="mb-[18px] text-[clamp(16px,1.5vw,23px)] font-normal leading-[1.15] [font-family:Georgia,serif] [overflow-wrap:anywhere] [@media(max-width:700px)]:text-[20px]">
        {title}
      </strong>
      <span className="text-[7px] leading-[1.5] tracking-[1.5px]">
        A STORY WORTH HEARING
      </span>
    </div>
  );
}

export default function BrowsePage() {
  const { user, loading } = useAuth();
  const [requestOpen, setRequestOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [genre, setGenre] = useState("All stories");
  const [selected, setSelected] = useState<DemoManga | null>(null);
  const [chapter, setChapter] = useState<{
    manga: DemoManga;
    chapter: DemoChapter;
  } | null>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<HTMLButtonElement | null>(null);
  const featured = manga[0];
  const genres = [
    "All stories",
    ...new Set(manga.flatMap((item) => item.genres)),
  ];
  const visible = manga.filter(
    (item) =>
      (genre === "All stories" || item.genres.includes(genre)) &&
      [item.title, item.author, ...item.genres]
        .join(" ")
        .toLowerCase()
        .includes(query.trim().toLowerCase()),
  );

  function openDetails(item: DemoManga, button: HTMLButtonElement) {
    opener.current = button;
    setSelected(item);
  }
  function closeDetails() {
    setSelected(null);
  }
  useEffect(() => {
    if (selected) closeButton.current?.focus();
    else opener.current?.focus();
  }, [selected]);
  useEffect(() => {
    if (!user) {
      setSelected(null);
      setChapter(null);
    }
  }, [user]);

  function card(item: DemoManga, rank?: number) {
    return (
      <button
        type="button"
        className="browse-card [&:hover_.browse-cover]:border-[var(--accent)] [&:hover_.browse-cover]:bg-[#324d43] [&[aria-pressed=true]_.browse-cover]:border-[var(--accent)] [&[aria-pressed=true]_.browse-cover]:bg-[#324d43] [&:hover_.browse-card-arrow]:opacity-100 [&:focus-visible_.browse-card-arrow]:opacity-100 [&[aria-pressed=true]_.browse-card-arrow]:opacity-100 min-w-0 self-start snap-start rounded-[8px] border-none bg-transparent p-0 text-left"
        key={item.id}
        aria-label={`View ${item.title}`}
        aria-pressed={selected?.id === item.id}
        onClick={(event) => openDetails(item, event.currentTarget)}
      >
        <div className="browse-card-art [&:has(.browse-rank)_.browse-cover>span:first-child]:invisible relative">
          {rank && (
            <span
              className="browse-rank absolute top-[10px] left-[10px] z-[1] grid h-[38px] min-w-[38px] place-items-center rounded-[8px] bg-[var(--accent)] px-[6px] py-0 text-[24px] font-extrabold text-[#102c27] shadow-[0_2px_12px_#0004]"
              aria-label={`Rank ${rank}`}
            >
              {rank}
            </span>
          )}
          <Cover title={item.title} />
          <span
            className="browse-card-arrow absolute right-[12px] bottom-[12px] grid size-[30px] place-items-center rounded-[50%] bg-[var(--accent)] text-[#102c27] opacity-0"
            aria-hidden="true"
          >
            ↗
          </span>
        </div>
        <strong className="mt-[12px] mr-0 mb-[5px] ml-0 block text-[13px] leading-[1.4]">
          {item.title}
        </strong>
        <span className="block text-[10px] leading-[1.6] text-[var(--muted)]">
          {item.genres.join(" · ")}
        </span>
        <small className="block text-[10px] leading-[1.6] mt-[4px] text-[#81b6a8]">
          {item.chapters.length} audio{" "}
          {item.chapters.length === 1 ? "chapter" : "chapters"}
        </small>
      </button>
    );
  }

  return (
    <div
      className="browse-preview min-h-dvh bg-[var(--paper)] pb-[110px] text-[var(--ink)] [color-scheme:dark] [font-family:Arial,Helvetica,sans-serif]"
      onKeyDown={(event) => {
        if (event.key === "Escape" && selected && !requestOpen) {
          event.stopPropagation();
          closeDetails();
        }
      }}
    >
      <RequestPreviewModal
        key={user?.uid ?? "guest"}
        open={requestOpen}
        signedIn={!!user}
        onDismiss={() => setRequestOpen(false)}
      />
      <header className="browse-topbar flex min-h-[86px] items-center gap-[32px] border-b border-[var(--line)] px-[32px] py-[18px] [@media(max-width:1100px)]:gap-[16px] [@media(max-width:1100px)]:px-[20px] [@media(max-width:700px)]:flex-wrap [@media(max-width:700px)]:gap-[14px] [@media(max-width:700px)]:p-[16px]">
        <Link
          href="/browse"
          className="browse-brand flex items-center gap-[12px] text-[23px] font-[750] tracking-[-.7px] [@media(max-width:1100px)]:text-[20px]"
        >
          <span
            className="grid size-[40px] place-items-center rounded-[12px] bg-[var(--accent)] text-[#102c27]"
            aria-hidden="true"
          >
            ♫
          </span>
          <div>
            KoeTTS
            <small className="mt-[5px] block text-[8px] tracking-[1.7px] text-[var(--muted)]">
              MANGA, WITH A VOICE
            </small>
          </div>
        </Link>
        <nav
          className="browse-links [&_a[aria-current]]:bg-[#25312f] [&_a[aria-current]]:text-[var(--accent)] [&_a:hover]:bg-[#25312f] [&_a:hover]:text-[var(--accent)] [&_button:hover]:bg-[#25312f] [&_button:hover]:text-[var(--accent)] flex gap-[8px] text-[13px] [@media(max-width:700px)]:gap-0"
          aria-label="Library navigation"
        >
          <Link
            className="rounded-[24px] px-[17px] py-[10px] text-[var(--muted)] [@media(max-width:700px)]:px-[10px] [@media(max-width:700px)]:py-[8px]"
            href="/browse"
            aria-current="page"
          >
            Browse
          </Link>
          <button
            className="rounded-[24px] border-none bg-transparent px-[17px] py-[10px] text-[13px]! text-[var(--muted)] [@media(max-width:700px)]:px-[10px] [@media(max-width:700px)]:py-[8px]"
            type="button"
            onClick={() => setRequestOpen(true)}
          >
            Request
          </button>
        </nav>
        <label className="browse-search [&>span:first-child]:text-[23px] [&>span:first-child]:text-[var(--muted)] ml-auto flex w-[min(360px,30vw)] items-center gap-[9px] rounded-[24px] border border-[var(--line)] bg-[var(--surface)] px-[15px] py-0 [@media(max-width:700px)]:order-4 [@media(max-width:700px)]:w-full">
          <span aria-hidden="true">⌕</span>
          <span className="visually-hidden">
            Search manga, authors, or genres
          </span>
          <input
            type="search"
            placeholder="Search manga, authors, or genres"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <AccountNav />
      </header>
      <div
        className={`browse-workspace grid grid-cols-[minmax(0,1fr)] [&.has-details]:grid-cols-[minmax(0,1fr)_360px] [@media(max-width:1100px)]:[&.has-details]:grid-cols-[minmax(0,1fr)] [@media(max-width:1100px)]:[&.has-details_.browse-discovery]:hidden ${selected && user ? " has-details" : ""}`}
      >
        <main className="browse-discovery m-0! min-w-0 max-w-none! px-[32px]! pt-[28px]! pb-0! [@media(min-width:1600px)]:px-[48px]! [@media(max-width:700px)]:px-[16px]! [@media(max-width:700px)]:pt-[20px]!">
          <div className="browse-section-label mb-[22px] flex items-center justify-between gap-[12px] text-[9px] tracking-[1.7px] text-[var(--muted)] [@media(max-width:700px)]:flex-wrap">
            <span>YOUR NEXT WORLD AWAITS</span>
            <span className="browse-demo rounded-[20px] border border-[var(--line)] px-[10px] py-[6px] text-[10px] tracking-normal">
              Demo collection · UI preview
            </span>
          </div>
          {loading ? (
            <p role="status">Checking your account…</p>
          ) : !user ? (
            <section className="browse-empty rounded-[14px] border border-dashed border-[var(--line)] px-[20px] py-[60px] text-center">
              <h1>Stories worth listening to.</h1>
              <p className="mt-[16px] mr-0 mb-[24px] ml-0 text-[13px] text-[var(--muted)]">
                Sign in to explore the manga audiobook collection.
              </p>
              <Link
                href="/login"
                className="browse-primary inline-flex items-center justify-center gap-[24px] rounded-[24px] border-none bg-[var(--accent)] px-[20px] py-[12px] text-[12px]! font-bold! text-[#102c27] [&:hover:not(:disabled)]:bg-[#8cebd7]"
              >
                Sign in
              </Link>
            </section>
          ) : (
            <>
              <section
                className="browse-hero relative flex items-center gap-[32px] overflow-hidden rounded-[16px] border border-[#30443e] bg-[linear-gradient(115deg,#223b34,#192724_65%,#151d20)] p-[28px] [@media(max-width:700px)]:items-start [@media(max-width:700px)]:gap-[18px] [@media(max-width:700px)]:p-[22px]"
                aria-labelledby="featured-title"
              >
                <div className="browse-hero-cover [@media(max-width:700px)]:[&_.browse-cover]:p-[8px] [@media(max-width:700px)]:[&_.browse-cover>span]:text-[5px] [@media(max-width:700px)]:[&_.browse-cover>span]:tracking-[.3px] [@media(max-width:700px)]:[&_.browse-cover_strong]:mb-[5px] [@media(max-width:700px)]:[&_.browse-cover_strong]:text-[13px] w-[155px] shrink-0 [@media(max-width:700px)]:w-[85px]">
                  <Cover title={featured.title} />
                </div>
                <div className="browse-hero-copy [@media(max-width:700px)]:[&_.browse-overline]:hidden relative z-[1] max-w-[640px] [@media(max-width:700px)]:min-w-0">
                  <span className="browse-tag mb-[20px] inline-block rounded-[20px] bg-[#204139] px-[10px] py-[7px] text-[9px] tracking-[1px] text-[var(--accent)] [@media(max-width:700px)]:mb-[13px] [@media(max-width:700px)]:text-[7px]">
                    ♫ FEATURED AUDIOBOOK
                  </span>
                  <p className="browse-overline mt-0 mr-0 mb-[9px] ml-0 text-[9px] tracking-[1.8px] text-[var(--muted)]">
                    LET THE STORY FIND YOU
                  </p>
                  <h1 id="featured-title">{featured.title}</h1>
                  <p className="browse-hero-meta flex flex-wrap gap-[12px] text-[11px] text-[#c0ceca] [@media(max-width:700px)]:gap-[5px] [@media(max-width:700px)]:text-[10px]">
                    {featured.genres.join(" · ")}
                    <span>•</span>
                    {featured.chapters.length} audio chapters
                  </p>
                  <p className="browse-hero-description mt-[14px] mr-0 mb-[20px] ml-0 max-w-[550px] text-[13px] leading-[1.7] text-[#b5c4c0] [@media(max-width:700px)]:text-[11px]">
                    {featured.synopsis}
                  </p>
                  <button
                    type="button"
                    className="browse-primary inline-flex items-center justify-center gap-[24px] rounded-[24px] border-none bg-[var(--accent)] px-[20px] py-[12px] text-[12px]! font-bold! text-[#102c27] [&:hover:not(:disabled)]:bg-[#8cebd7]"
                    onClick={(event) =>
                      openDetails(featured, event.currentTarget)
                    }
                  >
                    Explore manga <span aria-hidden="true">↗</span>
                  </button>
                </div>
                <span
                  className="browse-hero-number pointer-events-none absolute right-[16px] bottom-[-45px] text-[230px] font-extrabold tracking-[-20px] text-[#ffffff04]"
                  aria-hidden="true"
                >
                  01
                </span>
              </section>
              <div
                className="browse-filters [&_button[aria-pressed=true]]:border-[var(--ink)] [&_button[aria-pressed=true]]:bg-[var(--ink)] [&_button[aria-pressed=true]]:text-[#18221f] mt-[26px] mb-[24px] flex flex-wrap gap-[8px]"
                aria-label="Filter by genre"
              >
                {genres.map((item) => (
                  <button
                    className="rounded-[24px] border border-[var(--line)] bg-[var(--surface)] px-[13px] py-[8px] text-[11px]!"
                    type="button"
                    key={item}
                    aria-pressed={genre === item}
                    onClick={() => setGenre(item)}
                  >
                    {item}
                  </button>
                ))}
              </div>
              {query.trim() || genre !== "All stories" ? (
                <>
                  <p
                    role="status"
                    className="browse-results text-[12px] text-[var(--muted)]"
                  >
                    {visible.length}{" "}
                    {visible.length === 1 ? "story" : "stories"} found
                  </p>
                  <MangaShelf
                    id="browse-results"
                    title="Search results"
                    subtitle="FIND YOUR KIND OF STORY"
                  >
                    {visible.map((item) => card(item))}
                  </MangaShelf>
                  {!visible.length && (
                    <div className="browse-empty rounded-[14px] border border-dashed border-[var(--line)] px-[20px] py-[60px] text-center">
                      <h3>No stories found</h3>
                      <p className="mt-[16px] mr-0 mb-[24px] ml-0 text-[13px] text-[var(--muted)]">
                        Try a different title, author, or genre.
                      </p>
                      <button
                        type="button"
                        className="browse-primary inline-flex items-center justify-center gap-[24px] rounded-[24px] border-none bg-[var(--accent)] px-[20px] py-[12px] text-[12px]! font-bold! text-[#102c27] [&:hover:not(:disabled)]:bg-[#8cebd7]"
                        onClick={() => {
                          setQuery("");
                          setGenre("All stories");
                        }}
                      >
                        Reset filters
                      </button>
                    </div>
                  )}
                </>
              ) : (
                <>
                  <MangaShelf
                    id="browse-recent"
                    title="Recently added"
                    subtitle="FRESH ON THE SHELF"
                  >
                    {browseShelves.recent.map((item) => card(item))}
                  </MangaShelf>
                  <MangaShelf
                    id="browse-top"
                    title="Top 10 Mangas"
                    subtitle="DEMO CHART · STORIES TO GET LOST IN"
                  >
                    {browseShelves.top.map((item, index) =>
                      card(item, index + 1),
                    )}
                  </MangaShelf>
                  <section
                    className="browse-request-banner [&_.browse-primary]:ml-auto [&_.browse-primary]:shrink-0 [@media(max-width:700px)]:[&_.browse-primary]:ml-0 my-[34px] mx-0 flex items-center gap-[22px] rounded-[12px] border border-[#39594e] bg-[linear-gradient(110deg,#263e38,#1d2826)] px-[26px] py-[22px] [@media(max-width:700px)]:flex-wrap [@media(max-width:700px)]:gap-[14px] [@media(max-width:700px)]:p-[20px]"
                    aria-labelledby="browse-request-title"
                  >
                    <span
                      className="browse-request-icon border-r border-[#496158] pr-[22px] text-[34px] text-[var(--accent)]"
                      aria-hidden="true"
                    >
                      ♫
                    </span>
                    <div className="[@media(max-width:700px)]:min-w-[160px] [@media(max-width:700px)]:flex-1">
                      <h2
                        className="mt-0 mr-0 mb-[6px] ml-0 text-[18px] font-[650]"
                        id="browse-request-title"
                      >
                        Request a manga
                      </h2>
                      <p className="m-0 text-[12px] leading-[1.6] text-[#b5c4c0]">
                        Can't find the manga you'd love to hear? Tell us what we
                        should bring to audio next.
                      </p>
                    </div>
                    <button
                      type="button"
                      className="browse-primary inline-flex items-center justify-center gap-[24px] rounded-[24px] border-none bg-[var(--accent)] px-[20px] py-[12px] text-[12px]! font-bold! text-[#102c27] [&:hover:not(:disabled)]:bg-[#8cebd7]"
                      onClick={() => setRequestOpen(true)}
                    >
                      ＋ Request a manga
                    </button>
                  </section>
                  <MangaShelf
                    id="browse-picks"
                    title="Today's Top Picks for You"
                    subtitle="CURATED DEMO PICKS · FIND A NEW FAVORITE"
                  >
                    {browseShelves.picks.map((item) => card(item))}
                  </MangaShelf>
                </>
              )}
              <footer className="browse-footer mt-[40px] flex justify-between gap-[14px] border-t border-[var(--line)] px-0 py-[22px] text-[10px] text-[var(--muted)] [@media(max-width:700px)]:flex-col">
                <span>KoeTTS · A different way to experience manga</span>
                <span>Read. Listen. Imagine.</span>
              </footer>
            </>
          )}
        </main>
        {selected && user && (
          <aside
            className="browse-details sticky top-0 h-[calc(100dvh-110px)] overflow-y-auto border-l border-[var(--line)] bg-[#161d20] p-[22px] [@media(max-width:1100px)]:relative [@media(max-width:1100px)]:m-auto [@media(max-width:1100px)]:h-auto [@media(max-width:1100px)]:min-h-[calc(100dvh-200px)] [@media(max-width:1100px)]:w-full [@media(max-width:1100px)]:max-w-[700px] [@media(max-width:1100px)]:border-none [@media(max-width:1100px)]:border-current [@media(max-width:1100px)]:p-[24px]"
            aria-labelledby="details-title"
          >
            <div className="browse-details-top mb-[24px] flex items-center justify-between text-[9px] tracking-[1.5px] text-[var(--muted)]">
              <span>MANGA DETAILS</span>
              <button
                className="size-[34px] rounded-[50%] border-none bg-[#252e31] text-[24px]!"
                ref={closeButton}
                type="button"
                aria-label="Close manga details"
                onClick={closeDetails}
              >
                ×
              </button>
            </div>
            <div className="browse-details-summary [&_.browse-cover]:p-[9px] [&_.browse-cover_strong]:mb-[5px] [&_.browse-cover_strong]:text-[14px] [&_.browse-cover>span]:text-[5px] [&_.browse-cover>span]:tracking-[.5px] grid grid-cols-[96px_minmax(0,1fr)] items-center gap-[16px] [@media(max-width:1100px)]:grid-cols-[120px_minmax(0,1fr)]">
              <Cover title={selected.title} />
              <div>
                <h2
                  className="m-0 text-[22px] font-[650] leading-[1.2] tracking-[-.6px] [overflow-wrap:anywhere]"
                  id="details-title"
                >
                  {selected.title}
                </h2>
                <p className="my-[12px] mx-0 text-[11px] text-[var(--muted)]">
                  By {selected.author}
                </p>
                <div className="browse-genres flex flex-wrap gap-[5px]">
                  {selected.genres.map((item) => (
                    <span
                      className="rounded-[4px] bg-[#293635] px-[6px] py-[4px] text-[9px]"
                      key={item}
                    >
                      {item}
                    </span>
                  ))}
                </div>
              </div>
            </div>
            <button
              type="button"
              className="browse-primary inline-flex items-center justify-center gap-[24px] rounded-[24px] border-none bg-[var(--accent)] px-[20px] py-[12px] text-[12px]! font-bold! text-[#102c27] [&:hover:not(:disabled)]:bg-[#8cebd7] browse-listen mt-[24px] w-full"
              disabled
            >
              ▶ Listen now
            </button>
            <p className="browse-preview-note mt-[10px] mr-0 mb-[22px] ml-0 text-[10px] leading-[1.5] text-[var(--muted)]">
              Audio preview unavailable · Demo content
            </p>
            <h3 className="mt-0 mr-0 mb-[10px] ml-0 text-[13px]">Synopsis</h3>
            <p className="browse-synopsis mb-[26px] text-[12px] leading-[1.75] text-[#b7c2c3]">
              {selected.synopsis}
            </p>
            <div className="browse-chapter-heading flex items-baseline justify-between border-t border-[var(--line)] pt-[20px]">
              <h3 className="mt-0 mr-0 mb-[10px] ml-0 text-[13px]">
                Chapters{" "}
                <span className="text-[10px] text-[var(--muted)]">
                  ({selected.chapters.length})
                </span>
              </h3>
              <span className="text-[10px] text-[var(--muted)]">
                In story order
              </span>
            </div>
            <p className="browse-preview-note mt-[10px] mr-0 mb-[22px] ml-0 text-[10px] leading-[1.5] text-[var(--muted)]">
              Select a chapter to preview its player details.
            </p>
            <ol className="browse-chapters [&_button:hover]:bg-[#24312f] [&_button[aria-pressed=true]]:rounded-[6px] [&_button[aria-pressed=true]]:bg-[#203e35] [&_button[aria-pressed=true]]:text-[var(--accent)] m-0 list-none p-0">
              {selected.chapters.map((item) => (
                <li key={item.id}>
                  <button
                    className="grid w-full grid-cols-[22px_minmax(0,1fr)_34px] items-center gap-[10px] border-0 border-b border-solid border-[var(--line)] bg-transparent px-[8px] py-[14px] text-left text-[11px]! leading-[1.5]!"
                    type="button"
                    aria-pressed={
                      chapter?.manga.id === selected.id &&
                      chapter.chapter.id === item.id
                    }
                    onClick={() =>
                      setChapter({ manga: selected, chapter: item })
                    }
                  >
                    <span className="browse-chapter-number text-[10px] text-[var(--muted)]">
                      {String(item.number).padStart(2, "0")}
                    </span>
                    <span>{item.title}</span>
                    <small className="text-[10px] text-[var(--muted)]">
                      {item.duration}
                    </small>
                  </button>
                </li>
              ))}
            </ol>
          </aside>
        )}
      </div>
      <section
        className="browse-player fixed inset-x-0 bottom-0 z-30 grid h-[100px] grid-cols-[1fr_minmax(230px,1.2fr)_1fr] items-center gap-[30px] border-t border-[var(--line)] bg-[#191f22] px-[28px] py-[14px] [@media(max-width:700px)]:grid-cols-[minmax(0,1fr)_100px] [@media(max-width:700px)]:gap-[10px] [@media(max-width:700px)]:px-[16px] [@media(max-width:700px)]:py-[12px]"
        aria-label="Audiobook player preview"
      >
        <div className="browse-player-track [&_.browse-cover>span]:text-[10px] [&_.browse-cover_strong]:text-[11px] [@media(max-width:700px)]:[&_.browse-cover_strong]:text-[20px] [&>div:last-child]:min-w-0 [&_strong]:block [&_strong]:overflow-hidden [&_strong]:text-[11px] [&_strong]:text-ellipsis [&_strong]:whitespace-nowrap [&_span]:block [&_span]:overflow-hidden [&_span]:text-ellipsis [&_span]:whitespace-nowrap [&_span]:mt-[6px] [&_span]:text-[10px] [&_span]:text-[var(--muted)] [&_.browse-cover]:w-[44px] [&_.browse-cover]:shrink-0 [&_.browse-cover]:p-[5px] [&_.browse-cover_strong]:hidden [&_.browse-cover>span]:hidden [&_.browse-cover_svg]:w-[80%] [&_.browse-player-placeholder]:m-0 [&_.browse-player-placeholder]:grid [&_.browse-player-placeholder]:h-[54px] [&_.browse-player-placeholder]:w-[48px] [&_.browse-player-placeholder]:shrink-0 [&_.browse-player-placeholder]:place-items-center [&_.browse-player-placeholder]:rounded-[6px] [&_.browse-player-placeholder]:bg-[#283b35] [&_.browse-player-placeholder]:text-[24px] flex min-w-0 items-center gap-[12px]">
          {chapter && user ? (
            <>
              <Cover title={chapter.manga.title} />
              <div>
                <strong>
                  Ch. {chapter.chapter.number} · {chapter.chapter.title}
                </strong>
                <span>{chapter.manga.title}</span>
              </div>
            </>
          ) : (
            <>
              <span className="browse-player-placeholder" aria-hidden="true">
                ♫
              </span>
              <div>
                <strong>Your next chapter starts here</strong>
                <span>Select a manga, then choose a chapter</span>
              </div>
            </>
          )}
        </div>
        <div className="browse-player-controls [&>div:first-child]:flex [&>div:first-child]:items-center [&>div:first-child]:justify-center [&>div:first-child]:gap-[22px] [&_.browse-play]:size-[34px] [&_.browse-play]:rounded-[50%] [&_.browse-play]:bg-[var(--accent)] [&_.browse-play]:text-[#102c27] [@media(max-width:700px)]:[&>div:first-child]:gap-[10px]">
          <div>
            <button
              className="border-none bg-transparent text-[14px]!"
              type="button"
              disabled
              aria-label="Previous chapter"
            >
              Ⅰ◀
            </button>
            <button
              type="button"
              disabled
              className="browse-play border-none bg-transparent text-[14px]!"
              aria-label="Play"
            >
              ▶
            </button>
            <button
              className="border-none bg-transparent text-[14px]!"
              type="button"
              disabled
              aria-label="Next chapter"
            >
              ▶Ⅰ
            </button>
          </div>
          <div className="browse-timeline [@media(max-width:700px)]:hidden mt-[9px] flex items-center gap-[10px] text-[9px] text-[var(--muted)]">
            <span>0:00</span>
            <span className="browse-track-line h-[3px] flex-1 rounded-[10px] bg-[#3a454a]" />
            <span>{chapter && user ? chapter.chapter.duration : "0:00"}</span>
          </div>
        </div>
        <div className="browse-player-note text-right text-[10px] text-[var(--muted)] [@media(max-width:700px)]:col-span-full [@media(max-width:700px)]:text-left">
          <span>Audio preview unavailable</span>
          <label className="mt-[12px] flex items-center justify-end gap-[9px] [@media(max-width:700px)]:hidden">
            Volume{" "}
            <input
              type="range"
              disabled
              aria-label="Volume"
              defaultValue="70"
            />
          </label>
        </div>
      </section>
    </div>
  );
}
