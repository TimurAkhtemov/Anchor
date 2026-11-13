# Anchor — web

The Anchor site: the "Morning paper" dashboard (briefing, macro → sectors →
holdings) with a guided reading of the daily LLM briefing. Next.js 16 static
export, no backend, no credentials. The public build renders the committed
`public/data/anchor.json` (demo portfolio only, by construction) and is live at
<https://anchor-pi-five.vercel.app> (Vercel, root directory `web/`). The private
build renders a bundle in `var/` and is served on localhost only.

```bash
npm run dev        # local dev server
npm run build      # static export -> out/
npm run typecheck  # tsc --noEmit (build first: it generates next-env.d.ts)
npm run test:e2e   # Playwright — resolver unit tests + browser smoke (serves out/)
```

Refresh the data bundle from the pipeline root: `make export-web` (runs
`python app/export_web.py`; part of `make refresh`). `/text` is the plain-text
fallback of the same briefing.
