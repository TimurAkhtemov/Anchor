# Anchor — web tour surface

The immersive briefing front-end: the daily LLM briefing rendered as a
scroll-told tour (macro → sectors → holdings) per
`docs/immersive_briefing_design.md`. Next.js 16 static export — no backend, no
credentials; the page renders the committed `public/data/anchor.json` bundle
(demo portfolio only, by construction).

```bash
npm run dev        # local dev server
npm run build      # static export -> out/
npm run typecheck  # tsc --noEmit (build first: it generates next-env.d.ts)
npm run test:e2e   # Playwright — resolver unit tests + browser smoke (serves out/)
```

Refresh the data bundle from the pipeline root: `make export-web` (runs
`python app/export_web.py`; part of `make refresh`). `/text` is the plain-text
fallback of the same briefing.
