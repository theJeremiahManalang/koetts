# Text extraction and reading-order research

Research date: 2026-10-09. These are recommendations for a next phase, not additional
models or a guaranteed-order feature implemented in this change.

## What is implemented first

The shared runner supports MAGI v3 and dmMaze/comic-text-detector. Both expose text
boxes for comparison. MAGI also exposes its existing OCR and grounding methods.
CTD exposes text blocks, line polygons, and masks; it does not recognize characters.
The runner preserves model output order without asserting that it is correct.

## Practical extraction options

For Japanese panels, a strong candidate is CTD detection followed by Manga OCR on
individual text-block crops. Manga OCR supports vertical and horizontal Japanese,
furigana, and multi-line bubble text. Its authors warn that long crops can cause
errors and that the recognizer can invent text when the crop has no text. Restrict
recognition to detected regions and retain source crops for review. This is a
candidate to benchmark, not evidence that it beats MAGI on this project's images.
[Manga OCR documentation](https://github.com/kha-white/manga-ocr)

This detector/recognizer combination already exists in Mokuro. It is a useful
reference implementation for Japanese extraction, although selectable text in a
reader does not establish a correct narration sequence.
[Mokuro documentation](https://github.com/kha-white/mokuro)

MAGI is useful when panels, characters, text regions, and speech associations are
needed together. Its model card lists English and provides localization, OCR, and
character-grounding interfaces. Do not assume its Japanese accuracy matches a
Japanese-specific recognizer without evaluating representative pages.
[MAGI v3 model card](https://huggingface.co/ragavsachdeva/magiv3)

## Reading order is a separate problem

CTD contains a coarse spatial sorting heuristic: it chooses horizontal direction
based on whether a majority of detected blocks are classified Japanese, then uses
a grid-based spatial weight. This is not a semantic guarantee. An English
translation of a right-to-left manga can retain right-to-left panel order, making
language alone an unreliable direction selector.
[CTD text-block implementation](https://github.com/dmMaze/comic-text-detector/blob/440b978563c71b758e31aaa315d100faba1efa2f/utils/textblock.py)

Recommended future pipeline:

1. Set page/panel reading direction explicitly for the source edition, independently
   of OCR language. For a single supplied panel, skip page panel ordering.
2. For full pages, detect panels, assign text regions to panels, and establish panel
   order first. Preserve ambiguous, overlapping, and border-crossing regions for review.
3. Within each panel, group text into bubbles/blocks and infer their sequence using
   layout and narrative context. A plain global `(y, x)` sort can interleave panels
   and break tall or staggered bubbles.
4. Recognize each crop, respecting horizontal/vertical writing. Preserve original
   box IDs and record an explicit ordered list of IDs instead of reordering native
   arrays; this avoids breaking MAGI's index-based associations.
5. Show numbered crops/overlays for human correction before audio generation.
   For ambiguous layouts, require a reviewed order rather than claiming certainty.

These pipeline steps are engineering recommendations inferred from the models'
capabilities and limitations. Neither implementation currently provides a
verified audiobook reading-order guarantee. No automatic reordering was added.

## How to evaluate improvements

Use the same representative panels/pages and manually annotate text regions,
transcriptions, and reading sequence. Include Japanese vertical text, translated
manga, staggered bubbles, narration boxes, and sound effects where relevant.

Evaluate detection with matched-box precision/recall at a stated overlap threshold;
recognition with character error rate (and word error rate where appropriate);
and ordering with pairwise ordering accuracy plus exact-sequence accuracy. Review
block-versus-line granularity explicitly. To isolate recognition, use identical
reference crops; to compare complete systems, also score detection plus OCR end to
end. Time inference separately from loading/downloads on the same hardware.

For this project, the next experiment I recommend is CTD + Manga OCR for Japanese
text, alongside MAGI OCR as a baseline, followed by explicit panel-aware ordering
and a manual correction pass. Keep this separate from the initial two-detector
comparison so extraction changes do not obscure detector differences.
