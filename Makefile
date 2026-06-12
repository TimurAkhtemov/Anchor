# Anchor pipeline — tool-agnostic steps.
#
# The orchestrator (GitHub Actions today, possibly Dagster/Prefect later) is just
# a trigger over these targets; the pipeline logic lives here, not in YAML. A
# future orchestrator calls the same `make` targets (or the underlying scripts) —
# no rewrite. Same decoupling principle as the app's data.py source seam.
#
# Auth: ingestion + dbt read BigQuery creds from GOOGLE_APPLICATION_CREDENTIALS
# (or the local keyfile); FRED ingestion reads FRED_API_KEY. dbt target/profile
# is resolved by the caller's env (local ~/.dbt vs CI's DBT_PROFILES_DIR=ci).

.PHONY: help ingest deps build-prod snapshot refresh dagster

DAGSTER_HOME ?= $(CURDIR)/orchestration/.dagster_home

help:  ## List targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-12s %s\n", $$1, $$2}'

ingest:  ## Pull bronze: FRED + yfinance -> BigQuery (full refresh)
	python ingestion/ingest_fred.py
	python ingestion/ingest_yfinance.py

deps:  ## Install dbt packages
	dbt deps

build-prod: deps  ## dbt build + test into the prod marts (anchor_* datasets)
	dbt build --target prod

snapshot:  ## Export prod marts -> committed parquet (app/snapshot/)
	python app/export_snapshot.py

refresh: ingest build-prod snapshot  ## Full daily pipeline: ingest -> build -> snapshot

dagster:  ## Launch the Dagster UI locally (asset graph at http://localhost:3000)
	@mkdir -p $(DAGSTER_HOME)
	DAGSTER_HOME=$(DAGSTER_HOME) \
	GOOGLE_APPLICATION_CREDENTIALS=$(HOME)/.dbt/anchor-bigquery-key.json \
	DBT_PROFILES_DIR=$(HOME)/.dbt \
	PYTHONPATH=orchestration \
	dagster dev -m anchor_orchestration
