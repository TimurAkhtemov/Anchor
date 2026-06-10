import os
import sys
import time
import logging
import pandas as pd
import numpy as np
from datetime import datetime, UTC
import yfinance as yf
from dotenv import load_dotenv
from google.cloud import bigquery
from google.api_core.exceptions import GoogleAPIError

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Load local environment variables from .env file
load_dotenv()

PROJECT_ID = "anchor-495115"
DATASET_ID = "raw_yfinance"

# Two benchmark axes + the holdings we benchmark against them.
# Sector ETFs (SPDR Select Sector) — benchmark axis 1: holding vs its sector
SECTOR_ETFS = ['XLK', 'XLF', 'XLE', 'XLV', 'XLI']
# Cap-style ETFs — benchmark axis 2: holding vs its market-cap tier (SPY=large, MDY=mid, IWM=small)
CAP_STYLE_ETFS = ['SPY', 'MDY', 'IWM']
# Individual holdings — spread across sectors AND cap tiers so both benchmark axes are exercised.
# AAPL+IMMR are both Technology but different cap tiers (Large vs Small) — demonstrates the two axes.
#   AAPL=Tech/Large  JPM=Financials/Large  HIMS=Healthcare/Mid  TALO=Energy/Mid  CVLG=Industrials/Small  IMMR=Tech/Small
HOLDINGS = ['AAPL', 'JPM', 'HIMS', 'TALO', 'CVLG', 'IMMR']
TICKERS = SECTOR_ETFS + CAP_STYLE_ETFS + HOLDINGS

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

def main():
    # Initialize BigQuery client
    try:
        keyfile_path = "/Users/timurakhtemov/.dbt/anchor-bigquery-key.json"
        if os.path.exists(keyfile_path):
            logger.info(f"Using service account keyfile: {keyfile_path}")
            bq_client = bigquery.Client.from_service_account_json(keyfile_path, project=PROJECT_ID)
        else:
            logger.info("Initializing BigQuery client with default credentials...")
            bq_client = bigquery.Client(project=PROJECT_ID)
    except Exception as e:
        logger.error(f"Failed to initialize BigQuery client: {e}")
        sys.exit(1)
        
    # Ensure BigQuery dataset exists
    dataset_ref = bq_client.dataset(DATASET_ID)
    try:
        bq_client.get_dataset(dataset_ref)
        logger.info(f"Dataset {PROJECT_ID}.{DATASET_ID} already exists.")
    except Exception:
        logger.info(f"Dataset {PROJECT_ID}.{DATASET_ID} not found. Creating it...")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        dataset = bq_client.create_dataset(dataset, timeout=30)
        logger.info(f"Created dataset {PROJECT_ID}.{DATASET_ID}")

    ingested_at = datetime.now(UTC)
    
    metadata_list = []
    prices_dfs = []
    
    for ticker in TICKERS:
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
        logger.error("No stock prices were successfully fetched. Exiting.")
        sys.exit(1)
        
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
    try:
        table_ref_meta = dataset_ref.table("raw_yfinance_tickers")
        job_meta = bq_client.load_table_from_dataframe(df_meta, table_ref_meta, job_config=job_config_meta)
        job_meta.result()  # Wait for upload to complete
        logger.info(f"Successfully loaded tickers table {PROJECT_ID}.{DATASET_ID}.raw_yfinance_tickers with {len(df_meta)} rows.")
    except GoogleAPIError as e:
        logger.error(f"BigQuery metadata upload failed: {e}")
        sys.exit(1)
        
    # Write prices to BigQuery (Write Truncate)
    logger.info("Writing historical prices to BigQuery...")
    job_config_prices = bigquery.LoadJobConfig(
        schema=schema_prices,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    try:
        table_ref_prices = dataset_ref.table("raw_yfinance_prices")
        job_prices = bq_client.load_table_from_dataframe(df_prices, table_ref_prices, job_config=job_config_prices)
        job_prices.result()  # Wait for upload to complete
        logger.info(f"Successfully loaded prices table {PROJECT_ID}.{DATASET_ID}.raw_yfinance_prices with {len(df_prices)} rows.")
    except GoogleAPIError as e:
        logger.error(f"BigQuery prices upload failed: {e}")
        sys.exit(1)
        
    logger.info("Ingestion completed successfully.")

if __name__ == "__main__":
    main()
