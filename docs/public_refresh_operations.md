# Public refresh operations

## The public credential

The public GitHub job uses its own Google service account, `anchor-public-refresh`,
instead of the broad local key. It can build the public (demo) world and cannot read
anything private. `scripts/check_public_credential.py` proves that.

`gcloud` is not installed here, so use the Cloud Console (project `anchor-495115`).

### 1. Create the account

IAM & Admin -> Service Accounts -> Create service account:
name `anchor-public-refresh`. Skip the optional grant steps in the wizard.

### 2. Grant roles

**Project level** (IAM & Admin -> IAM -> Grant access):

- `BigQuery Job User`

**Dataset level**: `BigQuery Data Editor` on each of these datasets (BigQuery Studio ->
dataset -> Sharing -> Permissions -> Add principal):

- `raw_yfinance`
- `raw_fred`
- `anchor`
- `anchor_staging`
- `anchor_intermediate`
- `anchor_marts`
- `anchor_seeds`
- `anchor_snapshots`
- `dbt_ci`

**Table level**: `BigQuery Data Viewer` on the table `raw_holdings.holdings_demo` only
(BigQuery Studio -> table -> Share -> Manage permissions).

Never grant anything at the `raw_holdings` dataset level or at project level beyond Job
User. That dataset also holds `holdings_real` and `fund_classifications_real`, and
`raw_yfinance_private` / `anchor_marts_private` hold the private world.

### 3. Create a key

Service account -> Keys -> Add key -> JSON. Save it **outside the repo** (for example
`~/.config/anchor/anchor-public-refresh.json`). Never commit it or place it under
`~/Desktop` or `~/Documents`.

### 4. Verify

```bash
GOOGLE_APPLICATION_CREDENTIALS=~/.config/anchor/anchor-public-refresh.json \
  python scripts/check_public_credential.py
```

Expected: exit 0 and `OK: ...`. The script requires `permission denied` on
`raw_holdings.holdings_real`, `raw_holdings.fund_classifications_real`,
`raw_yfinance_private`, `anchor_marts_private`, and successful reads on
`raw_holdings.holdings_demo`, `raw_yfinance`, `raw_fred`, `anchor_marts`. It only runs
`limit 0` queries, so no rows are fetched. A `NotFound` on a private table counts as a
failure because the denial is then unproven.

A denial that blocks dbt (a missing grant) will surface on the first real run. Record
any grant change here:

| Date | Change | Reason |
| --- | --- | --- |
| | | |

## Replacing the GitHub secret (at go-live)

Do this only when the public workflow is ready to switch over, not before:

```bash
gh secret set BQ_SA_KEY < ~/.config/anchor/anchor-public-refresh.json
```

Then trigger the workflow once and watch for permission errors. Afterwards, delete any
copies of the key you no longer need. Keep the key file outside the repo at all times.
