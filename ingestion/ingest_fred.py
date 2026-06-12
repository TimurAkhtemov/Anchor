import os
import sys
import logging
import requests
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
from google.cloud import bigquery

logger = logging.getLogger(__name__)

# Load local environment variables if .env file exists
load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")
PROJECT_ID = "anchor-495115"
DATASET_ID = "raw_fred"
KEYFILE_PATH = "/Users/timurakhtemov/.dbt/anchor-bigquery-key.json"

# The initial macroeconomic series to ingest
FRED_SERIES = {
    'DFF': 'Effective Federal Funds Rate',
    'CPIAUCSL': 'Consumer Price Index for All Urban Consumers: All Items',
    'UNRATE': 'Civilian Unemployment Rate',
    'DGS10': '10-Year Treasury Constant Maturity Rate'
}

def build_bigquery_client():
    """Build a BigQuery client from the local service-account keyfile, falling
    back to Application Default Credentials when it is absent (CI, or a Dagster
    cloud run that injects GOOGLE_APPLICATION_CREDENTIALS)."""
    if os.path.exists(KEYFILE_PATH):
        logger.info(f"Using service account keyfile: {KEYFILE_PATH}")
        return bigquery.Client.from_service_account_json(KEYFILE_PATH, project=PROJECT_ID)
    logger.info("Initializing BigQuery client with default credentials...")
    return bigquery.Client(project=PROJECT_ID)

def fetch_series_metadata(series_id, api_key):
    """
    Fetches metadata for a given FRED series.
    """
    url = "https://api.stlouisfed.org/fred/series"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json"
    }

    logger.info(f"Fetching metadata for series: {series_id}")
    response = requests.get(url, params=params)
    if response.status_code != 200:
        logger.error(f"Failed to fetch metadata for {series_id}: {response.text}")
        response.raise_for_status()

    data = response.json()
    series_info = data["seriess"][0]
    return series_info

def fetch_series_observations(series_id, api_key):
    """
    Fetches all observations for a given FRED series.
    """
    url = "https://api.stlouisfed.org/fred/series/observations"
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json"
    }

    logger.info(f"Fetching observations for series: {series_id}")
    response = requests.get(url, params=params)
    if response.status_code != 200:
        logger.error(f"Failed to fetch observations for {series_id}: {response.text}")
        response.raise_for_status()

    data = response.json()
    return data["observations"]

def ingest_fred(bq_client) -> dict:
    """Pull all configured FRED series + observations and write them to the
    raw_fred BigQuery dataset (WRITE_TRUNCATE). Returns {table: row_count}.

    Raises on any failure (no sys.exit) so the caller — the standalone CLI or a
    Dagster asset — owns the exit / failure behavior.
    """
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY environment variable is not set.")

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

    ingested_at = datetime.utcnow()

    metadata_list = []
    observations_list = []

    for series_id in FRED_SERIES.keys():
        # 1. Fetch metadata
        meta = fetch_series_metadata(series_id, FRED_API_KEY)
        # FRED returns last_updated like "2026-03-26 07:46:02-05"; strip the
        # timezone offset and parse to seconds, falling back to ingested_at.
        last_updated_str = meta.get("last_updated")
        try:
            last_updated = datetime.strptime(last_updated_str[:-3], "%Y-%m-%d %H:%M:%S")
        except Exception:
            last_updated = ingested_at

        metadata_list.append({
            'series_id': series_id,
            'title': meta.get('title'),
            'frequency': meta.get('frequency'),
            'units': meta.get('units'),
            'seasonal_adjustment': meta.get('seasonal_adjustment'),
            'last_updated': last_updated,
            'ingested_at': ingested_at
        })

        # 2. Fetch observations
        obs = fetch_series_observations(series_id, FRED_API_KEY)
        for o in obs:
            observations_list.append({
                'series_id': series_id,
                'date': o.get('date'),
                'value': o.get('value'),
                'ingested_at': ingested_at
            })

    # Process metadata dataframe
    df_meta = pd.DataFrame(metadata_list)
    df_meta['last_updated'] = pd.to_datetime(df_meta['last_updated'])
    df_meta['ingested_at'] = pd.to_datetime(df_meta['ingested_at'])

    # Process observations dataframe
    df_obs = pd.DataFrame(observations_list)
    # Convert dates to actual date objects
    df_obs['date'] = pd.to_datetime(df_obs['date']).dt.date
    # Coerce values to floats (e.g. "." -> NaN; BQ stores NaN as NULL, which we want)
    df_obs['value'] = pd.to_numeric(df_obs['value'], errors='coerce')
    df_obs['ingested_at'] = pd.to_datetime(df_obs['ingested_at'])

    # Define Explicit Schemas
    schema_meta = [
        bigquery.SchemaField("series_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("title", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("frequency", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("units", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("seasonal_adjustment", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("last_updated", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED")
    ]

    schema_obs = [
        bigquery.SchemaField("series_id", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("date", "DATE", mode="REQUIRED"),
        bigquery.SchemaField("value", "FLOAT", mode="NULLABLE"),
        bigquery.SchemaField("ingested_at", "TIMESTAMP", mode="REQUIRED")
    ]

    # Write metadata to BigQuery (Write Truncate)
    logger.info("Writing metadata to BigQuery...")
    job_config_meta = bigquery.LoadJobConfig(
        schema=schema_meta,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    table_ref_meta = dataset_ref.table("raw_fred_series")
    bq_client.load_table_from_dataframe(df_meta, table_ref_meta, job_config=job_config_meta).result()
    logger.info(f"Successfully loaded {PROJECT_ID}.{DATASET_ID}.raw_fred_series with {len(df_meta)} rows.")

    # Write observations to BigQuery (Write Truncate)
    logger.info("Writing observations to BigQuery...")
    job_config_obs = bigquery.LoadJobConfig(
        schema=schema_obs,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    table_ref_obs = dataset_ref.table("raw_fred_observations")
    bq_client.load_table_from_dataframe(df_obs, table_ref_obs, job_config=job_config_obs).result()
    logger.info(f"Successfully loaded {PROJECT_ID}.{DATASET_ID}.raw_fred_observations with {len(df_obs)} rows.")

    logger.info("Ingestion completed successfully.")
    return {"raw_fred_series": len(df_meta), "raw_fred_observations": len(df_obs)}

def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    if not FRED_API_KEY:
        logger.error("FRED_API_KEY environment variable is not set. Exiting.")
        sys.exit(1)
    try:
        client = build_bigquery_client()
    except Exception as e:
        logger.error(f"Failed to initialize BigQuery client: {e}")
        sys.exit(1)
    try:
        ingest_fred(client)
    except Exception as e:
        logger.error(f"Error during FRED ingestion: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
