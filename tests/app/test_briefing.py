"""CI-side proof of the briefing generator (design: docs/llm_copilot_briefing_design.md).

Everything runs against fakes — no Ollama, no BigQuery, no network. The pure
seams (build_context, _parse_news_items, validate_briefing) make "did the right
numbers get into the prompt / out of the model" a deterministic test.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

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
