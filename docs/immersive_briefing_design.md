# Immersive Briefing Front-End — Design

_Date: 2026-07-11 · Status: approved design, pre-implementation._
_Evolves the v1 LLM briefing (`docs/llm_copilot_briefing_design.md`) from a prose
artifact into a guided, scroll-told walkthrough on a new serve surface. Prompted by
direct product feedback: the briefing reads as "another block of text" — the reader
still does the pointing, relating, and interpreting themselves._

## Goal

A **tour, not a report**: a single narrative page that walks the reader through
macro → sectors → holdings, highlighting the specific securities, relationships,
and headlines the briefing references — the page does the pointing. Keep every
grounding guarantee of v1 (numbers from marts, news attributed, audit trail).

## Locked decisions

1. **Custom front-end, alongside Streamlit.** The vision (spotlighting, scroll
   choreography, animated relationships) outgrows Streamlit's rerun model. The new
   front-end is a second consumer of the same gold layer; the public demo URL swaps
   to it when ready. Streamlit remains the local/real-portfolio workbench.
2. **Static export data path.** No backend, no creds, no cost — the pipeline exports
   a JSON bundle the front-end ships with; refresh = pipeline run + push, exactly the
   committed-parquet philosophy. An API service remains the documented seam if
   live/multi-user ever matters.
3. **Tour-first v1 scope.** One page: the daily briefing as a scroll narrative.
   Dashboard parity (tables, sparkline grids) stays in Streamlit for now.
4. **Stack: Next.js + React + TypeScript**, static export (`output: 'export'`),
   framer-motion (choreography), visx (charts), Tailwind (styling). Chosen over
   Svelte for ecosystem depth in scrollytelling/charts, free static hosting
   (Vercel or GitHub Pages), and hiring-signal adjacency. Lives in `web/`.
5. **Choreography principle: scroll-driven, never autoplay.** The reader paces the
   tour; the page responds (spotlight, dim, annotate) but never scrolls itself,
   flashes, or counts down. This is how "immersive" stays inside the product
   principles (calm, explain-don't-provoke, reflection over reaction). A
   plain-text reading of the same briefing stays one click away (accessibility
   and honesty fallback — it is the v1 `briefing_md`).

## The structured briefing artifact (v2 of `copilot_briefing`)

The generator gains a second output beside `briefing_md`: **`briefing_json`** — the
tour script. Additive column on the same table/grain (`horizon='all'`); the
Streamlit sidebar keeps reading `briefing_md` untouched.

```jsonc
{
  "steps": [
    {
      "id": 1,
      "target": { "kind": "regime" },                  // regime | indicator | sector | allocation | holding
      "narration": "Rates held steady while inflation kept climbing…",
      "figures": ["4.17%", "+1.73 pp"],                // every % / pp the narration cites — audited per step
      "headline_refs": []                               // indexes into sources[]
    },
    {
      "id": 5,
      "target": { "kind": "holding", "key": "TALO", "axis": "sector" },
      "narration": "TALO sits +34.77 pp ahead of XLE over the year…",
      "figures": ["+34.77 pp", "+67.81%"],
      "headline_refs": [13]
    }
  ]
}
```

- **Generation**: the LLM writes prose per step against the same DATA/NEWS packet;
  step targets constrain it to one entity at a time — the format itself suppresses
  the "across all horizons" blending that plagued free prose.
- **Validation strengthens**: per-step checks — `target.key` must exist in the
  packet's entities; every `figures[]` entry must pass the numeric audit; every
  `headline_refs` index must exist in `sources`. Malformed JSON or a failed step
  check is a **hard** failure (unlike v1's warning-level audit, structure makes
  strictness cheap). `briefing_md` is generated as today (or assembled from step
  narrations — decide during implementation by output quality).
- Ordering must follow the reading order: regime/indicator steps before sector
  steps before holding steps — validated, not hoped for.

## Static export for the web

`app/export_web.py` (importable fn + CLI, the `export_snapshot.py` convention):
reads `anchor_marts` (hardcoded — demo-only by construction, the same structural
privacy guarantee as the parquet snapshot) and writes one
`web/public/data/anchor.json`: the five context marts (records-oriented), the
briefing row (`briefing_md`, parsed `briefing_json`, `sources`, provenance), and
`as_of_calendar`. `make refresh` grows an `export-web` step after `snapshot`.
Real-portfolio data never flows here — the web surface is demo-only in v1.

## The page (v1)

Sections in reading order, each a full-viewport scroll scene; the tour script's
steps bind to them by `target`:

1. **Hero / regime** — as-of date, regime sentence, three state chips.
2. **Macro** — four indicator cards; the active step's indicator lifts, others dim;
   delta rendered as an annotated number, not a chart (monthly series stay humble).
3. **Sectors** — an 11-bar return strip (horizon from the step's cited figures);
   active sector bar spotlit, its rate-comovement label surfaced.
4. **Allocation** — proportional band (equity/fixed income/cash), animated on entry.
5. **Holdings** — position tiles; the active step's tile spotlights with its
   benchmark-relative bars (pp per axis, ahead/behind coloring from mart labels)
   and the referenced headline as an attributed chip.
6. **Coda** — provenance line (generated date · model · provider · N headlines),
   staleness marker when applicable, link to the text version.

Narration renders in a fixed side rail (desktop) / bottom sheet (mobile) that
advances as scenes enter the viewport (IntersectionObserver). No scroll hijacking.

## Testing & ops

- Python: step-schema validation unit tests (fakes, no LLM — extends
  `tests/app/test_briefing.py`); export_web privacy test (bundle tickers ⊆
  demo+benchmark set, reusing `_allowed_tickers`).
- Web: `tsc --noEmit` + build in CI (new job, no secrets needed); one Playwright
  smoke (page renders, N tour steps present, first spotlight fires on scroll).
- Deploy: Vercel (or Pages) from `main`, `web/` root. The committed
  `anchor.json` is the release artifact, same as the parquet today.

## Out of scope for v1 (documented follow-ups)

- Dashboard parity on the web surface; retiring Streamlit.
- Real-portfolio mode on the web (needs a local serving story or API — explicit
  future decision, privacy rules unchanged).
- API service, live reads, multi-user.
- Auto-generated per-step charts beyond the fixed scene kit; audio narration.
- Dagster: `export_web` joins the asset graph alongside `snapshot_parquet`
  (same follow-up boundary as the briefing asset).

## Resolved in review (2026-07-11)

1. **`briefing_md` is assembled from step narrations** — one generated source of
   truth, zero drift between the tour and the text fallback. Steps join as
   paragraphs grouped by target kind (macro steps → paragraph 1, sector steps →
   paragraph 2, allocation+holding steps → paragraph 3), preserving v1's shape
   for the Streamlit sidebar and the length bounds.
2. **The web surface gets a fresh visual identity** — not the Streamlit app's
   indigo-glass. Designed at implementation time (frontend-design + dataviz
   skills); constraint carried over: restrained, calm, no red/green emotional
   saturation.
3. **Hosting: Vercel** — the smoothest Next.js static-export path.
