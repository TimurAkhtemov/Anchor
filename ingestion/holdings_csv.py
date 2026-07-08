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
