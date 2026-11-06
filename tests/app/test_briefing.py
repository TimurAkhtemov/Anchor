"""CI-side proof of the briefing generator (design: docs/llm_copilot_briefing_design.md).

Everything runs against fakes — no Ollama, no BigQuery, no network. The pure
seams (build_context, _parse_news_items, validate_briefing) make "did the right
numbers get into the prompt / out of the model" a deterministic test.
"""
from __future__ import annotations

import importlib
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from app import briefing

NAN = float("nan")


class FakeProvider:
    """Records the (system, prompt, format_schema) it was called with and returns
    a canned response."""

    name = "fake"
    model = "fake-model"

    def __init__(self, output: str, is_local: bool = True):
        self.output = output
        self.is_local = is_local
        self.system = None
        self.prompt = None
        self.format_schema = None

    def generate(self, system: str, prompt: str, *, format_schema=None) -> str:
        self.system, self.prompt, self.format_schema = system, prompt, format_schema
        return self.output


class _FakeJob:
    def __init__(self, df=None):
        self._df = df

    def to_dataframe(self):
        return self._df

    def result(self):
        return None


class FakeBQClient:
    """Serves canned mart frames by table name; records table loads."""

    def __init__(self, marts: dict[str, pd.DataFrame]):
        self.marts = marts
        self.loads: list[tuple[pd.DataFrame, str, object]] = []

    def query(self, sql: str) -> _FakeJob:
        table = sql.split("`")[1].split(".")[-1]
        return _FakeJob(self.marts[table])

    def load_table_from_dataframe(self, df, table_id, job_config=None) -> _FakeJob:
        self.loads.append((df, table_id, job_config))
        return _FakeJob()


def _marts() -> dict[str, pd.DataFrame]:
    """Six context frames with distinctive values the assertions below quote."""
    return {
        "as_of_calendar": pd.DataFrame([{"as_of_date": "2026-07-08"}]),
        "macro_regime": pd.DataFrame(
            [
                {
                    "regime_summary": "Rates steady, inflation rising, labor stable",
                    "rates_state": "steady",
                    "inflation_state": "rising",
                    "labor_state": "stable",
                }
            ]
        ),
        "macro_indicators": pd.DataFrame(
            [
                {"indicator_key": "fed_funds_rate", "current_value": 3.63, "delta_3mo": -0.01, "direction": "down"},
                {"indicator_key": "ten_year_yield", "current_value": 4.55, "delta_3mo": 0.22, "direction": "up"},
                {"indicator_key": "inflation_yoy", "current_value": 4.17, "delta_3mo": 1.73, "direction": "up"},
                {"indicator_key": "unemployment_rate", "current_value": 4.20, "delta_3mo": -0.10, "direction": "down"},
            ]
        ),
        "sector_performance": pd.DataFrame(
            [
                {"sector": "Technology", "etf_ticker": "XLK", "return_1m_pct": 2.10,
                 "return_ytd_pct": 9.55, "return_1y_pct": 21.30,
                 "rate_comovement_label": "moves against rates"},
                {"sector": "Energy", "etf_ticker": "XLE", "return_1m_pct": -2.89,
                 "return_ytd_pct": 26.07, "return_1y_pct": 33.04,
                 "rate_comovement_label": "moves with rates"},
            ]
        ),
        "portfolio_composition": pd.DataFrame(
            [
                {"ticker": "AAPL", "description": "Apple Inc.", "asset_class": "equity",
                 "weight_pct": 40.0, "valuation_source": "market",
                 "return_1m_pct": 1.97, "return_ytd_pct": 12.34, "return_1y_pct": 49.86,
                 "unrealized_gain_pct": 40.12},
                {"ticker": "BND", "description": "Total Bond Market", "asset_class": "fixed_income",
                 "weight_pct": 35.0, "valuation_source": "market",
                 "return_1m_pct": 0.15, "return_ytd_pct": -0.23, "return_1y_pct": 3.46,
                 "unrealized_gain_pct": -3.07},
                {"ticker": "SPAXX", "description": "Money Market", "asset_class": "cash",
                 "weight_pct": 25.0, "valuation_source": "source",
                 "return_1m_pct": NAN, "return_ytd_pct": NAN, "return_1y_pct": NAN,
                 "unrealized_gain_pct": NAN},
            ]
        ),
        "holdings_benchmarks": pd.DataFrame(
            [
                {"holding_ticker": "AAPL", "benchmark_type": "sector", "benchmark_etf": "XLK",
                 "relative_1m_pp": 0.85, "relative_ytd_pp": -10.82, "relative_1y_pp": 6.79,
                 "label_1m": "ahead", "label_ytd": "behind", "label_1y": "ahead"},
                # No label_* columns on this row: the packet must tolerate their absence.
                {"holding_ticker": "AAPL", "benchmark_type": "cap_style", "benchmark_etf": "SPY",
                 "relative_1m_pp": 0.65, "relative_ytd_pp": 5.60, "relative_1y_pp": 28.44},
            ]
        ),
    }


# A valid tour whose every figure exists verbatim in the _marts() packet.
GOOD_STEPS = [
    {"id": 1, "target": {"kind": "regime"},
     "narration": "The macro regime is steady rates with rising inflation and stable labor conditions across the quarter.",
     "figures": [], "headline_refs": []},
    {"id": 2, "target": {"kind": "indicator", "key": "Inflation (YoY)"},
     "narration": "Inflation (YoY) now runs at 4.17%, up +1.73 pp over three months.",
     "figures": ["4.17%", "+1.73 pp"], "headline_refs": []},
    {"id": 3, "target": {"kind": "sector", "key": "XLK"},
     "narration": "Technology gained +2.10% over the month and moves against rates, extending a +21.30% year.",
     "figures": ["+2.10%", "+21.30%"], "headline_refs": []},
    {"id": 4, "target": {"kind": "allocation"},
     "narration": "Equity remains 40.0% of the portfolio, with fixed income at 35.0% and cash holding 25.0%.",
     "figures": ["40.0%", "35.0%", "25.0%"], "headline_refs": []},
    {"id": 5, "target": {"kind": "holding", "key": "AAPL"},
     "narration": "AAPL returned +12.34% YTD and sits +0.85 pp ahead of XLK on the month, carrying unrealized gains of +40.12%.",
     "figures": ["+12.34%", "+0.85 pp", "+40.12%"], "headline_refs": []},
    {"id": 6, "target": {"kind": "holding", "key": "BND"},
     "narration": "BND stayed quiet at +0.15% for the month and -0.23% YTD, in line with its benchmarks so far this year.",
     "figures": ["+0.15%", "-0.23%"], "headline_refs": []},
]
GOOD_TOUR = json.dumps({"steps": GOOD_STEPS})


# --- 1. build_context: the packet carries the exact mart numbers ---------------


def test_build_context_contains_exact_mart_numbers():
    ctx = briefing.build_context(_marts(), news=[])

    assert "as of 2026-07-08" in ctx
    assert "Rates steady, inflation rising, labor stable" in ctx
    assert "Fed Funds Rate: 3.63%" in ctx
    assert "+1.73 pp" in ctx  # indicator deltas carry the pp unit explicitly
    assert "Technology (XLK): 1M +2.10%" in ctx
    assert "moves with rates" in ctx  # comovement label verbatim
    assert "equity: 40.0%" in ctx  # allocation line
    assert "YTD +12.34%" in ctx
    # The mart's own ahead/behind verdicts ride beside the pp figures...
    assert "vs XLK (sector): 1M +0.85 pp (ahead), YTD -10.82 pp (behind)" in ctx
    # ...and rows without label columns still render, just without tags.
    assert "vs SPY (cap_style): 1M +0.65 pp," in ctx
    assert "unrealized +40.12%" in ctx
    # Reading order: DATA before NEWS.
    assert ctx.index(briefing.DATA_HEADER) < ctx.index(briefing.NEWS_HEADER)


def test_build_context_renders_missing_returns_without_nan():
    ctx = briefing.build_context(_marts(), news=[])
    assert "nan" not in ctx.lower()
    assert "SPAXX" in ctx
    assert "valued at source; no market returns" in ctx


# --- 2. news parsing against the canned nested-content shape -------------------

_NOW = datetime(2026, 7, 10, tzinfo=timezone.utc)


def _raw_item(title="Apple ships something", pub="2026-07-09T12:00:00Z",
              provider="Newswire", summary="A summary."):
    return {
        "content": {
            "title": title,
            "summary": summary,
            "pubDate": pub,
            "provider": {"displayName": provider},
        }
    }


def test_parse_news_items_parses_nested_content_shape():
    items = briefing._parse_news_items("AAPL", [_raw_item()], now=_NOW)
    assert items == [
        {
            "ticker": "AAPL",
            "title": "Apple ships something",
            "summary": "A summary.",
            "provider": "Newswire",
            "pub_date": "2026-07-09",
        }
    ]


def test_parse_news_items_filters_stale_and_malformed():
    raw = [
        _raw_item(pub="2026-07-01T00:00:00Z"),        # 9 days old -> stale
        {"content": {"pubDate": "2026-07-09T00:00:00Z"}},  # no title
        {},                                            # no content at all
        _raw_item(title="Fresh one"),
    ]
    items = briefing._parse_news_items("AAPL", raw, now=_NOW)
    assert [n["title"] for n in items] == ["Fresh one"]


def test_parse_news_items_caps_per_ticker_newest_first():
    raw = [_raw_item(title=f"day {d}", pub=f"2026-07-0{d}T00:00:00Z") for d in range(5, 10)]
    items = briefing._parse_news_items("AAPL", raw, now=_NOW)
    assert [n["title"] for n in items] == ["day 9", "day 8", "day 7"]


# --- 3. end-to-end with fakes ---------------------------------------------------


def test_generate_end_to_end_writes_valid_artifact():
    provider = FakeProvider(GOOD_TOUR)
    client = FakeBQClient(_marts())

    summary = briefing.generate("demo", provider, client, skip_news=True)

    assert provider.system == briefing.SYSTEM_PROMPT
    assert briefing.DATA_HEADER in provider.prompt
    assert provider.format_schema == briefing.TOUR_SCHEMA

    assert len(client.loads) == 1
    artifact, table_id, job_config = client.loads[0]
    assert table_id.endswith("anchor_marts.copilot_briefing")
    assert job_config.write_disposition == "WRITE_TRUNCATE"
    assert list(artifact.columns) == briefing.ARTIFACT_COLUMNS
    assert len(artifact) == 1
    row = artifact.iloc[0]
    assert row["horizon"] == "all"
    assert row["briefing_md"] == briefing.assemble_briefing_md(GOOD_STEPS)
    assert row["as_of_date"] == date(2026, 7, 8)
    assert row["generated_at"].tzinfo is not None
    assert json.loads(row["sources"]) == []
    assert json.loads(row["briefing_json"])["steps"] == GOOD_STEPS

    assert summary["as_of_date"] == "2026-07-08"
    assert summary["steps"] == 6
    assert summary["headlines"] == 0
    assert summary["warnings"] == []  # every GOOD_STEPS figure grounds


def test_generate_does_not_write_when_validation_fails():
    provider = FakeProvider("not json at all")  # unparseable tour -> hard failure
    client = FakeBQClient(_marts())
    with pytest.raises(briefing.ValidationError):
        briefing.generate("demo", provider, client, skip_news=True)
    assert client.loads == []  # strict policy: nothing written on failure


def test_generate_does_not_write_when_steps_invalid():
    bad = [dict(s) for s in GOOD_STEPS]
    bad[4] = {**bad[4], "narration": "TICKR surged 77.77% overnight.", "figures": ["77.77%"]}
    provider = FakeProvider(json.dumps({"steps": bad}))
    client = FakeBQClient(_marts())
    with pytest.raises(briefing.ValidationError, match="77.77"):
        briefing.generate("demo", provider, client, skip_news=True)
    assert client.loads == []


# --- 3b. tour-step validation + assembly -------------------------------------------


def _steps_setup():
    marts = _marts()
    context = briefing.build_context(marts, news=[])
    return marts, context


def test_validate_steps_accepts_good_tour():
    marts, context = _steps_setup()
    result = briefing.validate_steps(GOOD_STEPS, marts, context, n_news=0)
    assert result.ok, result.errors


def test_validate_steps_rejects_unknown_target_key():
    marts, context = _steps_setup()
    bad = [dict(s) for s in GOOD_STEPS]
    bad[4] = {**bad[4], "target": {"kind": "holding", "key": "TSLA"}}
    result = briefing.validate_steps(bad, marts, context, n_news=0)
    assert any("TSLA" in e for e in result.errors)


def test_validate_steps_rejects_reading_order_violation():
    marts, context = _steps_setup()
    bad = [GOOD_STEPS[0], GOOD_STEPS[1], GOOD_STEPS[3], GOOD_STEPS[2],
           GOOD_STEPS[4], GOOD_STEPS[5]]  # allocation before sector
    result = briefing.validate_steps(bad, marts, context, n_news=0)
    assert any("reading order" in e for e in result.errors)


def test_validate_steps_rejects_figure_absent_from_narration():
    marts, context = _steps_setup()
    bad = [dict(s) for s in GOOD_STEPS]
    bad[1] = {**bad[1], "figures": ["4.17%", "+0.22 pp"]}  # +0.22 pp never narrated
    result = briefing.validate_steps(bad, marts, context, n_news=0)
    assert any("not present in its narration" in e for e in result.errors)


def test_validate_steps_rejects_junk_narration_prefix():
    marts, context = _steps_setup()
    bad = [dict(s) for s in GOOD_STEPS]
    bad[5] = {**bad[5], "narration": "narration la " + bad[5]["narration"], "figures": []}
    result = briefing.validate_steps(bad, marts, context, n_news=0)
    assert any("junk" in e for e in result.errors)


def test_validate_steps_rejects_bad_headline_ref():
    marts, context = _steps_setup()
    bad = [dict(s) for s in GOOD_STEPS]
    bad[5] = {**bad[5], "headline_refs": [3]}
    result = briefing.validate_steps(bad, marts, context, n_news=2)
    assert any("headline_ref" in e for e in result.errors)


def test_validate_steps_requires_regime_first_and_one_allocation():
    marts, context = _steps_setup()
    no_regime = GOOD_STEPS[1:] + [GOOD_STEPS[5]]  # keep count >= 6
    result = briefing.validate_steps(no_regime, marts, context, n_news=0)
    assert any("regime" in e for e in result.errors)


def test_validate_steps_enforces_count_bounds():
    marts, context = _steps_setup()
    result = briefing.validate_steps(GOOD_STEPS[:3], marts, context, n_news=0)
    assert not result.ok


def test_assemble_briefing_md_groups_paragraphs_by_kind():
    md = briefing.assemble_briefing_md(GOOD_STEPS)
    paragraphs = md.split("\n\n")
    assert len(paragraphs) == 3
    assert "macro regime" in paragraphs[0] and "Inflation (YoY)" in paragraphs[0]
    assert paragraphs[1].startswith("Technology")
    assert paragraphs[2].startswith("Equity remains 40.0%")
    assert "BND stayed quiet" in paragraphs[2]


# --- 4. validator units -----------------------------------------------------------

_CTX = (
    f"{briefing.DATA_HEADER} (as of 2026-07-08)\n"
    "- Inflation (YoY): 3.21% (3-mo change +0.40 pp, up)\n"
    "- AAPL: YTD +12.34%\n"
    f"{briefing.NEWS_HEADER}\n"
    '- [AAPL] "Stock jumps 77.77% says pundit" — Newswire, 2026-07-09\n'
)

_PAD = " Context filler so the length check passes." * 6


# --- 3c. forward-looking guard, retry, dry run ---------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"


class SequenceProvider(FakeProvider):
    """Returns successive canned outputs; counts calls and records prompts."""

    def __init__(self, outputs: list[str]):
        super().__init__(outputs[0])
        self.outputs = list(outputs)
        self.calls = 0
        self.prompts: list[str] = []

    def generate(self, system, prompt, *, format_schema=None):
        out = self.outputs[min(self.calls, len(self.outputs) - 1)]
        self.calls += 1
        self.prompts.append(prompt)
        self.system, self.prompt, self.format_schema = system, prompt, format_schema
        return out


def _with_narration(idx: int, text: str) -> str:
    steps = [dict(s) for s in GOOD_STEPS]
    steps[idx] = {**steps[idx], "narration": text, "figures": []}
    return json.dumps({"steps": steps})


def test_validate_steps_rejects_prediction():
    marts, context = _steps_setup()
    steps = [dict(s) for s in GOOD_STEPS]
    steps[2] = {**steps[2], "narration": "Technology will provide a near-term catalyst.", "figures": []}
    result = briefing.validate_steps(steps, marts, context, n_news=0)
    assert any("step 3" in e and "'will'" in e for e in result.errors)


def test_validate_steps_rejects_recommendation():
    marts, context = _steps_setup()
    steps = [dict(s) for s in GOOD_STEPS]
    steps[3] = {**steps[3], "narration": "Given the mix, investors should buy more bonds.", "figures": []}
    result = briefing.validate_steps(steps, marts, context, n_news=0)
    assert any("step 4" in e for e in result.errors)


def test_forward_look_ignores_sell_off():
    assert briefing.find_forward_looking("A sell-off in energy weighed on the sector.") == []
    assert briefing.find_forward_looking("The selloff in energy deepened.") == []
    assert briefing.find_forward_looking("Investors sell the dip.") != []


def test_find_forward_looking_phrases():
    for text in [
        "Rates won't move.", "It is going to rally.", "Expected to rise.",
        "Likely to fall.", "Poised to gain.", "Set to report.",
        "It could continue higher.", "That may help margins.",
        "We recommend caution.", "Consider a trim.",
    ]:
        assert briefing.find_forward_looking(text), text
    assert briefing.find_forward_looking("Energy led the month, up +12.64%.") == []


def test_september_briefing_flags_only_the_apple_step():
    steps = json.loads((FIXTURES / "briefing_2026_09_steps.json").read_text())
    flagged = [s["id"] for s in steps if briefing.find_forward_looking(s["narration"])]
    assert flagged == [6]


def test_generate_retries_once_on_validation_failure():
    bad = _with_narration(2, "Technology will provide a near-term catalyst.")
    provider = SequenceProvider([bad, GOOD_TOUR])
    client = FakeBQClient(_marts())
    summary = briefing.generate("demo", provider, client, skip_news=True)
    assert provider.calls == 2
    assert len(client.loads) == 1
    assert summary["steps"] == 6


def test_generate_fails_after_second_invalid():
    bad = _with_narration(2, "Technology will provide a near-term catalyst.")
    provider = SequenceProvider([bad, bad, GOOD_TOUR])
    client = FakeBQClient(_marts())
    with pytest.raises(briefing.ValidationError):
        briefing.generate("demo", provider, client, skip_news=True, max_attempts=2)
    assert provider.calls == 2
    assert client.loads == []


def test_generate_does_not_retry_on_provider_error():
    class Boom(FakeProvider):
        calls = 0

        def generate(self, system, prompt, *, format_schema=None):
            Boom.calls += 1
            raise briefing.BriefingError("api down")

    with pytest.raises(briefing.BriefingError):
        briefing.generate("demo", Boom(""), FakeBQClient(_marts()), skip_news=True)
    assert Boom.calls == 1


def test_real_retry_log_withholds_validation_detail(capsys):
    """Validation errors quote tickers, figures, and narration, and the real
    portfolio's stdout is a LaunchAgent log file."""
    bad = _with_narration(2, "Technology will provide a near-term catalyst.")
    provider = SequenceProvider([bad, GOOD_TOUR])
    briefing.generate("real", provider, FakeBQClient(_marts()), skip_news=True)
    printed = capsys.readouterr().out
    assert "rejected" in printed
    assert "step 3" not in printed and "will" not in printed


def test_demo_retry_log_keeps_validation_detail(capsys):
    bad = _with_narration(2, "Technology will provide a near-term catalyst.")
    provider = SequenceProvider([bad, GOOD_TOUR])
    briefing.generate("demo", provider, FakeBQClient(_marts()), skip_news=True)
    assert "step 3" in capsys.readouterr().out


def test_describe_failure_only_withholds_real_validation_errors():
    secret = briefing.ValidationError("step 3: holding key 'ZZPRIVATE' not in the packet")
    assert "ZZPRIVATE" not in briefing.describe_failure(secret, "real")
    assert "ZZPRIVATE" in briefing.describe_failure(secret, "demo")
    # Provider failures carry the reason an operator needs, and no portfolio data.
    down = briefing.BriefingError("Ollama not reachable")
    assert "Ollama not reachable" in briefing.describe_failure(down, "real")


def test_describe_warnings_counts_for_real():
    warnings = ["cited '12.5%' not found in the DATA packet"]
    assert "12.5" not in " ".join(briefing.describe_warnings(warnings, "real"))
    assert "1 " in briefing.describe_warnings(warnings, "real")[0]
    assert briefing.describe_warnings(warnings, "demo") == warnings
    assert briefing.describe_warnings([], "real") == []


def test_real_generate_silences_yfinance_logger(monkeypatch):
    """yfinance logs fetch failures with the ticker in the message."""
    logger = logging.getLogger("yfinance")
    monkeypatch.setattr(logger, "level", logging.NOTSET)
    briefing.generate("real", FakeProvider(GOOD_TOUR), FakeBQClient(_marts()), skip_news=True)
    assert logger.level == logging.CRITICAL


@pytest.fixture
def briefing_cli(monkeypatch):
    """app/generate_briefing.py's main(), which imports `briefing` as a top-level module."""
    monkeypatch.syspath_prepend(str(Path(briefing.__file__).parent))
    module = importlib.import_module("generate_briefing")
    inner = module.briefing
    monkeypatch.setattr(inner, "build_provider", lambda _portfolio: object())
    monkeypatch.setattr(inner, "build_bigquery_client", lambda: object())
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr(sys, "argv", ["generate_briefing.py", "--portfolio", "real"])
    return module, inner


def test_cli_failure_withholds_real_validation_detail(briefing_cli, monkeypatch, capsys):
    module, inner = briefing_cli

    def fail(*_a, **_k):
        raise inner.ValidationError("step 3: holding key 'ZZPRIVATE' not in the packet")

    monkeypatch.setattr(inner, "generate", fail)
    with pytest.raises(SystemExit) as caught:
        module.main()
    assert caught.value.code == 1
    streams = capsys.readouterr()
    assert "briefing generation failed" in streams.err
    assert "ZZPRIVATE" not in streams.out + streams.err


def test_cli_success_withholds_real_audit_figures(briefing_cli, monkeypatch, capsys):
    module, inner = briefing_cli
    summary = {
        "warnings": ["cited '12.5%' not found in the DATA packet"],
        "table": "t", "as_of_date": "2026-11-05", "steps": 6, "chars": 900,
        "headlines": 0, "model": "m",
    }
    monkeypatch.setattr(inner, "generate", lambda *_a, **_k: summary)
    module.main()
    printed = capsys.readouterr().out
    assert "WARNING (numeric audit)" in printed
    assert "12.5" not in printed


def test_dry_run_does_not_write():
    provider = FakeProvider(GOOD_TOUR)
    client = FakeBQClient(_marts())
    summary = briefing.generate("demo", provider, client, skip_news=True, dry_run=True)
    assert client.loads == []
    assert summary["steps"] == GOOD_STEPS
    assert summary["table"] is None


def test_validate_briefing_rejects_empty():
    result = briefing.validate_briefing("   ", _CTX)
    assert not result.ok
    assert "empty" in result.errors[0]


def test_validate_briefing_rejects_think_tags():
    text = "<think>reasoning</think> A briefing." + _PAD
    result = briefing.validate_briefing(text, _CTX)
    assert not result.ok
    assert any("<think>" in e for e in result.errors)


def test_validate_briefing_rejects_length_out_of_bounds():
    assert not briefing.validate_briefing("ok", _CTX).ok
    assert not briefing.validate_briefing("x" * (briefing.MAX_BRIEFING_CHARS + 1), _CTX).ok


def test_validate_briefing_warns_on_ungrounded_numbers():
    text = "Inflation sits at 3.21% but the fund surged 99.99% this month." + _PAD
    result = briefing.validate_briefing(text, _CTX)
    assert result.ok  # numeric audit is warning-level in v1
    assert any("99.99" in w for w in result.warnings)
    assert not any("3.21" in w for w in result.warnings)


def test_validate_briefing_tolerates_rounded_numbers():
    text = "Inflation sits at 3.2%, roughly 3% on the year, with AAPL up +12.34%." + _PAD
    result = briefing.validate_briefing(text, _CTX)
    assert result.warnings == []


def test_validate_briefing_news_numbers_do_not_ground():
    text = "One holding reportedly jumped 77.77% according to a pundit." + _PAD
    result = briefing.validate_briefing(text, _CTX)
    assert any("77.77" in w for w in result.warnings)


# --- 5. privacy: structural, before any I/O ---------------------------------------


def test_generate_refuses_real_with_nonlocal_provider():
    provider = FakeProvider("anything", is_local=False)
    with pytest.raises(briefing.PrivacyError):
        # client=None proves the guard fires before any BigQuery/network use.
        briefing.generate("real", provider, client=None)


def test_generate_rejects_unknown_portfolio():
    with pytest.raises(ValueError):
        briefing.generate("staging", FakeProvider("x"), client=None)


# The ANCHOR_BRIEFING_PROVIDER factory: same interlock, one layer earlier —
# a cloud provider for the real portfolio must fail at construction, before a
# client object even exists.


def test_build_provider_defaults_to_ollama(monkeypatch):
    monkeypatch.delenv("ANCHOR_BRIEFING_PROVIDER", raising=False)
    assert isinstance(briefing.build_provider("demo"), briefing.OllamaProvider)


def test_build_provider_anthropic_for_demo(monkeypatch):
    monkeypatch.setenv("ANCHOR_BRIEFING_PROVIDER", "anthropic")
    # No API key in the environment: construction must not touch the SDK or
    # the network — generate() is the only network surface.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANCHOR_BRIEFING_CLOUD_MODEL", raising=False)
    provider = briefing.build_provider("demo")
    assert isinstance(provider, briefing.AnthropicProvider)
    assert provider.is_local is False
    assert provider.model == briefing.DEFAULT_ANTHROPIC_MODEL


def test_build_provider_cloud_model_env_override(monkeypatch):
    monkeypatch.setenv("ANCHOR_BRIEFING_PROVIDER", "anthropic")
    monkeypatch.setenv("ANCHOR_BRIEFING_CLOUD_MODEL", "claude-sonnet-5")
    assert briefing.build_provider("demo").model == "claude-sonnet-5"


def test_build_provider_refuses_cloud_for_real(monkeypatch):
    monkeypatch.setenv("ANCHOR_BRIEFING_PROVIDER", "anthropic")
    with pytest.raises(briefing.PrivacyError):
        briefing.build_provider("real")


def test_build_provider_real_stays_local_by_default(monkeypatch):
    monkeypatch.delenv("ANCHOR_BRIEFING_PROVIDER", raising=False)
    assert briefing.build_provider("real").is_local is True


def test_build_provider_rejects_unknown_name(monkeypatch):
    monkeypatch.setenv("ANCHOR_BRIEFING_PROVIDER", "openai")
    with pytest.raises(briefing.BriefingError):
        briefing.build_provider("demo")


# --- 6. news scoping helper ---------------------------------------------------------


def test_held_tickers_excludes_cash_and_source_valued():
    composition = pd.DataFrame(
        [
            {"ticker": "PLAN_ALT", "asset_class": "alt", "weight_pct": 50.0, "valuation_source": "source"},
            {"ticker": "AAPL", "asset_class": "equity", "weight_pct": 30.0, "valuation_source": "market"},
            {"ticker": "SPAXX", "asset_class": "cash", "weight_pct": 12.0, "valuation_source": "source"},
            {"ticker": "BND", "asset_class": "fixed_income", "weight_pct": 8.0, "valuation_source": "market"},
        ]
    )
    assert briefing.held_tickers(composition) == ["AAPL", "BND"]


def test_anthropic_provider_request_shape(monkeypatch):
    """No network: a fake `anthropic` module records the request kwargs."""
    import sys
    import types

    seen: dict = {}

    class _Stream:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get_final_message(self):
            block = types.SimpleNamespace(type="text", text=' {"steps": []} ')
            usage = types.SimpleNamespace(input_tokens=1200, output_tokens=340)
            return types.SimpleNamespace(stop_reason="end_turn", content=[block], usage=usage)

    class _Messages:
        def stream(self, **kwargs):
            seen.update(kwargs)
            return _Stream()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = lambda: types.SimpleNamespace(messages=_Messages())
    for name in ("AuthenticationError", "APIStatusError", "APIConnectionError"):
        setattr(fake, name, type(name, (Exception,), {}))
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    provider = briefing.AnthropicProvider(model="claude-sonnet-5-5")
    out = provider.generate("sys", "prompt", format_schema={"type": "object"})
    assert out == '{"steps": []}'
    assert provider.usage == [
        {
            "input_tokens": 1200,
            "output_tokens": 340,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        }
    ]
    assert seen["model"] == "claude-sonnet-5-5"
    assert seen["thinking"] == {"type": "adaptive"}
    assert seen["output_config"]["effort"] == "medium"
    assert seen["output_config"]["format"] == {"type": "json_schema", "schema": {"type": "object"}}
    assert "temperature" not in seen


# --- 5. validation retries + llama-server provider ---------------------------------


def _bad_tour():
    bad = [dict(s) for s in GOOD_STEPS]
    bad[4] = {**bad[4], "narration": "TICKR surged 77.77% overnight.", "figures": ["77.77%"]}
    return json.dumps({"steps": bad})


def test_generate_retries_with_rejection_feedback_then_writes():
    provider = SequenceProvider([_bad_tour(), GOOD_TOUR])
    client = FakeBQClient(_marts())

    summary = briefing.generate("demo", provider, client, skip_news=True)

    assert len(provider.prompts) == 2
    assert briefing.REJECTION_HEADER not in provider.prompts[0]
    assert briefing.REJECTION_HEADER in provider.prompts[1]
    assert "77.77" in provider.prompts[1]  # the validator's verdict is fed back
    assert len(client.loads) == 1  # written exactly once, after the good attempt
    assert summary["steps"] == 6


def test_generate_gives_up_after_max_attempts_and_never_writes():
    provider = SequenceProvider([_bad_tour(), _bad_tour(), _bad_tour()])
    client = FakeBQClient(_marts())
    with pytest.raises(briefing.ValidationError, match="all 3 attempts"):
        briefing.generate("demo", provider, client, skip_news=True, max_attempts=3)
    assert len(provider.prompts) == 3
    assert client.loads == []


def test_generate_attempts_env_override(monkeypatch):
    monkeypatch.setenv("ANCHOR_BRIEFING_ATTEMPTS", "1")
    provider = SequenceProvider([_bad_tour()])
    with pytest.raises(briefing.ValidationError, match="all 1 attempts"):
        briefing.generate("demo", provider, FakeBQClient(_marts()), skip_news=True)


def test_build_provider_llama_server_is_local(monkeypatch):
    monkeypatch.setenv("ANCHOR_BRIEFING_PROVIDER", "llama-server")
    monkeypatch.setenv("ANCHOR_LLAMA_SERVER_HOST", "http://127.0.0.1:9999/")
    provider = briefing.build_provider("real")  # local -> allowed for real
    assert isinstance(provider, briefing.LlamaServerProvider)
    assert provider.is_local is True
    assert provider.host == "http://127.0.0.1:9999"


def test_llama_server_provider_request_shape(monkeypatch):
    import requests

    calls = {}

    class Resp:
        def __init__(self, payload):
            self._p = payload

        def raise_for_status(self):
            pass

        def json(self):
            return self._p

    def fake_get(url, timeout):
        calls["get"] = url
        return Resp({"data": [{"id": "qwen3.6-35b-a3b"}]})

    def fake_post(url, json, timeout):
        calls["post"] = (url, json)
        return Resp({"choices": [{"message": {"content": ' {"steps": []} ', "reasoning_content": "…"}}]})

    monkeypatch.setattr(requests, "get", fake_get)
    monkeypatch.setattr(requests, "post", fake_post)

    provider = briefing.LlamaServerProvider(host="http://h:1")
    out = provider.generate("SYS", "PROMPT", format_schema={"type": "object"})

    assert out == '{"steps": []}'
    assert provider.model == "qwen3.6-35b-a3b"  # the served id, not the request's
    url, body = calls["post"]
    assert url == "http://h:1/v1/chat/completions"
    assert body["messages"][0] == {"role": "system", "content": "SYS"}
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}
