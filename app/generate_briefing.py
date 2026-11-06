"""Generate the LLM copilot briefing and write it into the active marts dataset.

Pipeline-time step (see docs/llm_copilot_briefing_design.md): reads the served
marts, fetches held-ticker headlines, generates via the configured provider
(local Ollama by default), validates, then WRITE_TRUNCATEs `copilot_briefing`.
A failure exits non-zero, which halts `make refresh` before the snapshot
export — the strict failure policy.

Run locally (needs BigQuery creds + Ollama running, unless on the cloud provider):
    python app/generate_briefing.py --portfolio demo
    python app/generate_briefing.py --portfolio real   # local provider enforced in code

    python app/generate_briefing.py --dry-run --out briefing.json  # validate, no write

Config (environment; .env for local non-secret settings):
    ANCHOR_BRIEFING_PROVIDER     ollama (default) | anthropic — cloud is DEMO ONLY;
                                 combined with --portfolio real it hard-fails
    ANCHOR_BRIEFING_MODEL        Ollama model (default qwen3.6:35b)
    OLLAMA_HOST                  Ollama endpoint
    ANCHOR_BRIEFING_CLOUD_MODEL  Anthropic model (default claude-sonnet-5-5)
    ANTHROPIC_API_KEY            required for the anthropic provider; set in the
                                 shell or GitHub secrets, not .env
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import briefing


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--portfolio", choices=["demo", "real"], default="demo")
    parser.add_argument(
        "--no-news", action="store_true", help="skip yfinance headlines (offline debugging)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="generate and validate, but do not write to BigQuery",
    )
    parser.add_argument(
        "--out", type=Path, help="with --dry-run: save the validated result as JSON here"
    )
    args = parser.parse_args()
    if args.out and not args.dry_run:
        parser.error("--out requires --dry-run")

    from dotenv import load_dotenv  # model/host config lives in .env like the other secrets

    load_dotenv()

    try:
        # Provider resolution first: the cloud+real privacy interlock must fire
        # before any client (BigQuery included) is even constructed.
        provider = briefing.build_provider(args.portfolio)
        client = briefing.build_bigquery_client()
        summary = briefing.generate(
            args.portfolio, provider, client,
            skip_news=args.no_news, dry_run=args.dry_run,
        )
    except briefing.BriefingError as exc:
        print(f"briefing generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        if args.out:
            args.out.write_text(json.dumps(summary, indent=2, default=str))
        print(
            f"  dry run, nothing written — as_of {summary['as_of_date']}, "
            f"{len(summary['steps'])} tour steps, {summary['chars']} chars, "
            f"model {summary['model']}" + (f", saved to {args.out}" if args.out else "")
        )
        return

    for warning in summary["warnings"]:
        print(f"  WARNING (numeric audit): {warning}")
    print(
        f"  wrote {summary['table']} — as_of {summary['as_of_date']}, "
        f"{summary['steps']} tour steps, {summary['chars']} chars, "
        f"{summary['headlines']} headlines, model {summary['model']}"
    )


if __name__ == "__main__":
    main()
