# Make It Real — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Anchor's static 6-stock watchlist with real Fidelity portfolio holdings, benchmarked per asset class (equity / equity fund / fixed income / cash), sized by actual weights, with a structural demo/private split — per the locked spec `docs/make_it_real_design.md`.

**Architecture:** Holdings become data, not config: a loader normalizes Fidelity CSV (later SnapTrade) into `raw_holdings.*` bronze tables; the yfinance ticker universe derives from holdings ∪ benchmark ETFs; dbt classifies each holding (yfinance `quote_type` + a fund-classification seed) and routes it to asset-class-appropriate benchmarks; gold ships two marts (`holdings_benchmarks` reworked, `portfolio_composition` new). Demo builds into `anchor_*` (public path), real builds into `anchor_*_private` (local only), enforced by a compile-time interlock.

**Tech Stack:** Python 3 (`venv/`), pandas, google-cloud-bigquery, yfinance, pytest (new), snaptrade-python-sdk (new, Task 10) · dbt (local = dbt-fusion at `~/.local/bin/dbt`, CI = dbt-core 1.11) · BigQuery (`anchor-495115`) · Streamlit + Altair · Dagster (`orchestration/`).

## Global Constraints

- **Run dbt from inside `transformation/`** — never `--project-dir` (fusion mishandles seed paths). Local dbt binary: `~/.local/bin/dbt`.
- **Python = `./venv/bin/python`** from the repo root (`/Users/timurakhtemov/Desktop/Programming/Personal/Anchor`).
- **Never commit** anything under `data/private/`, any `.env` value, or any real position/dollar data. The committed sample portfolio is fake.
- **Verify against live data before baking values in** (project rule). Explicit checkpoints: Fidelity CSV headers (Task 1), benchmark ETF names (Task 3), SnapTrade payload shape (Task 10).
- **`holdings_source` var defaults to `demo` everywhere.** Only `make build-private` passes `real`.
- **Commit style:** conventional commits (`feat:`, `fix:`, `docs:`, `chore:`), **no Co-Authored-By trailer** (user preference).
- Existing contract: `holdings_benchmarks` has an enforced dbt contract — its yml must change in the same commit as its SQL.
- CI (`dbt build --target ci`, dbt-core) must stay green; it builds the demo world by definition.

---

### Task 1: Fidelity CSV parser (pure functions) + committed sample portfolio + pytest infra

**Files:**
- Create: `ingestion/holdings_csv.py`
- Create: `tests/conftest.py`, `tests/ingestion/test_holdings_csv.py`
- Create: `data/sample_portfolio.csv`
- Modify: `ingestion/requirements.txt` (add `pytest`)

**Interfaces:**
- Consumes: nothing (pure functions over CSV text).
- Produces: `to_number(raw: str | None) -> float | None`, `clean_symbol(raw: str | None) -> str | None`, `parse_fidelity_positions(text: str) -> list[dict]` where each dict has keys `account_number, account_name, ticker, description, quantity, price, market_value, cost_basis_total` (ticker `None` for cash-like rows). Task 2's loader consumes this list verbatim.

- [ ] **Step 1: Verification checkpoint — confirm the real export format.** Ask Timur for the header row (and one redacted data row) of an actual Fidelity positions export. Expected headers (adjust `parse_fidelity_positions` and the sample CSV below if the real export differs):

```
Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type
```

- [ ] **Step 2: Create the sample portfolio** at `data/sample_portfolio.csv` — Fidelity format, exercises every routing branch (6 stocks, VOO, SPY-root, BND, FXAIX, FXNAX, SPAXX cash, pending-activity row, two accounts, trailing disclaimer junk):

```csv
Account Number,Account Name,Symbol,Description,Quantity,Last Price,Last Price Change,Current Value,Today's Gain/Loss Dollar,Today's Gain/Loss Percent,Total Gain/Loss Dollar,Total Gain/Loss Percent,Percent Of Account,Cost Basis Total,Average Cost Basis,Type
Z12345678,DEMO BROKERAGE,AAPL,APPLE INC,20,$210.00,+$1.50,"$4,200.00",+$30.00,+0.72%,"+$1,200.00",+40.00%,14.2%,"$3,000.00",$150.00,Cash
Z12345678,DEMO BROKERAGE,JPM,JPMORGAN CHASE & CO,15,$290.00,-$2.10,"$4,350.00",-$31.50,-0.72%,"+$1,950.00",+81.25%,14.7%,"$2,400.00",$160.00,Cash
Z12345678,DEMO BROKERAGE,HIMS,HIMS & HERS HEALTH INC,40,$45.00,+$0.85,"$1,800.00",+$34.00,+1.92%,+$500.00,+38.46%,6.1%,"$1,300.00",$32.50,Cash
Z12345678,DEMO BROKERAGE,TALO,TALOS ENERGY INC,150,$16.00,-$0.20,"$2,400.00",-$30.00,-1.23%,+$400.00,+20.00%,8.1%,"$2,000.00",$13.33,Cash
Z12345678,DEMO BROKERAGE,CVLG,COVENANT LOGISTICS GROUP INC,30,$27.00,+$0.15,$810.00,+$4.50,+0.56%,+$10.00,+1.25%,2.7%,$800.00,$26.67,Cash
Z12345678,DEMO BROKERAGE,IMMR,IMMERSION CORP,100,$8.50,-$0.05,$850.00,-$5.00,-0.58%,-$50.00,-5.56%,2.9%,$900.00,$9.00,Cash
Z12345678,DEMO BROKERAGE,VOO,VANGUARD S&P 500 ETF,12,$560.00,+$3.20,"$6,720.00",+$38.40,+0.57%,"+$1,520.00",+29.23%,22.7%,"$5,200.00",$433.33,Cash
Z12345678,DEMO BROKERAGE,SPY,SPDR S&P 500 ETF TRUST,5,$610.00,+$3.50,"$3,050.00",+$17.50,+0.58%,+$450.00,+17.31%,10.3%,"$2,600.00",$520.00,Cash
Z12345678,DEMO BROKERAGE,BND,VANGUARD TOTAL BOND MARKET ETF,40,$73.00,+$0.10,"$2,920.00",+$4.00,+0.14%,-$80.00,-2.67%,9.9%,"$3,000.00",$75.00,Cash
Z12345678,DEMO BROKERAGE,SPAXX**,FIDELITY GOVERNMENT MONEY MARKET,2500.00,$1.00,,"$2,500.00",,,,,8.4%,,,Cash
Z12345678,DEMO BROKERAGE,Pending Activity,,,,,$150.25,,,,,,,,
Z87654321,DEMO IRA,FXAIX,FIDELITY 500 INDEX FUND,30,$195.00,+$1.10,"$5,850.00",+$33.00,+0.57%,+$450.00,+8.33%,86.7%,"$5,400.00",$180.00,Cash
Z87654321,DEMO IRA,FXNAX,FIDELITY US BOND INDEX FUND,60,$10.50,+$0.02,$630.00,+$1.20,+0.19%,+$10.00,+1.61%,9.3%,$620.00,$10.33,Cash
Z87654321,DEMO IRA,SPAXX**,FIDELITY GOVERNMENT MONEY MARKET,800.00,$1.00,,$800.00,,,,,4.0%,,,Cash

"The data and information in this spreadsheet is provided to you solely for your use and is not for distribution. This is sample data for the Anchor demo portfolio."
"Date downloaded 07/01/2026 6:30 PM ET"
```

- [ ] **Step 3: Write the failing tests** at `tests/ingestion/test_holdings_csv.py` (and `tests/conftest.py` to put the repo root on `sys.path`):

```python
# tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

```python
# tests/ingestion/test_holdings_csv.py
from pathlib import Path

from ingestion.holdings_csv import clean_symbol, parse_fidelity_positions, to_number

SAMPLE = Path(__file__).parent.parent.parent / "data" / "sample_portfolio.csv"


def test_to_number_strips_currency_formatting():
    assert to_number("$4,200.00") == 4200.0
    assert to_number("+$1,200.00") == 1200.0
    assert to_number("(123.45)") == -123.45
    assert to_number("--") is None
    assert to_number("") is None
    assert to_number(None) is None


def test_clean_symbol_strips_moneymarket_stars():
    assert clean_symbol("SPAXX**") == "SPAXX"
    assert clean_symbol(" AAPL ") == "AAPL"


def test_clean_symbol_rejects_non_symbols():
    assert clean_symbol("Pending Activity") is None
    assert clean_symbol("") is None
    assert clean_symbol(None) is None


def test_parse_sample_portfolio():
    rows = parse_fidelity_positions(SAMPLE.read_text())
    # 14 position rows survive; 2 disclaimer lines are dropped.
    assert len(rows) == 14

    aapl = next(r for r in rows if r["ticker"] == "AAPL")
    assert aapl["account_number"] == "Z12345678"
    assert aapl["quantity"] == 20.0
    assert aapl["market_value"] == 4200.0
    assert aapl["cost_basis_total"] == 3000.0

    # SPAXX stars stripped; appears in both accounts.
    assert sum(1 for r in rows if r["ticker"] == "SPAXX") == 2

    pending = next(r for r in rows if r["ticker"] is None)
    assert pending["description"] == "Pending Activity"
    assert pending["market_value"] == 150.25
```

- [ ] **Step 4: Run tests to verify they fail.** Run: `./venv/bin/pip install pytest && ./venv/bin/python -m pytest tests/ -v`. Expected: FAIL — `ModuleNotFoundError: No module named 'ingestion.holdings_csv'`.

- [ ] **Step 5: Implement the parser** at `ingestion/holdings_csv.py`:

```python
"""Pure parsing functions for Fidelity positions CSV exports.

No BigQuery, no I/O beyond the text passed in — the loader (ingest_holdings.py)
owns landing the rows. Kept separate so the format quirks are unit-testable.

Fidelity quirks handled here and only here:
- money-market symbols carry a trailing '**' (SPAXX**)
- 'Pending Activity' rows have no symbol, only a Current Value (cash in motion)
- money columns carry $ , + ( ) formatting; '--' and blank mean "no value"
- the file ends with quoted disclaimer lines and a 'Date downloaded' line,
  which surface as rows with only the first column populated
"""
from __future__ import annotations

import csv
import io

# Columns we consume from the export (the rest are display-only derivatives).
_REQUIRED_HEADERS = {"Account Number", "Symbol", "Current Value"}


def to_number(raw: str | None) -> float | None:
    """'$4,200.00' -> 4200.0, '(123.45)' -> -123.45, '--'/''/None -> None."""
    if raw is None:
        return None
    s = raw.strip().replace("$", "").replace(",", "").replace("%", "").lstrip("+")
    if s in ("", "--", "n/a", "N/A"):
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def clean_symbol(raw: str | None) -> str | None:
    """Normalize a Fidelity Symbol cell to a ticker; None for cash-like rows."""
    if raw is None:
        return None
    s = raw.strip().rstrip("*")
    if not s or " " in s:  # 'Pending Activity' and other non-symbols
        return None
    return s


def parse_fidelity_positions(text: str) -> list[dict]:
    """Parse a Fidelity positions export into normalized position dicts."""
    reader = csv.DictReader(io.StringIO(text))
    missing = _REQUIRED_HEADERS - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"not a Fidelity positions export; missing headers: {sorted(missing)}")

    rows: list[dict] = []
    for row in reader:
        symbol = (row.get("Symbol") or "").strip()
        value = (row.get("Current Value") or "").strip()
        if not symbol and not value:  # blank / disclaimer / date-downloaded lines
            continue
        account = (row.get("Account Number") or "").strip()
        if not account:
            continue
        ticker = clean_symbol(symbol)
        rows.append(
            {
                "account_number": account,
                "account_name": (row.get("Account Name") or "").strip(),
                "ticker": ticker,
                "description": (row.get("Description") or "").strip() or (symbol if ticker is None else ""),
                "quantity": to_number(row.get("Quantity")),
                "price": to_number(row.get("Last Price")),
                "market_value": to_number(row.get("Current Value")),
                "cost_basis_total": to_number(row.get("Cost Basis Total")),
            }
        )
    return rows
```

- [ ] **Step 6: Run tests to verify they pass.** Run: `./venv/bin/python -m pytest tests/ -v`. Expected: 4 passed.

- [ ] **Step 7: Add `pytest` to `ingestion/requirements.txt`** (append one line: `pytest`).

- [ ] **Step 8: Commit.**

```bash
git add ingestion/holdings_csv.py tests/ data/sample_portfolio.csv ingestion/requirements.txt
git commit -m "feat(ingestion): Fidelity positions CSV parser + committed sample portfolio"
```

---

### Task 2: Holdings loader CLI → `raw_holdings` bronze

**Files:**
- Create: `ingestion/ingest_holdings.py`

**Interfaces:**
- Consumes: `parse_fidelity_positions` from Task 1.
- Produces: `ingest_holdings_csv(bq_client, csv_path: str, portfolio: str, as_of: datetime.date | None = None) -> int` (row count), `ingest_fund_classifications(bq_client, csv_path: str) -> int`, constant `SAMPLE_CSV_PATH`. Tables: `raw_holdings.holdings_demo`, `raw_holdings.holdings_real` (append), `raw_holdings.fund_classifications_real` (truncate). Task 8's Dagster asset and Task 9 consume these.

- [ ] **Step 1: Implement the loader** at `ingestion/ingest_holdings.py`:

```python
"""Load portfolio holdings into the raw_holdings BigQuery dataset.

One loader, multiple transports, one schema:
  --from-csv <path>      parse a Fidelity positions export (or the committed
                         demo sample, which is in the same format)
  --from-snaptrade       pull live positions via SnapTrade (added later)

--portfolio demo|real routes to holdings_demo / holdings_real. Loads APPEND
with an as_of batch date so position history accumulates from day one;
staging reads the latest as_of. --fund-classifications lands the private
fund-classification CSV (real funds only) as a truncate-and-replace table.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from google.cloud import bigquery

from ingestion.holdings_csv import parse_fidelity_positions

logger = logging.getLogger(__name__)

PROJECT_ID = "anchor-495115"
DATASET_ID = "raw_holdings"
KEYFILE_PATH = "/Users/timurakhtemov/.dbt/anchor-bigquery-key.json"
SAMPLE_CSV_PATH = str(Path(__file__).parent.parent / "data" / "sample_portfolio.csv")

_HOLDINGS_SCHEMA = [
    bigquery.SchemaField("account_number", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("account_name", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("ticker", "STRING", mode="NULLABLE"),  # null = cash-like row
    bigquery.SchemaField("description", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("quantity", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("price", "FLOAT", mode="NULLABLE"),          # audit only
    bigquery.SchemaField("market_value", "FLOAT", mode="NULLABLE"),   # audit only; gold recomputes
    bigquery.SchemaField("cost_basis_total", "FLOAT", mode="NULLABLE"),
    bigquery.SchemaField("as_of", "DATE", mode="REQUIRED"),
    bigquery.SchemaField("source", "STRING", mode="REQUIRED"),  # sample | csv | snaptrade
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
]

_CLASSIFICATIONS_SCHEMA = [
    bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("asset_class", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("sub_style", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED"),
]


def build_bigquery_client():
    """Keyfile locally, ADC elsewhere — same pattern as the other ingesters."""
    if os.path.exists(KEYFILE_PATH):
        return bigquery.Client.from_service_account_json(KEYFILE_PATH, project=PROJECT_ID)
    return bigquery.Client(project=PROJECT_ID)


def _ensure_dataset(bq_client) -> None:
    dataset_ref = bq_client.dataset(DATASET_ID)
    try:
        bq_client.get_dataset(dataset_ref)
    except Exception:
        ds = bigquery.Dataset(dataset_ref)
        ds.location = "US"
        bq_client.create_dataset(ds, timeout=30)
        logger.info(f"Created dataset {PROJECT_ID}.{DATASET_ID}")


def ingest_holdings_csv(bq_client, csv_path: str, portfolio: str, as_of: date | None = None) -> int:
    """Parse a Fidelity-format CSV and APPEND it to holdings_<portfolio>."""
    if portfolio not in ("demo", "real"):
        raise ValueError(f"portfolio must be demo|real, got {portfolio!r}")
    rows = parse_fidelity_positions(Path(csv_path).read_text())
    if not rows:
        raise RuntimeError(f"no positions parsed from {csv_path}")

    df = pd.DataFrame(rows)
    df["as_of"] = as_of or date.today()
    df["source"] = "sample" if portfolio == "demo" else "csv"
    df["ingested_at"] = datetime.now(UTC)

    _ensure_dataset(bq_client)
    table = f"holdings_{portfolio}"
    job_config = bigquery.LoadJobConfig(
        schema=_HOLDINGS_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
    )
    bq_client.load_table_from_dataframe(
        df, bq_client.dataset(DATASET_ID).table(table), job_config=job_config
    ).result()
    logger.info(f"Appended {len(df)} rows to {PROJECT_ID}.{DATASET_ID}.{table}")
    return len(df)


def ingest_fund_classifications(bq_client, csv_path: str) -> int:
    """Land the PRIVATE fund-classification CSV (real funds) — truncate & replace."""
    df = pd.read_csv(csv_path)
    expected = {"ticker", "asset_class"}
    if not expected.issubset(df.columns):
        raise ValueError(f"{csv_path} must have columns ticker,asset_class[,sub_style]")
    if "sub_style" not in df.columns:
        df["sub_style"] = None
    df = df[["ticker", "asset_class", "sub_style"]].copy()
    df["ingested_at"] = datetime.now(UTC)

    _ensure_dataset(bq_client)
    job_config = bigquery.LoadJobConfig(
        schema=_CLASSIFICATIONS_SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    bq_client.load_table_from_dataframe(
        df, bq_client.dataset(DATASET_ID).table("fund_classifications_real"), job_config=job_config
    ).result()
    logger.info(f"Loaded {len(df)} fund classifications (private)")
    return len(df)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=[logging.StreamHandler(sys.stdout)])
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from-csv", metavar="PATH", help="Fidelity positions export to load")
    ap.add_argument("--portfolio", choices=["demo", "real"], required=True)
    ap.add_argument("--as-of", type=date.fromisoformat, default=None,
                    help="batch date (default: today)")
    ap.add_argument("--fund-classifications", metavar="PATH", default=None,
                    help="also load this private fund-classification CSV")
    args = ap.parse_args()

    client = build_bigquery_client()
    if args.from_csv:
        ingest_holdings_csv(client, args.from_csv, args.portfolio, args.as_of)
    else:
        ap.error("--from-csv is required (SnapTrade mode arrives in a later task)")
    if args.fund_classifications:
        ingest_fund_classifications(client, args.fund_classifications)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Load the demo portfolio.** Run: `./venv/bin/python ingestion/ingest_holdings.py --from-csv data/sample_portfolio.csv --portfolio demo`. Expected: log line `Appended 14 rows to anchor-495115.raw_holdings.holdings_demo`.

- [ ] **Step 3: Spot-check the landed rows.** Run:

```bash
./venv/bin/python -c "
from ingestion.ingest_holdings import build_bigquery_client
c = build_bigquery_client()
for r in c.query('select ticker, sum(quantity) q from \`anchor-495115.raw_holdings.holdings_demo\` group by 1 order by 1').result():
    print(r.ticker, r.q)
"
```

Expected: 13 rows — 12 tickers (AAPL…VOO, SPAXX summed across accounts) plus a `None` row (pending activity).

- [ ] **Step 4: Commit.**

```bash
git add ingestion/ingest_holdings.py
git commit -m "feat(ingestion): holdings loader CLI -> raw_holdings bronze (append, demo/real)"
```

---

### Task 3: Benchmark seed expansion + yfinance `quote_type` + derived ticker universe

**Files:**
- Modify: `transformation/seeds/benchmark_etfs.csv`
- Modify: `ingestion/ingest_yfinance.py`

**Interfaces:**
- Consumes: `raw_holdings.holdings_demo` / `holdings_real` (Task 2); `transformation/seeds/benchmark_etfs.csv` as the single source of truth for the benchmark ETF set.
- Produces: `raw_yfinance_tickers` gains a `quote_type` column; prices/metadata exist for all held tickers + all seed ETFs. dbt staging (Task 4) consumes `quote_type`.

- [ ] **Step 1: Verification checkpoint — probe the new benchmark ETF names live** (never bake names from memory):

```bash
./venv/bin/python -c "
import yfinance as yf
for t in ['AGG','SHY','IEF','TLT','SPY']:
    print(t, '|', yf.Ticker(t).info.get('longName'))
"
```

- [ ] **Step 2: Append the new axis rows to `transformation/seeds/benchmark_etfs.csv`** (use the exact `longName` strings from Step 1 as `etf_name`; expected shape):

```csv
market,equity,SPY,SPDR S&P 500 ETF Trust
bond_market,fixed_income,AGG,iShares Core U.S. Aggregate Bond ETF
duration,short,SHY,iShares 1-3 Year Treasury Bond ETF
duration,intermediate,IEF,iShares 7-10 Year Treasury Bond ETF
duration,long,TLT,iShares 20+ Year Treasury Bond ETF
```

- [ ] **Step 3: Rework `ingestion/ingest_yfinance.py`.** Three changes:

(a) Replace the static ticker constants (`SECTOR_ETFS`, `CAP_STYLE_ETFS`, `HOLDINGS`, `TICKERS`, lines 20–29) with derivation helpers:

```python
import csv
from pathlib import Path

from google.api_core.exceptions import NotFound

_SEED_PATH = Path(__file__).parent.parent / "transformation" / "seeds" / "benchmark_etfs.csv"


def _seed_benchmark_etf_tickers() -> set[str]:
    """The benchmark ETF universe — read from the dbt seed so Python and dbt
    can never disagree about which ETFs the models expect prices for."""
    with open(_SEED_PATH) as f:
        return {row["etf_ticker"] for row in csv.DictReader(f)}


def _held_tickers(bq_client) -> set[str]:
    """Every ticker held in either portfolio. Prices are public market data,
    so one shared price table serves both worlds; privacy scoping happens in
    the marts. Missing tables (fresh env, no real portfolio) are skipped."""
    held: set[str] = set()
    for table in ("holdings_demo", "holdings_real"):
        try:
            q = f"select distinct ticker from `{PROJECT_ID}.raw_holdings.{table}` where ticker is not null"
            held |= {row.ticker for row in bq_client.query(q).result()}
        except NotFound:
            logger.info(f"raw_holdings.{table} not found; skipping")
    return held


def resolve_universe(bq_client) -> list[str]:
    return sorted(_seed_benchmark_etf_tickers() | _held_tickers(bq_client))
```

(b) In `ingest_yfinance(bq_client)`, replace the `for ticker in TICKERS:` loop header with:

```python
    tickers = resolve_universe(bq_client)
    logger.info(f"Resolved ticker universe: {len(tickers)} tickers: {tickers}")
    for ticker in tickers:
```

(c) Capture `quoteType`: in the `metadata_list.append({...})` dict add, after `'currency'`:

```python
            'quote_type': info.get('quoteType'),  # EQUITY / ETF / MUTUALFUND / MONEYMARKET — the classification spine
```

and in `schema_meta` add, after the `currency` field:

```python
        bigquery.SchemaField("quote_type", "STRING", mode="NULLABLE"),
```

- [ ] **Step 4: Run the ingestion.** Run: `./venv/bin/python ingestion/ingest_yfinance.py` (several minutes; ~30 tickers × 5y). Expected: `Resolved ticker universe: 29 tickers` (18 seed ETFs: 11 sector + SPY/MDY/IWM + AGG/SHY/IEF/TLT, plus 11 held non-benchmark tickers; held SPY overlaps the seed), then successful loads of both tables. Note: SPAXX may return zero price bars — that's fine (metadata still lands; cash is valued from source, not prices).

- [ ] **Step 5: Spot-check `quote_type`.** Run:

```bash
./venv/bin/python -c "
from ingestion.ingest_holdings import build_bigquery_client
c = build_bigquery_client()
for r in c.query('select quote_type, count(*) n from \`anchor-495115.raw_yfinance.raw_yfinance_tickers\` group by 1 order by 2 desc').result():
    print(r.quote_type, r.n)
"
```

Expected: `ETF` ≈ 20, `EQUITY` = 6, `MUTUALFUND` = 2, `MONEYMARKET` = 1.

- [ ] **Step 6: Commit.**

```bash
git add transformation/seeds/benchmark_etfs.csv ingestion/ingest_yfinance.py
git commit -m "feat(ingestion): derive yfinance universe from holdings + seed; capture quote_type; add market/bond/duration benchmark ETFs"
```

---

### Task 4: Holdings staging + `quote_type` through tickers staging and SCD2 snapshot

**Files:**
- Create: `transformation/models/staging/holdings/_src_holdings.yml`
- Create: `transformation/models/staging/holdings/stg_holdings__positions.sql`
- Create: `transformation/models/staging/holdings/stg_holdings__fund_classifications.sql`
- Create: `transformation/models/staging/holdings/_stg_holdings.yml`
- Create: `transformation/seeds/fund_classifications.csv`
- Modify: `transformation/models/staging/yfinance/stg_yfinance__tickers.sql`
- Modify: `transformation/models/staging/yfinance/_stg_yfinance.yml`
- Modify: `transformation/snapshots/snap_yfinance_tickers.sql`

**Interfaces:**
- Consumes: `raw_holdings.*` (Task 2), `quote_type` in `raw_yfinance_tickers` (Task 3), var `holdings_source` (`demo` default).
- Produces: `stg_holdings__positions` (grain: account_number × ticker; columns `account_number, account_name, ticker, description, quantity, source_price, source_market_value, cost_basis_total, as_of, source, raw_ingested_at`; null bronze ticker coalesced to `'CASH'`); `stg_holdings__fund_classifications` (`ticker, asset_class, sub_style`); `stg_yfinance__tickers` gains `quote_type`. Task 5's intermediate models consume all three.

- [ ] **Step 1: Declare the bronze source** at `transformation/models/staging/holdings/_src_holdings.yml` (no freshness config — holdings load on demand, not on a cadence):

```yaml
version: 2

sources:
  - name: holdings
    database: anchor-495115
    schema: raw_holdings
    description: >
      Portfolio holdings bronze. holdings_demo is the committed sample portfolio
      (public path); holdings_real is the private portfolio (never public).
      Loads append with an as_of batch date; staging reads the latest batch.
    tables:
      - name: holdings_demo
      - name: holdings_real
      - name: fund_classifications_real
        description: >
          Private fund-classification table for real-portfolio funds, landed by
          the loader from a gitignored CSV. The committed fund_classifications
          seed covers demo funds only — no fact about the real portfolio (not
          even fund tickers) lives in the repo.
```

- [ ] **Step 2: Create `stg_holdings__positions.sql`** — the `holdings_source` var picks the world at compile time, so the unselected world's table is never referenced:

```sql
-- Latest position batch for the selected portfolio (var holdings_source:
-- demo | real, default demo). Bronze appends every load with an as_of batch
-- date (position history banks for a future time-series milestone); staging
-- serves only the newest batch, deduped to the latest ingestion within it.

{% set holdings_table = 'holdings_real' if var('holdings_source', 'demo') == 'real' else 'holdings_demo' %}

with source as (

    select * from {{ source('holdings', holdings_table) }}

),

latest_batch as (

    select * from source
    where as_of = (select max(as_of) from source)

),

deduped as (

    select
        *,
        row_number() over (
            partition by account_number, coalesce(ticker, 'CASH')
            order by ingested_at desc
        ) as rn
    from latest_batch

)

select
    account_number,
    account_name,
    -- Cash-in-motion rows (e.g. Fidelity "Pending Activity") carry no symbol;
    -- give them a stable pseudo-ticker so every grain key is non-null.
    coalesce(ticker, 'CASH') as ticker,
    description,
    quantity,
    price        as source_price,
    market_value as source_market_value,
    cost_basis_total,
    as_of,
    source,
    ingested_at  as raw_ingested_at
from deduped
where rn = 1
```

- [ ] **Step 3: Create the committed demo classification seed** at `transformation/seeds/fund_classifications.csv` (demo funds only — decision 8):

```csv
ticker,asset_class,sub_style
VOO,equity,
SPY,equity,
BND,fixed_income,intermediate
FXAIX,equity,
FXNAX,fixed_income,intermediate
```

- [ ] **Step 4: Create `stg_holdings__fund_classifications.sql`** — committed seed ∪ (real world only) the private table:

```sql
-- Fund-classification mapping: which asset class a held fund (quote_type
-- ETF/MUTUALFUND) belongs to, plus its per-class sub_style (duration bucket
-- for bonds). Maintained by hand because no free source can classify fund
-- CONTENTS (verified: yfinance category is null for mutual funds; SnapTrade
-- security_type is just 'oef'; see docs/make_it_real_design.md appendix).
-- Demo funds = the committed seed; real funds = a private bronze table so no
-- fact about the real portfolio lives in the repo (decision 8).

with committed as (

    select
        ticker,
        asset_class,
        nullif(trim(coalesce(sub_style, '')), '') as sub_style
    from {{ ref('fund_classifications') }}

)

{% if var('holdings_source', 'demo') == 'real' %}

, private as (

    select
        ticker,
        asset_class,
        nullif(trim(coalesce(sub_style, '')), '') as sub_style
    from {{ source('holdings', 'fund_classifications_real') }}

)

select * from committed
union distinct
select * from private

{% else %}

select * from committed

{% endif %}
```

- [ ] **Step 5: Add `quote_type` to tickers staging.** In `transformation/models/staging/yfinance/stg_yfinance__tickers.sql`, add `quote_type,` after the `currency,` line in the `renamed` CTE. In `transformation/snapshots/snap_yfinance_tickers.sql`, add `'quote_type'` to `check_cols` (after `'currency'`) and `quote_type,` to the select list (after `currency,`) — an additive snapshot schema change; existing history is preserved.

- [ ] **Step 6: Write the staging schema tests** at `transformation/models/staging/holdings/_stg_holdings.yml`:

```yaml
version: 2

models:
  - name: stg_holdings__positions
    description: >
      Latest position batch for the selected portfolio (holdings_source var).
      Grain: one row per (account_number, ticker); ticker 'CASH' is the
      pseudo-ticker for cash-in-motion rows with no symbol.
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments:
            combination_of_columns:
              - account_number
              - ticker
    columns:
      - name: account_number
        data_tests: [not_null]
      - name: ticker
        description: Held symbol, or the CASH pseudo-ticker.
        data_tests: [not_null]
      - name: quantity
        description: Shares / units / dollars (money market). Null for pending-activity rows.
      - name: source_market_value
        description: Value as stated by the source at as_of — audit column; gold recomputes.
      - name: as_of
        description: Batch date of the import.
        data_tests: [not_null]
      - name: source
        data_tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['sample', 'csv', 'snaptrade']

  - name: stg_holdings__fund_classifications
    description: >
      Maintained fund-classification mapping (committed demo seed ∪ private
      real table). Grain: one row per ticker.
    columns:
      - name: ticker
        data_tests: [unique, not_null]
      - name: asset_class
        data_tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['equity', 'fixed_income', 'commodity', 'cash', 'alt']
      - name: sub_style
        description: "Per-asset-class style axis value (bonds: duration bucket). Null = skip that axis."
        data_tests:
          - accepted_values:
              arguments:
                values: ['short', 'intermediate', 'long']
```

- [ ] **Step 7: Document `quote_type` in `_stg_yfinance.yml`.** Under `stg_yfinance__tickers` columns, after `currency`, add:

```yaml
      - name: quote_type
        description: >
          yfinance quoteType — EQUITY / ETF / MUTUALFUND / MONEYMARKET. The
          asset-classification spine; reliable for instrument FORM, silent on
          fund contents (hence the fund_classifications mapping).
        data_tests:
          - accepted_values:
              arguments:
                values: ['EQUITY', 'ETF', 'MUTUALFUND', 'MONEYMARKET', 'INDEX', 'CRYPTOCURRENCY']
```

- [ ] **Step 8: Build and test staging.** Run: `cd transformation && ~/.local/bin/dbt build --select staging fund_classifications snap_yfinance_tickers --indirect-selection cautious`. Expected: all green (staging models + seed + snapshot + new tests) into the dev sandbox. (`cautious` is required: eager indirect selection pulls in the pre-existing `assert_holdings_benchmarked_on_both_axes` test, which is known-red between Task 3's universe expansion and Task 6's mart+test rework.)

- [ ] **Step 9: Commit.**

```bash
git add transformation/models/staging/ transformation/seeds/fund_classifications.csv transformation/snapshots/snap_yfinance_tickers.sql
git commit -m "feat(dbt): holdings staging (world-select via var), fund classifications, quote_type through staging + snapshot"
```

---

### Task 5: Intermediate models — classification + benchmark routing + coverage guardrail

**Files:**
- Create: `transformation/models/intermediate/int_holdings_classified.sql`
- Create: `transformation/models/intermediate/int_benchmark_routing.sql`
- Create: `transformation/tests/assert_held_funds_classified.sql`
- Modify: `transformation/models/intermediate/_int.yml`

**Interfaces:**
- Consumes: `stg_holdings__positions`, `stg_holdings__fund_classifications`, `stg_yfinance__tickers` (+`quote_type`), `int_ticker_returns`, `benchmark_etfs` seed.
- Produces: `int_holdings_classified` (grain: ticker; columns `ticker, display_name, sector, market_cap, quote_type, asset_class, sub_style, cap_tier, quantity, source_market_value, cost_basis_total, as_of_date, latest_close, market_value, weight_pct, unrealized_gain_pct`); `int_benchmark_routing` (grain: holding_ticker × benchmark_type; columns `holding_ticker, benchmark_type, benchmark_etf, benchmark_name, is_self`). Task 6's marts consume both.

- [ ] **Step 1: Create `int_holdings_classified.sql`:**

```sql
-- One classified, valued row per held ticker (aggregated across accounts).
-- Classification: quote_type is the spine (EQUITY -> equity, MONEYMARKET ->
-- cash); funds (ETF/MUTUALFUND) come from the maintained mapping because no
-- metadata source can classify fund contents. cap_tier is computed ONLY for
-- individual equities — funds have null market_cap and must never inherit a
-- cap tier (the old `else 'Small'` bug).
-- Valuation: market_value = quantity x latest close so weights stay fresh
-- between imports; cash keeps its source value (fixed $1 NAV, no price series).

with positions as (

    select
        ticker,
        max(description)          as description,
        sum(quantity)             as quantity,
        sum(source_market_value)  as source_market_value,
        sum(cost_basis_total)     as cost_basis_total,
        max(as_of)                as as_of_date
    from {{ ref('stg_holdings__positions') }}
    group by ticker

),

meta as (

    select ticker, company_name, sector, market_cap, quote_type
    from {{ ref('stg_yfinance__tickers') }}

),

fund_classes as (

    select ticker, asset_class, sub_style
    from {{ ref('stg_holdings__fund_classifications') }}

),

latest_prices as (

    select ticker, latest_close
    from {{ ref('int_ticker_returns') }}

),

classified as (

    select
        p.ticker,
        coalesce(m.company_name, p.description) as display_name,
        m.sector,
        m.market_cap,
        m.quote_type,
        case
            when p.ticker = 'CASH'                       then 'cash'
            when m.quote_type = 'MONEYMARKET'            then 'cash'
            when m.quote_type = 'EQUITY'                 then 'equity'
            when m.quote_type in ('ETF', 'MUTUALFUND')   then f.asset_class
        end as asset_class,
        f.sub_style,
        case
            when m.quote_type = 'EQUITY' then
                case
                    when m.market_cap >= 10e9 then 'Large'
                    when m.market_cap >=  2e9 then 'Mid'
                    else 'Small'
                end
        end as cap_tier,
        p.quantity,
        p.source_market_value,
        p.cost_basis_total,
        p.as_of_date,
        r.latest_close
    from positions p
    left join meta          m using (ticker)
    left join fund_classes  f using (ticker)
    left join latest_prices r using (ticker)

),

valued as (

    select
        *,
        case
            when asset_class = 'cash' then coalesce(source_market_value, quantity)
            else round(quantity * latest_close, 2)
        end as market_value
    from classified

)

select
    *,
    round(market_value / sum(market_value) over () * 100, 2) as weight_pct,
    case
        when asset_class != 'cash' and cost_basis_total > 0
        then round((market_value / cost_basis_total - 1) * 100, 2)
    end as unrealized_gain_pct
from valued
```

- [ ] **Step 2: Create `int_benchmark_routing.sql`:**

```sql
-- Resolve each non-cash holding to its benchmark set, per asset class.
-- Axes (lookup_key = the holding attribute the axis routes on):
--   equity stock  -> sector (sector name) + cap_style (cap tier)
--   equity fund   -> market ('equity')
--   fixed income  -> bond_market ('fixed_income') + duration (sub_style, if set)
-- Self-pairings (held SPY routed to SPY) are FLAGGED here, filtered by the
-- mart, and surfaced as is_root in portfolio_composition. Cash never routes.

with holdings as (

    select ticker, sector, cap_tier, quote_type, asset_class, sub_style
    from {{ ref('int_holdings_classified') }}
    where asset_class is not null
      and asset_class != 'cash'

),

benchmarks as (

    select benchmark_type, lookup_key, etf_ticker, etf_name
    from {{ ref('benchmark_etfs') }}

),

routed as (

    -- equity stocks: sector axis
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'sector'
       and h.quote_type = 'EQUITY'
       and b.lookup_key = h.sector

    union all

    -- equity stocks: cap-style axis
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'cap_style'
       and h.quote_type = 'EQUITY'
       and b.lookup_key = h.cap_tier

    union all

    -- held equity funds: market axis ("did it beat the index?")
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'market'
       and h.asset_class = 'equity'
       and h.quote_type in ('ETF', 'MUTUALFUND')
       and b.lookup_key = 'equity'

    union all

    -- fixed income: broad bond-market axis
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'bond_market'
       and h.asset_class = 'fixed_income'
       and b.lookup_key = 'fixed_income'

    union all

    -- fixed income: duration axis (only when the mapping assigns a bucket)
    select h.ticker, b.benchmark_type, b.etf_ticker, b.etf_name
    from holdings h
    join benchmarks b
        on b.benchmark_type = 'duration'
       and h.asset_class = 'fixed_income'
       and b.lookup_key = h.sub_style

)

select
    ticker              as holding_ticker,
    benchmark_type,
    etf_ticker          as benchmark_etf,
    etf_name            as benchmark_name,
    ticker = etf_ticker as is_self
from routed
```

- [ ] **Step 3: Create the fund-coverage guardrail** at `transformation/tests/assert_held_funds_classified.sql`:

```sql
-- Guardrail: every held fund (quote_type ETF / MUTUALFUND) must have a row in
-- the fund-classification mapping. Without one its asset_class is null and it
-- would silently receive no benchmark. Fail the build loudly instead — the fix
-- is one seed row (demo) or one line in data/private/fund_classifications_real.csv.

select
    p.ticker,
    t.quote_type
from (select distinct ticker from {{ ref('stg_holdings__positions') }}) p
join {{ ref('stg_yfinance__tickers') }} t using (ticker)
where t.quote_type in ('ETF', 'MUTUALFUND')
  and p.ticker not in (select ticker from {{ ref('stg_holdings__fund_classifications') }})
```

- [ ] **Step 4: Add schema tests to `_int.yml`** (append under `models:`):

```yaml
  - name: int_holdings_classified
    description: >
      One classified, valued row per held ticker: asset_class (quote_type spine
      + fund mapping), cap_tier (equities only), live market value, portfolio
      weight, unrealized gain. Grain: one row per ticker.
    columns:
      - name: ticker
        data_tests: [unique, not_null]
      - name: asset_class
        description: equity / fixed_income / cash (commodity, alt reserved). Null = unclassified fund (guardrail fails the build).
        data_tests:
          - accepted_values:
              arguments:
                values: ['equity', 'fixed_income', 'commodity', 'cash', 'alt']
      - name: cap_tier
        description: Large / Mid / Small — individual equities ONLY; null for funds and cash.
        data_tests:
          - accepted_values:
              arguments:
                values: ['Large', 'Mid', 'Small']
      - name: market_value
        description: quantity x latest close (cash - source value).
        data_tests: [not_null]
      - name: weight_pct
        description: Share of total portfolio market value, in percent.
        data_tests: [not_null]

  - name: int_benchmark_routing
    description: >
      Each non-cash holding resolved to its asset-class-appropriate benchmark
      set, with self-pairings flagged (is_self) for the root rule. Grain: one
      row per (holding_ticker, benchmark_type).
    data_tests:
      - dbt_utils.unique_combination_of_columns:
          arguments:
            combination_of_columns:
              - holding_ticker
              - benchmark_type
    columns:
      - name: holding_ticker
        data_tests: [not_null]
      - name: benchmark_type
        data_tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['sector', 'cap_style', 'market', 'bond_market', 'duration']
      - name: benchmark_etf
        data_tests:
          - not_null
          - relationships:
              arguments:
                to: ref('stg_yfinance__tickers')
                field: ticker
```

- [ ] **Step 5: Build and inspect.** Run: `cd transformation && ~/.local/bin/dbt build --select +int_holdings_classified +int_benchmark_routing assert_held_funds_classified --indirect-selection cautious` (`cautious` avoids the known-red pre-Task-6 guardrail, as in Task 4). Expected: green. Then eyeball the routing:

```bash
cd transformation && ~/.local/bin/dbt show --inline "select holding_ticker, benchmark_type, benchmark_etf, is_self from {{ ref('int_benchmark_routing') }} order by 1, 2" --limit 50
```

Expected: 6 stocks × (sector + cap_style) = 12 rows; VOO/FXAIX → market/SPY; SPY → market/SPY with `is_self = true`; BND/FXNAX → bond_market/AGG + duration/IEF. No SPAXX, no CASH.

- [ ] **Step 6: Commit.**

```bash
git add transformation/models/intermediate/ transformation/tests/assert_held_funds_classified.sql
git commit -m "feat(dbt): asset-class classification + benchmark routing intermediates with fund-coverage guardrail"
```

---

### Task 6: Gold rework — `holdings_benchmarks` + new `portfolio_composition` + scoped `ticker_trend`

**Files:**
- Modify: `transformation/models/marts/holdings_benchmarks.sql` (full rewrite)
- Create: `transformation/models/marts/portfolio_composition.sql`
- Modify: `transformation/models/marts/ticker_trend.sql`
- Modify: `transformation/models/marts/_marts.yml`
- Create: `transformation/tests/assert_holdings_benchmarked_on_expected_axes.sql`
- Create: `transformation/tests/assert_portfolio_weights_sum.sql`
- Delete: `transformation/tests/assert_holdings_benchmarked_on_both_axes.sql`

**Interfaces:**
- Consumes: `int_holdings_classified`, `int_benchmark_routing`, `int_ticker_returns`, macros `ahead_behind`.
- Produces: `holdings_benchmarks` (grain unchanged: holding_ticker × benchmark_type; gains `asset_class, quote_type, weight_pct`; `sector/market_cap/cap_tier` now nullable); `portfolio_composition` (grain: ticker, columns `ticker, description, asset_class, quote_type, sub_style, quantity, latest_close, market_value, weight_pct, cost_basis, unrealized_gain_pct, is_root, as_of_date`). Task 8's app consumes both.

- [ ] **Step 1: Rewrite `holdings_benchmarks.sql`:**

```sql
-- The load-bearing holdings-tier mart. Each holding is paired with its
-- asset-class-appropriate benchmarks (routing in int_benchmark_routing) and
-- the holding% / benchmark% are computed together, so each pairing is a
-- single output row — the serve layer never joins two independent cuts.
--
-- Grain: one row per (holding_ticker, benchmark_type). Cash never appears
-- (no benchmark); root holdings (self-pairings, e.g. held SPY) are filtered
-- here and flagged in portfolio_composition instead.

with routing as (

    select * from {{ ref('int_benchmark_routing') }}
    where not is_self

),

holdings as (

    select * from {{ ref('int_holdings_classified') }}

),

returns as (

    select * from {{ ref('int_ticker_returns') }}

)

select
    r.holding_ticker,
    h.display_name as company_name,
    h.asset_class,
    h.quote_type,
    h.sector,
    h.market_cap,
    h.cap_tier,
    h.weight_pct,
    r.benchmark_type,
    r.benchmark_etf,
    r.benchmark_name,
    hr.as_of_date,
    hr.latest_close as holding_close,
    br.latest_close as benchmark_close,

    -- Daily
    hr.daily_return_pct as holding_daily_pct,
    br.daily_return_pct as benchmark_daily_pct,
    round(hr.daily_return_pct - br.daily_return_pct, 2) as relative_daily_pp,
    {{ ahead_behind('hr.daily_return_pct - br.daily_return_pct') }} as label_daily,

    -- 1 month (default horizon)
    hr.return_1m_pct as holding_1m_pct,
    br.return_1m_pct as benchmark_1m_pct,
    round(hr.return_1m_pct - br.return_1m_pct, 2) as relative_1m_pp,
    {{ ahead_behind('hr.return_1m_pct - br.return_1m_pct') }} as label_1m,

    -- YTD
    hr.return_ytd_pct as holding_ytd_pct,
    br.return_ytd_pct as benchmark_ytd_pct,
    round(hr.return_ytd_pct - br.return_ytd_pct, 2) as relative_ytd_pp,
    {{ ahead_behind('hr.return_ytd_pct - br.return_ytd_pct') }} as label_ytd,

    -- 1 year
    hr.return_1y_pct as holding_1y_pct,
    br.return_1y_pct as benchmark_1y_pct,
    round(hr.return_1y_pct - br.return_1y_pct, 2) as relative_1y_pp,
    {{ ahead_behind('hr.return_1y_pct - br.return_1y_pct') }} as label_1y

from routing r
join holdings h  on h.ticker  = r.holding_ticker
join returns  hr on hr.ticker = r.holding_ticker
join returns  br on br.ticker = r.benchmark_etf
```

- [ ] **Step 2: Create `portfolio_composition.sql`:**

```sql
-- The sizing mart: one row per held ticker INCLUDING cash and root holdings,
-- with live market value, portfolio weight, and unrealized gain. This is the
-- holding-vs-whole-portfolio relationship, computed in gold per the core
-- principle. is_root marks a holding whose only routed benchmark was itself
-- (held SPY on the market axis) — it IS the reference point, so it displays
-- with no comparison rather than a meaningless holding-vs-itself row.

with holdings as (

    select * from {{ ref('int_holdings_classified') }}

),

routing_summary as (

    select
        holding_ticker,
        countif(not is_self) as n_benchmarks,
        countif(is_self)     as n_self
    from {{ ref('int_benchmark_routing') }}
    group by holding_ticker

)

select
    h.ticker,
    h.display_name       as description,
    h.asset_class,
    h.quote_type,
    h.sub_style,
    h.quantity,
    h.latest_close,
    h.market_value,
    h.weight_pct,
    h.cost_basis_total   as cost_basis,
    h.unrealized_gain_pct,
    coalesce(r.n_self, 0) > 0 and coalesce(r.n_benchmarks, 0) = 0 as is_root,
    h.as_of_date
from holdings h
left join routing_summary r on r.holding_ticker = h.ticker
```

- [ ] **Step 3: Scope `ticker_trend` to the world's universe.** In `ticker_trend.sql`, add after the `prices` CTE (and add the `where` to the final select):

```sql
-- Scope to this world's universe: held tickers + benchmark ETFs. Demo marts
-- (and therefore the public snapshot) must never mention a real-portfolio
-- ticker; the scoping inherits the world from stg_holdings__positions.
universe as (

    select ticker from {{ ref('stg_holdings__positions') }}
    where ticker != 'CASH'

    union distinct

    select etf_ticker as ticker from {{ ref('benchmark_etfs') }}

),
```

and change the final select's `where days_ago <= 30` to:

```sql
where days_ago <= 30
  and ticker in (select ticker from universe)
```

- [ ] **Step 4: Update `_marts.yml`.** Under `holdings_benchmarks`:
  - Remove `not_null` from `sector` and `cap_tier` (funds are null); keep their `accepted_values` (nulls pass).
  - Expand `benchmark_type` accepted_values to `['sector', 'cap_style', 'market', 'bond_market', 'duration']`.
  - Add three column blocks after `company_name`:

```yaml
      - name: asset_class
        data_type: string
        description: equity / fixed_income — the routing class (cash never appears here).
        data_tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['equity', 'fixed_income']
      - name: quote_type
        data_type: string
        description: yfinance quoteType (EQUITY / ETF / MUTUALFUND) — instrument form.
      - name: weight_pct
        data_type: float64
        description: Holding's share of total portfolio market value, in percent.
        data_tests:
          - not_null
```

  - Append the new mart's contract + tests:

```yaml
  - name: portfolio_composition
    description: >
      Sizing mart: one row per held ticker including cash and root holdings —
      live market value, portfolio weight, unrealized gain, asset class.
      Grain: one row per ticker.
    config:
      contract:
        enforced: true
    columns:
      - name: ticker
        data_type: string
        data_tests: [unique, not_null]
      - name: description
        data_type: string
        description: Company/fund name (yfinance), or the source description for cash rows.
      - name: asset_class
        data_type: string
        data_tests:
          - not_null
          - accepted_values:
              arguments:
                values: ['equity', 'fixed_income', 'cash']
      - name: quote_type
        data_type: string
        description: yfinance quoteType; null for the CASH pseudo-ticker.
      - name: sub_style
        data_type: string
        description: "Per-class style axis (bonds: duration bucket); null = axis skipped."
      - name: quantity
        data_type: float64
        description: Shares / units / dollars (money market).
      - name: latest_close
        data_type: float64
        description: Close on the common as-of date; null for unpriced cash rows.
      - name: market_value
        data_type: float64
        description: quantity x latest close (cash - source value).
        data_tests: [not_null]
      - name: weight_pct
        data_type: float64
        description: Share of total portfolio market value, in percent.
        data_tests: [not_null]
      - name: cost_basis
        data_type: float64
        description: Total cost basis from the source; null for cash.
      - name: unrealized_gain_pct
        data_type: float64
        description: market_value vs cost_basis, in percent; null for cash / missing basis.
      - name: is_root
        data_type: boolean
        description: True when the holding IS its own benchmark (held SPY/AGG) — display with no comparison.
        data_tests: [not_null]
      - name: as_of_date
        data_type: date
        description: Batch date of the underlying holdings import.
        data_tests: [not_null]
```

- [ ] **Step 5: Replace the axis guardrail.** Delete the old test and create `transformation/tests/assert_holdings_benchmarked_on_expected_axes.sql`:

```sql
-- Guardrail: every non-cash holding resolves the number of benchmark axes its
-- asset class prescribes (equity stock = 2, equity fund = 1, fixed income =
-- 1 + duration-if-mapped), where self-suppressed pairings (roots) count as
-- resolved. Catches seed drift, taxonomy renames, and unmapped sub_styles
-- before they silently drop a comparison.

with holdings as (

    select ticker, asset_class, quote_type, sub_style
    from {{ ref('int_holdings_classified') }}
    where asset_class is not null
      and asset_class != 'cash'

),

expected as (

    select
        ticker,
        case
            when quote_type = 'EQUITY'          then 2
            when asset_class = 'fixed_income'   then 1 + if(sub_style is not null, 1, 0)
            when asset_class = 'equity'         then 1
            else 0
        end as n_expected
    from holdings

),

routed as (

    select
        holding_ticker,
        countif(is_self) as n_self
    from {{ ref('int_benchmark_routing') }}
    group by holding_ticker

),

resolved as (

    select
        holding_ticker,
        count(distinct benchmark_type) as n_axes
    from {{ ref('holdings_benchmarks') }}
    group by holding_ticker

)

select
    e.ticker,
    e.n_expected,
    coalesce(r.n_axes, 0) as n_resolved,
    coalesce(s.n_self, 0) as n_self_suppressed
from expected e
left join resolved r on r.holding_ticker = e.ticker
left join routed   s on s.holding_ticker = e.ticker
where coalesce(r.n_axes, 0) + coalesce(s.n_self, 0) < e.n_expected
```

```bash
git rm transformation/tests/assert_holdings_benchmarked_on_both_axes.sql
```

- [ ] **Step 6: Create the weights guardrail** at `transformation/tests/assert_portfolio_weights_sum.sql`:

```sql
-- Weights are shares of one whole; if they don't sum to ~100 the valuation
-- or the window function broke. Tolerance absorbs per-row rounding.

select sum(weight_pct) as total_weight
from {{ ref('portfolio_composition') }}
having abs(sum(weight_pct) - 100) > 0.5
```

- [ ] **Step 7: Full build.** Run: `cd transformation && ~/.local/bin/dbt build`. Expected: all green (new marts, contracts, all guardrails) in the dev sandbox. Then eyeball composition:

```bash
cd transformation && ~/.local/bin/dbt show --inline "select ticker, asset_class, round(weight_pct,1) w, is_root from {{ ref('portfolio_composition') }} order by weight_pct desc" --limit 20
```

Expected: 13 rows (12 tickers + CASH), SPY `is_root=true`, weights descending, cash rows with weights.

- [ ] **Step 8: Commit.**

```bash
git add transformation/models/marts/ transformation/tests/
git commit -m "feat(dbt): asset-class-aware holdings_benchmarks + portfolio_composition sizing mart + scoped ticker_trend"
```

---

### Task 7: Privacy plumbing — `prod-private` target, schema routing, compile-time interlock

**Files:**
- Modify: `~/.dbt/profiles.yml` (user file, outside repo)
- Modify: `transformation/macros/generate_schema_name.sql`
- Create: `transformation/macros/assert_portfolio_isolation.sql`
- Modify: `transformation/dbt_project.yml` (on-run-start hook)
- Modify: `Makefile`, `.gitignore`

**Interfaces:**
- Consumes: var `holdings_source` (Tasks 4–6).
- Produces: target `prod-private` → datasets `anchor_staging_private` / `anchor_intermediate_private` / `anchor_marts_private` / `anchor_seeds_private`; `make build-private`, `make ingest-holdings-demo`, `make ingest-holdings-real`. Task 8's app reads `anchor_marts_private` in real mode.

- [ ] **Step 1: Add the `prod-private` target to `~/.dbt/profiles.yml`** (inside `anchor.outputs`, sibling of `prod`):

```yaml
    prod-private:
      type: bigquery
      method: service-account
      project: anchor-495115
      dataset: anchor_private       # catch-all; per-layer +schema routes to anchor_*_private
      keyfile: /Users/timurakhtemov/.dbt/anchor-bigquery-key.json
      threads: 4
      location: US
```

- [ ] **Step 2: Route `prod-private` in `generate_schema_name.sql`.** Replace the `{%- if ... -%}` block with:

```sql
    {%- if target.name == 'prod' and custom_schema_name is not none -%}

        {{ custom_schema_name | trim }}

    {%- elif target.name == 'prod-private' and custom_schema_name is not none -%}

        {# Private mirror of the prod layout: anchor_marts -> anchor_marts_private.
           Full layer isolation so nothing public-facing ever reads these. #}
        {{ custom_schema_name | trim }}_private

    {%- else -%}

        {{ default_schema }}

    {%- endif -%}
```

- [ ] **Step 3: Create the interlock** at `transformation/macros/assert_portfolio_isolation.sql`:

```sql
{#
  PRIVACY INTERLOCK. The public contract (prod -> anchor_marts -> committed
  snapshot -> public deploy) and CI must never be built from real holdings.
  This is the structural guarantee from docs/make_it_real_design.md: a leak
  is not a mistake you can make — it's a build the system refuses to run.
  Runs from on-run-start (dbt_project.yml).
#}
{% macro assert_portfolio_isolation() %}
    {% if var('holdings_source', 'demo') == 'real' and target.name in ('prod', 'ci') %}
        {{ exceptions.raise_compiler_error(
            "PRIVACY INTERLOCK: holdings_source=real cannot build into the public '"
            ~ target.name ~ "' target. Use --target prod-private (make build-private)."
        ) }}
    {% endif %}
{% endmacro %}
```

and register it in `transformation/dbt_project.yml` (top level, after `vars:` block):

```yaml
on-run-start:
  - "{{ assert_portfolio_isolation() }}"
```

- [ ] **Step 4: Add Makefile targets** (after `build-prod`):

```make
ingest-holdings-demo:  ## Load the committed sample portfolio -> raw_holdings.holdings_demo
	python ingestion/ingest_holdings.py --from-csv data/sample_portfolio.csv --portfolio demo

ingest-holdings-real:  ## Load a real Fidelity export + private fund classes (data/private/, gitignored)
	python ingestion/ingest_holdings.py --from-csv data/private/fidelity_positions.csv --portfolio real \
		--fund-classifications data/private/fund_classifications_real.csv

build-private: deps  ## dbt build the REAL portfolio into the anchor_*_private datasets
	cd transformation && $(DBT) build --target prod-private --vars '{holdings_source: real}'
```

and add `ingest-holdings-demo ingest-holdings-real build-private` to the `.PHONY` line.

- [ ] **Step 5: Gitignore the private inputs.** Append to `.gitignore`:

```
# real portfolio inputs — never committed (see docs/make_it_real_design.md)
data/private/
```

- [ ] **Step 6: Verify the interlock refuses.** Run: `cd transformation && ~/.local/bin/dbt build --target prod --vars '{holdings_source: real}' --select stg_holdings__positions`. Expected: **compilation error** containing `PRIVACY INTERLOCK`. (This failing is the test passing.)

- [ ] **Step 7: Verify the public prod build (demo).** Run: `cd transformation && ~/.local/bin/dbt build --target prod`. Expected: all green; new marts land in `anchor_marts`.

- [ ] **Step 8: Commit.**

```bash
git add transformation/macros/ transformation/dbt_project.yml Makefile .gitignore
git commit -m "feat(dbt): prod-private target routing + privacy interlock (real can never build public targets)"
```

---

### Task 8: Serve layer — world switch in the seam, composition-driven holdings tier, allocation bar

**Files:**
- Modify: `app/data.py`
- Modify: `app/ui.py`
- Modify: `app/app.py` (holdings tier)
- Modify: `app/export_snapshot.py` (TABLES list)

**Interfaces:**
- Consumes: `portfolio_composition` + reworked `holdings_benchmarks` (Task 6), `anchor_marts_private` (Task 7).
- Produces: `data.portfolio_composition() -> pd.DataFrame`; env switch `ANCHOR_PORTFOLIO=real`; `ui.allocation_bar(alloc: pd.DataFrame) -> alt.Chart`, `ui.ASSET_CLASS_COLORS`, `ui.ASSET_CLASS_LABELS`, `ui.money(x) -> str`.

- [ ] **Step 1: World switch + new reader in `app/data.py`.** Replace the line `MARTS_DATASET = "anchor_marts"` with:

```python
# demo (default) reads the public contract; ANCHOR_PORTFOLIO=real points the
# live-BigQuery path at the private mirror. The snapshot path is demo-only by
# construction (the exporter only knows anchor_marts).
PORTFOLIO = os.environ.get("ANCHOR_PORTFOLIO", "demo")
MARTS_DATASET = "anchor_marts_private" if PORTFOLIO == "real" else "anchor_marts"
```

After the `SOURCE = _resolve_source()` line, add:

```python
if PORTFOLIO == "real" and SOURCE == "snapshot":
    raise RuntimeError(
        "ANCHOR_PORTFOLIO=real requires live BigQuery access; the committed "
        "snapshot is demo-only by design."
    )
```

At the bottom, add the reader:

```python
def portfolio_composition() -> pd.DataFrame:
    return _read("portfolio_composition").sort_values("weight_pct", ascending=False)
```

- [ ] **Step 2: Visual vocabulary additions in `app/ui.py`.** After the `DIR_COLOR` line, add:

```python
# Asset-class identity (allocation bar + class dots). Fixed assignment, never
# cycled; deliberately distinct from the reserved semantic colors (green/red =
# performance verdicts, orange/blue = macro direction). Palette validated for
# lightness / chroma / CVD separation / contrast (dataviz six-checks, 2026-07-01).
ASSET_CLASS_COLORS = {"equity": "#0d9488", "fixed_income": "#7c3aed", "cash": "#b45309"}
ASSET_CLASS_LABELS = {"equity": "Equities", "fixed_income": "Fixed income", "cash": "Cash"}
```

After `fmt_date`, add:

```python
def money(x, digits=2) -> str:
    return "—" if pd.isna(x) else f"${x:,.{digits}f}"
```

At the bottom, add the allocation bar (single normalized stacked bar; 2px white
segment gaps; tooltip per segment; identity is never color-alone — the caller
renders a labeled legend line under it):

```python
def allocation_bar(alloc: pd.DataFrame):
    """One horizontal 100% stacked bar of portfolio weight by asset class.

    `alloc` columns: asset_class, weight_pct. Order and colors are fixed by
    ASSET_CLASS_COLORS (identity follows the class, never its rank).
    """
    order = [c for c in ASSET_CLASS_COLORS if c in set(alloc["asset_class"])]
    df = alloc.copy()
    df["label"] = df["asset_class"].map(ASSET_CLASS_LABELS)
    df["_order"] = df["asset_class"].map({c: i for i, c in enumerate(order)})
    return (
        alt.Chart(df)
        .mark_bar(height=20, stroke="#ffffff", strokeWidth=2)
        .encode(
            x=alt.X("weight_pct:Q", stack="normalize", axis=None),
            color=alt.Color(
                "asset_class:N",
                scale=alt.Scale(domain=order, range=[ASSET_CLASS_COLORS[c] for c in order]),
                legend=None,
            ),
            order=alt.Order("_order:Q"),
            tooltip=[
                alt.Tooltip("label:N", title="Asset class"),
                alt.Tooltip("weight_pct:Q", title="Weight (%)", format=".1f"),
            ],
        )
        .properties(height=20)
        .configure_view(strokeWidth=0)
    )


def class_dot(asset_class: str) -> str:
    """A small colored identity dot for the allocation legend line."""
    color = ASSET_CLASS_COLORS.get(asset_class, SLATE)
    return (
        f"<span style='display:inline-block;width:9px;height:9px;border-radius:50%;"
        f"background:{color};margin-right:5px'></span>"
    )
```

- [ ] **Step 3: Rewrite the holdings tier in `app/app.py`.** Replace `render_holdings` and `_render_rollup` (lines 166–223) with:

```python
AXIS_LABELS = {
    "sector": "Sector",
    "cap_style": "Cap-style",
    "market": "Market",
    "bond_market": "Bond market",
    "duration": "Duration",
}
# Reading order within the tier: growth assets, then rate-driven, then cash.
ASSET_CLASS_ORDER = ["equity", "fixed_income", "cash"]


def render_holdings(hkey: str):
    comp = data.portfolio_composition()
    hb = data.holdings_benchmarks()
    rel_col, lab_col = f"relative_{hkey}_pp", f"label_{hkey}"
    hold_col, bench_col = f"holding_{hkey}_pct", f"benchmark_{hkey}_pct"

    st.subheader("Holdings")
    st.caption(
        "Your portfolio, sized by weight. Each holding is compared against the "
        "benchmarks appropriate to its asset class — read under the sectors and "
        "macro regime above."
    )

    _render_allocation(comp)
    _render_rollup(hb, lab_col)

    for asset_class in ASSET_CLASS_ORDER:
        grp = comp[comp["asset_class"] == asset_class]
        if grp.empty:
            continue
        st.markdown(
            ui.class_dot(asset_class)
            + f"<span style='font-weight:700'>{ui.ASSET_CLASS_LABELS[asset_class]}</span>"
            + f"<span style='color:{ui.SLATE};font-size:0.85rem'>"
            f" · {grp['weight_pct'].sum():.1f}% of portfolio</span>",
            unsafe_allow_html=True,
        )
        for _, h in grp.iterrows():
            if asset_class == "cash":
                _render_cash_row(h)
            else:
                _render_holding_card(h, hb, hold_col, bench_col, rel_col, lab_col)


def _render_allocation(comp: pd.DataFrame):
    alloc = comp.groupby("asset_class", as_index=False)["weight_pct"].sum()
    st.altair_chart(ui.allocation_bar(alloc), use_container_width=True)
    legend = "&nbsp;&nbsp;".join(
        ui.class_dot(row["asset_class"])
        + f"{ui.ASSET_CLASS_LABELS[row['asset_class']]} {row['weight_pct']:.1f}%"
        for _, row in alloc.sort_values("weight_pct", ascending=False).iterrows()
    )
    st.markdown(
        f"<div style='font-size:0.85rem;color:{ui.SLATE};margin:-6px 0 10px'>{legend}</div>",
        unsafe_allow_html=True,
    )


def _render_holding_card(h, hb, hold_col, bench_col, rel_col, lab_col):
    with st.container(border=True):
        top_l, top_r = st.columns([3.2, 2])
        with top_l:
            # equities: sector + cap chips (from the benchmark row, which carries
            # the classification); bond funds: duration chip; roots: root badge
            benches = hb[hb["holding_ticker"] == h["ticker"]]
            chips = []
            if not benches.empty and benches.iloc[0]["quote_type"] == "EQUITY":
                head = benches.iloc[0]
                chips = [ui.chip(head["sector"]), ui.chip(f"{head['cap_tier']}-cap")]
            elif h["asset_class"] == "fixed_income" and pd.notna(h["sub_style"]):
                chips = [ui.chip(f"{h['sub_style']} duration")]
            if h["is_root"]:
                chips.append(ui.chip("market root", fg=ui.TEAL, bg="#cffafe"))
            st.markdown(
                f"**{h['ticker']}**  ·  {h['description']}  " + " ".join(chips),
                unsafe_allow_html=True,
            )
            gain = (
                ui.colored(ui.pct(h["unrealized_gain_pct"]), ui.ret_color(h["unrealized_gain_pct"]))
                if pd.notna(h["unrealized_gain_pct"])
                else "—"
            )
            st.markdown(
                f"<span style='color:{ui.SLATE};font-size:0.85rem'>"
                f"{h['weight_pct']:.1f}% of portfolio · {ui.money(h['market_value'])} · "
                f"since purchase: </span>{gain}",
                unsafe_allow_html=True,
            )
        with top_r:
            tr = trend_for(h["ticker"])
            if not tr.empty:
                st.altair_chart(ui.price_spark(tr), use_container_width=True)

        benches = hb[hb["holding_ticker"] == h["ticker"]]
        for _, b in benches.iterrows():
            axis = AXIS_LABELS.get(b["benchmark_type"], b["benchmark_type"])
            c1, c2, c3 = st.columns([2.5, 3, 2])
            with c1:
                st.markdown(f"{axis}: vs **{b['benchmark_etf']}**")
            with c2:
                st.markdown(
                    f"{ui.pct(b[hold_col])} vs {ui.pct(b[bench_col])}  "
                    f"({ui.signed_pp(b[rel_col])})"
                )
            with c3:
                st.markdown(ui.pill(b[lab_col]), unsafe_allow_html=True)
        if h["is_root"] and benches.empty:
            st.markdown(
                f"<span style='color:{ui.SLATE};font-size:0.85rem'>This holding is the "
                f"market reference point — other holdings are compared against it.</span>",
                unsafe_allow_html=True,
            )


def _render_cash_row(h):
    with st.container(border=True):
        c1, c2 = st.columns([4, 2])
        with c1:
            st.markdown(f"**{h['ticker']}**  ·  {h['description']}")
        with c2:
            st.markdown(
                f"{ui.money(h['market_value'])}"
                f"<span style='color:{ui.SLATE};font-size:0.85rem'> · "
                f"{h['weight_pct']:.1f}% of portfolio</span>",
                unsafe_allow_html=True,
            )


def _render_rollup(hb: pd.DataFrame, lab_col: str):
    """Ahead/behind tally per benchmark axis present in the portfolio."""
    axes = [a for a in AXIS_LABELS if a in set(hb["benchmark_type"])]
    cols = st.columns(max(len(axes), 1))
    for col, axis_key in zip(cols, axes):
        sub = hb[hb["benchmark_type"] == axis_key]
        counts = sub[lab_col].value_counts()
        with col:
            st.markdown(
                f"<span style='color:{ui.SLATE};font-size:0.85rem'>{AXIS_LABELS[axis_key]} axis: </span>"
                + ui.colored(f"{int(counts.get('ahead', 0))} ahead", ui.POS)
                + "<span style='color:#cbd5e1'> · </span>"
                + ui.colored(f"{int(counts.get('behind', 0))} behind", ui.NEG)
                + "<span style='color:#cbd5e1'> · </span>"
                + ui.colored(f"{int(counts.get('in_line', 0))} in line", ui.SLATE),
                unsafe_allow_html=True,
            )
```

- [ ] **Step 4: Add the mart to the snapshot exporter.** In `app/export_snapshot.py`, add `"portfolio_composition",` to `TABLES` (after `"holdings_benchmarks",`).

- [ ] **Step 5: Run and verify demo mode.** Run: `GOOGLE_APPLICATION_CREDENTIALS=~/.dbt/anchor-bigquery-key.json streamlit run app/app.py`. Expected: allocation bar with three segments + legend line; equities grouped first with weight/value/gain lines and sector+cap chips; VOO/FXAIX cards show one "Market: vs SPY" row; SPY card shows "market root" badge and the reference-point line; BND/FXNAX show "Bond market: vs AGG" + "Duration: vs IEF"; cash rows show balances; sector tier shows 11 rows. Hard-refresh the tab after any server restart (known gotcha).

- [ ] **Step 6: Commit.**

```bash
git add app/data.py app/ui.py app/app.py app/export_snapshot.py
git commit -m "feat(app): composition-driven holdings tier with allocation bar, asset-class grouping, weights and gains"
```

---

### Task 9: Real-portfolio cutover (human-in-the-loop)

**Files:**
- Create (LOCAL ONLY, gitignored): `data/private/fidelity_positions.csv`, `data/private/fund_classifications_real.csv`

**Interfaces:**
- Consumes: everything above.
- Produces: populated `raw_holdings.holdings_real` + `anchor_*_private` datasets; verified real-mode app.

- [ ] **Step 1: Timur exports Fidelity positions** (Fidelity → Positions → download) and saves as `data/private/fidelity_positions.csv`. Verify the header row matches the parser's expected columns (Task 1 Step 1); if it differs, fix `parse_fidelity_positions` + the sample CSV in the same change.

- [ ] **Step 2: Identify which real holdings need classification rows.** Run:

```bash
./venv/bin/python -c "
import yfinance as yf
from ingestion.holdings_csv import parse_fidelity_positions
from pathlib import Path
rows = parse_fidelity_positions(Path('data/private/fidelity_positions.csv').read_text())
for t in sorted({r['ticker'] for r in rows if r['ticker']}):
    print(t, yf.Ticker(t).info.get('quoteType'))
"
```

Every ticker printing `ETF` or `MUTUALFUND` needs a row in `data/private/fund_classifications_real.csv` (`ticker,asset_class,sub_style`; duration bucket for bond funds hand-verified from the fund's stated average duration: <3.5y = short, 3.5–7y = intermediate, >7y = long).

- [ ] **Step 3: Load and rebuild.** Run: `make ingest-holdings-real`, then `make ingest` (universe now includes real tickers), then `make build-private`. Expected: all green — the guardrails (fund coverage, expected axes, weights sum) are now validating the *real* portfolio.

- [ ] **Step 4: Verify real mode locally.** Run: `ANCHOR_PORTFOLIO=real GOOGLE_APPLICATION_CREDENTIALS=~/.dbt/anchor-bigquery-key.json streamlit run app/app.py`. Expected: the actual portfolio, sized and benchmarked. Verify no real ticker appears in demo mode (unset the env var, reload).

- [ ] **Step 5: Confirm the public path is untouched.** Run: `git status` → nothing to commit under `data/`; `python app/export_snapshot.py` then inspect: `./venv/bin/python -c "import pandas as pd; print(sorted(pd.read_parquet('app/snapshot/portfolio_composition.parquet')['ticker']))"`. Expected: demo tickers only.

- [ ] **Step 6: Commit** (snapshot refresh only — no private files):

```bash
git add app/snapshot/
git commit -m "chore(app): refresh committed snapshot with portfolio_composition (demo)"
```

---

### Task 10: SnapTrade live connection (phase 2 — severable)

**Files:**
- Create: `ingestion/snaptrade_connect.py`
- Modify: `ingestion/ingest_holdings.py` (add `--from-snaptrade`)
- Modify: `ingestion/requirements.txt` (add `snaptrade-python-sdk`)

**Interfaces:**
- Consumes: SnapTrade account (Timur registers at snaptrade.com; free personal tier), secrets in `.env`: `SNAPTRADE_CLIENT_ID`, `SNAPTRADE_CONSUMER_KEY`, `SNAPTRADE_USER_ID`, `SNAPTRADE_USER_SECRET`.
- Produces: `fetch_snaptrade_positions() -> list[dict]` (same dict shape as `parse_fidelity_positions`); `--from-snaptrade` appends to `holdings_real` with `source='snaptrade'`.

- [ ] **Step 1: Human setup.** Timur creates a SnapTrade developer account, registers an app, and puts `SNAPTRADE_CLIENT_ID` + `SNAPTRADE_CONSUMER_KEY` in `.env`. Run: `./venv/bin/pip install snaptrade-python-sdk` and append `snaptrade-python-sdk` to `ingestion/requirements.txt`.

- [ ] **Step 2: One-time connect script** at `ingestion/snaptrade_connect.py`:

```python
"""One-time SnapTrade setup: register the user, print the hosted connection
portal URL. Timur completes the Fidelity login IN THE BROWSER — brokerage
credentials never touch this codebase; we hold only a revocable, read-only
user secret (stored in .env, gitignored).
"""
from __future__ import annotations

import os

from dotenv import load_dotenv
from snaptrade_client import SnapTrade

load_dotenv()


def main() -> None:
    snaptrade = SnapTrade(
        client_id=os.environ["SNAPTRADE_CLIENT_ID"],
        consumer_key=os.environ["SNAPTRADE_CONSUMER_KEY"],
    )
    user_id = os.environ.get("SNAPTRADE_USER_ID", "anchor-timur")
    secret = os.environ.get("SNAPTRADE_USER_SECRET")

    if not secret:
        resp = snaptrade.authentication.register_snap_trade_user(user_id=user_id)
        secret = resp.body["userSecret"]
        print("Add these to .env (NEVER commit them):")
        print(f"  SNAPTRADE_USER_ID={user_id}")
        print(f"  SNAPTRADE_USER_SECRET={secret}")

    login = snaptrade.authentication.login_snap_trade_user(
        user_id=user_id, user_secret=secret
    )
    print("\nOpen this URL in your browser and connect Fidelity (read-only):")
    print(login.body["redirectURI"])


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verification checkpoint — probe the positions payload before mapping it.** After the browser connect succeeds, dump one raw payload to the scratchpad (NOT the repo) and read the actual field names — the SDK's response shape is verified, not assumed:

```bash
./venv/bin/python -c "
import json, os
from dotenv import load_dotenv
from snaptrade_client import SnapTrade
load_dotenv()
st = SnapTrade(client_id=os.environ['SNAPTRADE_CLIENT_ID'], consumer_key=os.environ['SNAPTRADE_CONSUMER_KEY'])
uid, sec = os.environ['SNAPTRADE_USER_ID'], os.environ['SNAPTRADE_USER_SECRET']
accounts = st.account_information.list_user_accounts(user_id=uid, user_secret=sec).body
print(json.dumps(accounts, indent=2, default=str)[:2000])
pos = st.account_information.get_user_account_positions(user_id=uid, user_secret=sec, account_id=accounts[0]['id']).body
print(json.dumps(pos[:2], indent=2, default=str))
"
```

- [ ] **Step 4: Add `fetch_snaptrade_positions` + `--from-snaptrade` to `ingest_holdings.py`.** Target shape (adjust field paths to what Step 3 actually shows):

```python
def fetch_snaptrade_positions() -> list[dict]:
    """Pull live positions for every connected account, normalized to the same
    dict shape parse_fidelity_positions produces."""
    import os

    from dotenv import load_dotenv
    from snaptrade_client import SnapTrade

    load_dotenv()
    st = SnapTrade(
        client_id=os.environ["SNAPTRADE_CLIENT_ID"],
        consumer_key=os.environ["SNAPTRADE_CONSUMER_KEY"],
    )
    uid = os.environ["SNAPTRADE_USER_ID"]
    sec = os.environ["SNAPTRADE_USER_SECRET"]

    rows: list[dict] = []
    for account in st.account_information.list_user_accounts(user_id=uid, user_secret=sec).body:
        positions = st.account_information.get_user_account_positions(
            user_id=uid, user_secret=sec, account_id=account["id"]
        ).body
        for p in positions:
            symbol = (p.get("symbol") or {}).get("symbol") or {}
            units = p.get("units") or p.get("fractional_units")
            price = p.get("price")
            rows.append(
                {
                    "account_number": account.get("number") or account["id"],
                    "account_name": account.get("name"),
                    "ticker": symbol.get("symbol"),
                    "description": symbol.get("description"),
                    "quantity": float(units) if units is not None else None,
                    "price": float(price) if price is not None else None,
                    "market_value": (float(units) * float(price))
                    if units is not None and price is not None
                    else None,
                    "cost_basis_total": (float(p["average_purchase_price"]) * float(units))
                    if p.get("average_purchase_price") is not None and units is not None
                    else None,
                }
            )
    return rows
```

CLI wiring in `main()`: add `ap.add_argument("--from-snaptrade", action="store_true")`; when set, require `--portfolio real`, build the DataFrame from `fetch_snaptrade_positions()` with `source='snaptrade'`, and append via the same load path (factor the DataFrame-building tail of `ingest_holdings_csv` into a shared `_load_positions(bq_client, rows, portfolio, as_of, source)` helper both modes call).

- [ ] **Step 5: End-to-end pull.** Run: `./venv/bin/python ingestion/ingest_holdings.py --from-snaptrade --portfolio real`, then `make build-private`, then the real-mode app. Expected: same portfolio as Task 9's CSV path (SnapTrade replaced transport, nothing else). If cash/SPAXX arrives differently than the CSV path (e.g. as a balance, not a position), map it to a `ticker=None` row so staging's CASH path handles it.

- [ ] **Step 6: Commit.**

```bash
git add ingestion/snaptrade_connect.py ingestion/ingest_holdings.py ingestion/requirements.txt
git commit -m "feat(ingestion): SnapTrade live connection -> holdings_real (read-only, secrets in .env)"
```

---

### Task 11: Ops + docs — Dagster asset, exposures, README/handoff, docs site, live demo refresh

**Files:**
- Modify: `orchestration/anchor_orchestration/ingestion.py`, `orchestration/anchor_orchestration/definitions.py`
- Modify: `transformation/models/marts/_exposures.yml`
- Modify: `README.md`, `handoff.md`, `CLAUDE.md`, `docs/make_it_real_design.md` (status line)
- Modify: `site/index.html` (regenerated dbt docs)

**Interfaces:**
- Consumes: `ingest_holdings_csv` + `SAMPLE_CSV_PATH` (Task 2).
- Produces: Dagster asset `holdings_demo` upstream of `ingest_yfinance` and the dbt `holdings` source; refreshed public artifacts.

- [ ] **Step 1: Dagster asset.** In `orchestration/anchor_orchestration/ingestion.py`, add:

```python
from dagster import asset

from ingestion.ingest_holdings import SAMPLE_CSV_PATH, ingest_holdings_csv


@asset(
    key="holdings_demo",
    group_name="bronze",
    compute_kind="python",
    description="Committed sample portfolio -> raw_holdings.holdings_demo (append, as_of=today).",
)
def ingest_holdings_demo_asset(context, bigquery: BigQueryResource):
    """Load the demo portfolio. Real/SnapTrade pulls are deliberately manual and
    local — the scheduled public graph only ever touches the demo world."""
    with bigquery.get_client() as client:
        n = ingest_holdings_csv(client, csv_path=SAMPLE_CSV_PATH, portfolio="demo")
    context.log.info(f"holdings_demo: appended {n} rows")
```

Make `ingest_yfinance_asset` depend on it (the universe query reads the holdings table), by adding to its `@multi_asset(...)` decorator:

```python
    deps=["holdings_demo"],
```

Register in `definitions.py`: import `ingest_holdings_demo_asset` and add it to the `assets=[...]` list. The existing translator already maps the dbt source table `holdings_demo` to this asset key by name; `holdings_real` / `fund_classifications_real` don't appear in the manifest (the demo-var parse never references them).

- [ ] **Step 2: Verify the graph.** Run: `make dagster`, materialize all assets in the UI. Expected: `holdings_demo → ingest_yfinance → dbt models → snapshot_parquet` in dependency order, RUN_SUCCESS, dbt tests green as asset checks.

- [ ] **Step 3: Exposures.** In `_exposures.yml`, add `- ref('portfolio_composition')` to both exposures' `depends_on` lists.

- [ ] **Step 4: Docs pass.**
  - `README.md`: status paragraph (dynamic holdings + multi-asset now built); data-sources table (+`raw_holdings`, ~30 tickers, 11 sectors); model-layer table (+`portfolio_composition`, holdings staging/intermediates); "Key design decisions" (+asset-class routing, root rule, privacy interlock — one bullet each, linking `docs/make_it_real_design.md`); Limitations (remove "single-asset-class today", add "quantities are as-of the last import; prices are daily", "duration buckets are hand-assigned per fund"); Repo layout (+`data/`, holdings loader); Setup (+`make ingest-holdings-demo`).
  - `handoff.md`: new "DONE — make-it-real capstone" section (what shipped, how to run demo vs real, where private inputs live); update "state of the world" node count; next = Dagster+ Serverless.
  - `CLAUDE.md`: update model-layers + data-sources sections (holdings bronze, new marts, `holdings_source` var, `prod-private` target, privacy interlock); update the "Long-term direction" paragraph (dynamic holdings = built; next = Robinhood/other brokers, portfolio-over-time).
  - `docs/make_it_real_design.md`: status line → "built 2026-07-.., see handoff.md".
  - `transformation/models/marts/sector_performance.sql`: refresh the stale header comment (lines 5–7) — all 11 SPDR sectors are now ingested, so the "currently XLK/XLF/XLE/XLV/XLI" caveat is gone.
- [ ] **Step 5: Regenerate the docs site.** Run: `cd transformation && ~/.local/bin/dbt docs generate --static --target prod && cp target/static_index.html ../site/index.html`.

- [ ] **Step 6: Refresh prod + the live demo.** Run: `make refresh` (ingest → build prod → snapshot). Expected: 100+ dbt nodes green; snapshot parquets refreshed (demo). Then commit + push everything and confirm CI green: `gh run watch`.

```bash
git add orchestration/ transformation/models/marts/_exposures.yml README.md handoff.md CLAUDE.md docs/ site/index.html app/snapshot/
git commit -m "feat(ops): holdings_demo Dagster asset + exposures + docs for the make-it-real capstone"
git push
```

---

## Out of scope (per the spec — do not build)

Portfolio-over-time UI · credit axis for bonds · generalized bond context tier · private deploy (real = local only) · multi-user/`user_id`/RLS · EOD API migration · brokers beyond Fidelity · "hide amounts" toggle (optional follow-up).
