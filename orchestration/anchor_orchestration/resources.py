"""Dagster resources for the Anchor code location.

The BigQuery client is the single auth seam: locally it resolves Application
Default Credentials (GOOGLE_APPLICATION_CREDENTIALS -> the service-account
keyfile); in a Dagster cloud run you swap to a `gcp_credentials` secret instead
— config, not code. This also unifies the auth that the ingestion scripts and
the snapshot export each used to wire up separately.
"""
from dagster_gcp import BigQueryResource

PROJECT_ID = "anchor-495115"

bigquery_resource = BigQueryResource(project=PROJECT_ID)
