# Browse UI preview

Approved on 2026-11-03: implement the agreed UI plan and document it. Scope is `/browse` only. The root route and admin routes are unchanged.

## Experience

A dark, audio-first manga discovery page inspired by a manga catalog and a music library: compact navigation, featured manga, three horizontal discovery shelves, searchable collection, genre filters, manga details, and a fixed player preview. Charcoal surfaces and a teal accent are scoped to `.browse-preview`.

All covers use one plain title-and-headphones template. Fictional manga and chapter metadata live in `apps/web/features/temp-data/manga.ts`. No external artwork, dependencies, audio files, generation, playback requests, or simulated progress are introduced.

The existing sign-in state still gates the collection. Account navigation is reused. The browse preview does not fetch the live catalog; existing catalog, reader, playback, and publication APIs are unchanged.

## Shelf layout (approved follow-up, 2026-11-03)

Below the featured banner and genre controls: Recently added, Top 10 Mangas, a full-width Request a manga banner linking to `/request`, then Today's Top Picks for You. Each discovery shelf contains exactly 10 manga. Top 10 displays ranks 1–10. `browseShelves` defines explicit demo ordering in the fixture file; rankings and picks are editorial placeholders, not live metrics or personalization. Search or an active genre replaces the discovery shelves with one horizontal results shelf containing all matches.

Desktop shelves hide their scrollbar. With a fine pointer and hover support, wheel down moves the hovered row right and wheel up moves it left. At either end, the wheel is not cancelled so normal page scrolling resumes. Rows without overflow also leave page scrolling alone. Native horizontal trackpad gestures, Shift-wheel, and Ctrl-wheel zoom are preserved. Touch devices retain native swiping with proximity snapping. Desktop wheel scrolling is continuous to avoid small deltas getting stuck on a snap point.

Each shelf has labelled previous/next buttons, disabled at its edges, and a focusable region supporting Left/Right arrow keys. Buttons move 85% of the visible row width and respect reduced-motion preferences. Fixed card widths retain a hint of the next card at typical viewports. Rows scroll independently and are not remounted when manga details open.

## Interactions

- Search matches title, author, or genre; genre filters combine with search. Reset restores the collection.
- Selecting manga opens a 360px right panel on wide screens without navigation. Focus moves to Close; Close or Escape restores focus to the originating card.
- At widths of 1100px or less, details replace the discovery region with a full-width view, avoiding a squeezed catalog and modal focus traps.
- Chapter selection updates only the player metadata. Inspecting another manga does not replace that chapter.
- All actual playback and volume controls are disabled and labelled as unavailable. No audio element is mounted.
- Fixtures have no live manga IDs, so there are no misleading links to real manga detail routes.

## Implementation and validation

UI: `apps/web/features/library/browse-page.tsx`, `manga-shelf.tsx`, and `browse.css`. Fixtures: `apps/web/features/temp-data/manga.ts`. Interaction coverage belongs in `apps/web/tests/shared-ui.test.cjs`.

Acceptance: search/filter/reset, selection independent from chapter metadata, details dismissal and focus restoration, signed-out collection gate, disabled playback, and no catalog/audio requests. Verify narrow and wide layouts, long titles, chapter overflow, and bottom-player clearance. Run root `npm run check` and record exact outcomes in `CONTEXT.md`.

## Deferred

Real catalog metadata integration, playable audio, saved listening progress, bookmarks, queues, theme switching, and changes outside browse require a separate scope. The demo collection is intentionally temporary; this phase replaces live catalog discovery on `/browse` while preserving existing endpoints and detail/reader routes.

## Motion

Shelf wheel bursts accumulate a destination and use native smooth scrolling; reduced-motion users get instant movement. Manga selection has no entrance or card-lift animation. The details panel stays mounted when switching manga, preserving its scroll container. No Framer Motion dependency is required.

## UI-only request modal

Browse header and banner request buttons open a native modal dialog (desktop) or bottom sheet (mobile). Fields: required title (maximum 200 characters), chapter 1–9999, optional notes (maximum 4000 characters). Preview request shows a local summary explicitly stating nothing was sent or saved. No request API or Firestore calls are made by this modal. Drafts survive dismissal while the browse component remains mounted, and reset on account change or page departure. Native dialog behavior provides background inertness and keyboard focus containment; Escape and Close dismiss, restore scroll locking, and return focus to the opener. Existing sign-in behavior is retained.

**Outstanding decision — remind the user in subsequent request-flow work:** `/request` is deliberately retained. Do not remove it without explicit approval. Its existing backend behavior is unchanged; the new browse modal alone is UI-only. Decide later whether to keep `/request` as the direct-link fallback or retire it after the real request flow is approved. Do not wire the preview to Firestore without authorization.
