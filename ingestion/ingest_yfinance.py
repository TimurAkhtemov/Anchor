import csv
import os
import sys
import time
import logging
import pandas as pd
from datetime import datetime, UTC
from pathlib import Path
import yfinance as yf
from dotenv import load_dotenv
from google.api_core.exceptions import NotFound
from google.cloud import bigquery

logger = logging.getLogger(__name__)

# Load local environment variables from .env file
load_dotenv()

PROJECT_ID = "anchor-495115"
DATASET_ID = "raw_yfinance"
KEYFILE_PATH = "/Users/timurakhtemov/.dbt/anchor-bigquery-key.json"

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


def build_bigquery_client():
    """Build a BigQuery client from the local service-account keyfile, falling
    back to Application Default Credentials when it is absent (CI, or a Dagster
    cloud run that injects GOOGLE_APPLICATION_CREDENTIALS)."""
    if os.path.exists(KEYFILE_PATH):
        logger.info(f"Using service account keyfile: {KEYFILE_PATH}")
        return bigquery.Client.from_service_account_json(KEYFILE_PATH, project=PROJECT_ID)
    logger.info("Initializing BigQuery client with default credentials...")
    return bigquery.Client(project=PROJECT_ID)

def fetch_ticker_metadata(ticker):
    """
    Fetches ticker info from yfinance with retry mechanism and backoff.
    """
    logger.info(f"Fetching metadata for ticker: {ticker}")
    t = yf.Ticker(ticker)
    for attempt in range(3):
        try:
            info = t.info
            if info and isinstance(info, dict):
                return info
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed for ticker {ticker}: {e}")
            time.sleep(2 ** attempt)

    logger.error(f"Failed to fetch metadata for {ticker} after 3 attempts. Proceeding with empty metadata.")
    return {}

def fetch_ticker_prices(ticker, period="5y"):
    """
    Fetches historical daily prices for a given ticker and lookback period.
    """
    logger.info(f"Fetching historical prices for ticker: {ticker} (period: {period})")
    t = yf.Ticker(ticker)
    try:
        # Download historical prices
        hist = t.history(period=period)
        return hist
    except Exception as e:
        logger.error(f"Failed to fetch prices for {ticker}: {e}")
        return pd.DataFrame()

def ingest_yfinance(bq_client) -> dict:
    """Pull ticker metadata + 5y daily price bars for every configured ticker
    and write them to the raw_yfinance BigQuery dataset (WRITE_TRUNCATE).
    Returns {table: row_count}.

    Raises on any failure (no sys.exit) so the caller — the standalone CLI or a
    Dagster asset — owns the exit / failure behavior.
    """
    # Ensure BigQuery dataset exists
    dataset_ref = bq_client.dataset(DATASET_ID)
    try:
        bq_client.get_dataset(dataset_ref)
        logger.info(f"Dataset {PROJECT_ID}.{DATASET_ID} already exists.")
    except Exception:
        logger.info(f"Dataset {PROJECT_ID}.{DATASET_ID} not found. Creating it...")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        bq_client.create_dataset(dataset, timeout=30)
        logger.info(f"Created dataset {PROJECT_ID}.{DATASET_ID}")

    ingested_at = datetime.now(UTC)

    metadata_list = []
    prices_dfs = []

    tickers = resolve_universe(bq_client)
    logger.info(f"Resolved ticker universe: {len(tickers)} tickers: {tickers}")
    for ticker in tickers:
        # 1. Fetch Ticker Info
        info = fetch_ticker_metadata(ticker)

        metadata_list.append({
            'ticker': ticker,
            'name': info.get('longName') or info.get('shortName'),
            'sector': info.get('sector'),
            'industry': info.get('industry'),
            'market_cap': info.get('marketCap'),  # null for ETFs; used to bucket holdings into cap tiers
            'exchange': info.get('exchange'),
            'currency': info.get('currency'),
            'quote_type': info.get('quoteType'),  # EQUITY / ETF / MUTUALFUND / MONEYMARKET — the classification spine
            'ingested_at': ingested_at
        })

        # 2. Fetch Historical Price Bars
        df_hist = fetch_ticker_prices(ticker, period="5y")
        if not df_hist.empty:
            # Format DataFrame
            df_hist = df_hist.reset_index()
            # Standardize names
            df_hist = df_hist.rename(columns={
                'Date': 'date',
                'Open': 'open',
                'High': 'high',
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })

            # Keep only standard columns
            df_hist = df_hist[['date', 'open', 'high', 'low', 'close', 'volume']]
            df_hist['ticker'] = ticker
            df_hist['ingested_at'] = ingested_at

            prices_dfs.append(df_hist)
            logger.info(f"Fetched {len(df_hist)} price bars for {ticker}.")

            # Simple sleep to prevent hammering Yahoo API
            time.sleep(0.5)

    # Process metadata dataframe
    df_meta = pd.DataFrame(metadata_list)
    df_meta['market_cap'] = pd.to_numeric(df_meta['market_cap'], errors='coerce').astype('Int64')  # Nullable Int
    df_meta['ingested_at'] = pd.to_datetime(df_meta['ingested_at'])

    # Process observations dataframe
    if not prices_dfs:
        raise RuntimeError("No stock prices were successfully fetched.")

    df_prices = pd.concat(prices_dfs, ignore_index=True)
    df_prices['date'] = pd.to_datetime(df_prices['date']).dt.date
    df_prices['open'] = pd.to_numeric(df_prices['open'], errors='coerce')
    df_prices['high'] = pd.to_numeric(df_prices['high'], errors='coerce')
    df_prices['low'] = pd.to_numeric(df_prices['low'], errors='coerce')
    df_prices['close'] = pd.to_numeric(df_prices['close'], errors='coerce')
    df_prices['volume'] = pd.to_numeric(df_prices['volume'], errors='coerce').astype('Int64')  # Nullable Int
    df_prices['ingested_at'] = pd.to_datetime(df_prices['ingested_at'])

    # Define Explicit Schemas
    schema_meta = [
        bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("name", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("sector", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("industry", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("market_cap", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("exchange", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("currency", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("quote_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED")
    ]

    schema_prices = [
        bigquery.SchemaField("ticker", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("open", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("high", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("low", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("close", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("volume", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED")
    ]

    # Write metadata to BigQuery (Write Truncate)
    logger.info("Writing tickers metadata to BigQuery...")
    job_config_meta = bigquery.LoadJobConfig(
        schema=schema_meta,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    table_ref_meta = dataset_ref.table("raw_yfinance_tickers")
    bq_client.load_table_from_dataframe(df_meta, table_ref_meta, job_config=job_config_meta).result()
    logger.info(f"Successfully loaded {PROJECT_ID}.{DATASET_ID}.raw_yfinance_tickers with {len(df_meta)} rows.")

    # Write prices to BigQuery (Write Truncate)
    logger.info("Writing historical prices to BigQuery...")
    job_config_prices = bigquery.LoadJobConfig(
        schema=schema_prices,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    table_ref_prices = dataset_ref.table("raw_yfinance_prices")
    bq_client.load_table_from_dataframe(df_prices, table_ref_prices, job_config=job_config_prices).result()
    logger.info(f"Successfully loaded {PROJECT_ID}.{DATASET_ID}.raw_yfinance_prices with {len(df_prices)} rows.")

    logger.info("Ingestion completed successfully.")
    return {"raw_yfinance_tickers": len(df_meta), "raw_yfinance_prices": len(df_prices)}

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    try:
        client = build_bigquery_client()
    except Exception as e:
        logger.error(f"Failed to initialize BigQuery client: {e}")
        sys.exit(1)
    try:
        ingest_yfinance(client)
    except Exception as e:
        logger.error(f"Error during yfinance ingestion: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
