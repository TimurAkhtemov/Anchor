# The Daily Note — Briefing v3 Design

_Date: 2026-07-11 · Status: draft for review, pre-implementation._
_Succeeds the tour form of `docs/immersive_briefing_design.md` (shipped as PR #8).
Prompted by product feedback on the shipped tour: the content reads as restated
labels rather than insight, the form reads as onboarding, and real-portfolio
data has no web path._

## Diagnosis (carried into the design)

1. **The packet is the ceiling, not the model.** The generator narrates a DATA
   packet of mart rows — labels and numbers — and the numeric audit (rightly)
   forbids anything beyond it. Restatement is the only permitted output.
   Insight must therefore be **computed upstream** and placed in the packet as
   first-class numbers the model can cite.
2. **One-entity-per-step forbids synthesis.** The v2 step schema fixed
   horizon-blending by confining each step to one entity — but the interesting
   sentences are cross-entity ("TALO's move is idiosyncratic, not sector
   beta"). The schema must permit synthesis without reopening the
   hallucination door.
3. **The page walks the schema, not the story.** One scene per mart means the
   same six rooms every day. A briefing is structured by what happened today;
   the macro→sector→holding principle belongs **inside each item's sentences**,
   not as the page's table of contents.

## Goal

A daily note someone reads because it tells them something they could not read
off the charts: what today means for *this* portfolio, verdict first, every
claim grounded and attributed, silent when there is nothing to say.

## Locked decisions

1. **Form: the Daily Note.** A PM's-letter spine — a flowing written note —
   with one front-page element above it: a verdict headline plus the single
   chart that matters today. No stepper, no scenes, no scroll choreography;
   scrolling is reading. The plain-text edition (`/text`) remains.
2. **Chain as item anatomy.** Each item states its macro→sector→holding chain
   in prose (regime fit → sector context → the position), with small marks
   embedded inline where the sentence cites them. The chain is the item's
   anatomy, not the page's structure.
3. **Earn every sentence; silence is a valid output.** Item count flexes with
   salience (roughly 2–4). A quiet day renders a short note plus an explicit
   "nothing else moved beyond noise" line — an honest sentence dashboards
   never say.
4. **Salience selection is code, not LLM.** A deterministic ranker picks the
   items; the model narrates what the ranker chose. Selection is testable and
   audit-logged; generation quality can never smuggle in item choice.
5. **Insight is computed in gold (lever A).** New derived-signal marts feed
   the packet: portfolio rate sensitivity, per-holding attribution splits,
   concentration. The LLM's job narrows to narration and framing.
6. **Schema v3: lede / items / watch (lever B).** Items may reference multiple
   entities. Cross-entity claims are validated by a containment rule: the lede
   and watch may only cite figures already audited within items; every
   referenced entity must exist in the packet.
7. **Cloud model for the demo world only (lever D).** A provider seam
   (`ANCHOR_BRIEFING_PROVIDER`) allows a frontier cloud model for the demo
   briefing. A structural guard — the `assert_portfolio_isolation` pattern —
   hard-fails any cloud provider combined with `holdings_source: real` before
   a single network call. Real portfolio remains local-only (Ollama).
8. **Editorial voice rules (lever D).** Verdict first. Never restate a label
   or number the page already renders without adding a relation or cause.
   Every item answers "so what for this portfolio." Attribute news or omit it.
   Non-advisory framing throughout ("worth watching", never buy/sell/should).
9. **Visual identity follows the form.** The letter form gets its own
   text-first identity, designed at implementation time with the
   frontend-design + dataviz skills. The morning-paper tokens are not presumed
   to survive; constraints carried: calm, restrained, no red/green saturation,
   not the Streamlit indigo-glass.
10. **Local-only real mode.** The web surface can render the real portfolio
    only via a gitignored private bundle and a local build. Real data never
    reaches a committed file, CI, or a deploy host.
11. **Compatibility.** `briefing_md` remains, assembled from lede + item +
    watch narrations (the Streamlit sidebar and `/text` read it unchanged).
    All v1/v2 grounding guarantees carry over: numeric audit, source
    attribution, hard-fail validation, provenance row.

## The note script artifact (v3 of `briefing_json`)

Sketch — exact field names finalized at implementation:

```jsonc
{
  "lede": { "headline": "…", "narration": "…", "figures": ["…"] },
  "items": [
    {
      "id": 1,
      "kind": "position | sector | regime | allocation | risk",   // "change" reserved for the history phase
      "entities": ["TALO", "XLE"],          // every ticker/key the narration references — all must exist
      "narration": "…",
      "figures": ["+34.77 pp", "+67.81%"],  // audited per item, as v2
      "headline_refs": [14],
      "salience": { "score": 0.91, "reasons": ["top_relative_move_1y"] }  // ranker echo, for audit
    }
  ],
  "watch": { "narration": "…", "figures": [] },   // optional
  "quiet": false                                   // true → short note + the quiet-day line
}
```

Validation (all hard failures, extending v2's machinery):
- Per-item: every figure passes the numeric audit; every entity exists in the
  packet; every headline ref is in range.
- Containment: lede and watch may only cite figures that some item already
  carries (generation order: items first, then lede/watch — display order is
  the reverse).
- Flex bounds: 1–4 items, or `quiet: true` with ≤ 2 items.
- The v2 kind-ladder ordering rule retires; chain anatomy is enforced at the
  prompt level, not the validator (it is a style property, not a truth
  property).

## The insight engine (derived-signal marts)

New gold models, each with the usual tests, added to the DATA packet under
names the model can cite:

- `portfolio_rate_sensitivity` — the portfolio's weighted rate-comovement:
  equity holdings' sector `rate_comovement` weighted by position weight (one
  row; the "60% of your book moves against rates" number). Fixed-income
  duration buckets join as a labeled second axis, not blended into the same
  scalar.
- `holding_attribution` — per holding × horizon: benchmark contribution vs
  idiosyncratic remainder (`holding = benchmark + relative`, framed in pp), so
  an item can say how much of a move was sector beta.
- Concentration signals — top-position share, top-2 share, per-class shares;
  likely an extension of `portfolio_composition` or one small summary mart.
- (Reserved for the history phase: crossings and drift.)

## The salience ranker

Deterministic Python in `app/briefing.py`, unit-tested on fixtures.
Candidates: every holding × (axis, horizon) relative move, sector extremes at
each horizon, regime-state deltas (v1 proxy: `|delta_3mo|` thresholds until
history exists), concentration flags. Scored and thresholded; top 2–4 become
items; below threshold → quiet day. The ranker's score and reasons are echoed
into each item's `salience` for the audit trail.

## The page (Daily Note surface)

- **Above the fold:** masthead, dateline, the lede's verdict headline set
  large, and today's chart (chosen by the lede's dominant entity: the sector
  strip, a pp bar group, or the allocation band — the existing mark kit).
- **The note:** items as flowing prose blocks; inline marks embedded at the
  citing sentence; figures and source chips as margin annotations (desktop) /
  footnotes after the paragraph (mobile).
- **Close:** the watch line, then the colophon (provenance, staleness marker,
  `/text` link).
- The tour's scroll choreography retires. Retained from PR #8: the mark
  components, the resolver (it now selects inline-mark horizons/axes), `/text`,
  the Playwright harness, the CI web job, the data layer and types.

## Local-only real mode

- `make export-web-real` → `web/public/data/anchor.private.json` (gitignored).
- Build-time selection (`ANCHOR_WEB_BUNDLE=private npm run build`) produces a
  local `out/` only; the default path and every CI/deploy build read the
  committed demo bundle exactly as today.
- Privacy tests: the private filename is gitignored and never tracked; the
  committed bundle remains demo-only (existing `_allowed_tickers` test).

## Testing & ops

- Python: ranker unit tests; v3 validation tests (containment, flex bounds,
  quiet mode); provider-guard test (cloud + real → hard fail). All fake-based,
  no LLM in CI.
- Web: smoke updated (note renders, N items present, margin annotation binds
  to its item); resolver unit tests carry over.
- CI shape unchanged (the `web` job and gated dbt job as today).

## Phasing (PR-sized chunks)

1. **Provider seam + voice rules** — works against the current v2 schema;
   immediate content lift for the demo (cloud model), guard included.
2. **Derived-signal marts** — models + tests + packet + audit extensions.
3. **Schema v3 + ranker + the Daily Note page** — the big one; may split into
   artifact PR and page PR. Identity redesign happens here, with the skills.
4. **Local-only real mode** — small and independent; any time after 3 (the
   note must exist before a real-portfolio note is worth rendering).
5. **History / what-changed** — own design doc first (storage grain, crossings
   detection); schema v3 reserves item `kind: "change"` for it.

## Out of scope (unchanged from v2's list)

Dashboard parity on the web; API service / live reads / multi-user; audio;
auto-generated chart types beyond the mark kit; retiring Streamlit.
