"""Generate the LLM copilot briefing and write it into the active marts dataset.

Pipeline-time step (see docs/llm_copilot_briefing_design.md): reads the served
marts, fetches held-ticker headlines, generates via the configured provider
(local Ollama by default), validates, then WRITE_TRUNCATEs `copilot_briefing`.
A failure exits non-zero, which halts `make refresh` before the snapshot
export — the strict failure policy.

Run locally (needs BigQuery creds + Ollama running, unless on the cloud provider):
    python app/generate_briefing.py --portfolio demo
    python app/generate_briefing.py --portfolio real   # local provider enforced in code

Config (.env, optional):
    ANCHOR_BRIEFING_PROVIDER     ollama (default) | anthropic — cloud is DEMO ONLY;
                                 combined with --portfolio real it hard-fails
    ANCHOR_BRIEFING_MODEL        Ollama model (default gemma4:31b)
    OLLAMA_HOST                  Ollama endpoint
    ANCHOR_BRIEFING_CLOUD_MODEL  Anthropic model (default claude-opus-4-8)
    ANTHROPIC_API_KEY            required for the anthropic provider
"""

from __future__ import annotations

import argparse
import sys

import briefing


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--portfolio", choices=["demo", "real"], default="demo")
    parser.add_argument(
        "--no-news", action="store_true", help="skip yfinance headlines (offline debugging)"
    )
    args = parser.parse_args()

    from dotenv import load_dotenv  # model/host config lives in .env like the other secrets

    load_dotenv()

    try:
        # Provider resolution first: the cloud+real privacy interlock must fire
        # before any client (BigQuery included) is even constructed.
        provider = briefing.build_provider(args.portfolio)
        client = briefing.build_bigquery_client()
        summary = briefing.generate(
            args.portfolio, provider, client, skip_news=args.no_news
        )
    except briefing.BriefingError as exc:
        print(f"briefing generation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    for warning in summary["warnings"]:
        print(f"  WARNING (numeric audit): {warning}")
    print(
        f"  wrote {summary['table']} — as_of {summary['as_of_date']}, "
        f"{summary['steps']} tour steps, {summary['chars']} chars, "
        f"{summary['headlines']} headlines, model {summary['model']}"
    )


if __name__ == "__main__":
    main()
