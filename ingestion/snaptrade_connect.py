"""One-time SnapTrade setup: resolve the SnapTrade user, print the hosted
connection portal URL. Timur completes the Fidelity login IN THE BROWSER —
brokerage credentials never touch this codebase.

Account-type adaptation (discovered live, not assumed from the brief): a
*personal* SnapTrade API key has no register/userSecret model at all — the
account already comes with exactly one auto-provisioned user, and calling
`register_snap_trade_user` for it fails with HTTP 400 ("registerUser is not
available for personal keys"). Per SnapTrade's docs
(docs.snaptrade.com/docs/personal-vs-commercial), personal-key holders
resolve identity from the API key itself and should omit user_id/user_secret
where possible; this SDK build still requires non-None values client-side,
but an empty-string secret is accepted and the portal call succeeds. So:
  - If `list_snap_trade_users()` returns any user, this is a personal key —
    use that user id, skip registration, store an empty-string secret (kept
    only so ingest_holdings.py's expected SNAPTRADE_USER_SECRET var exists).
  - If it returns none, this is a commercial key — fall back to the brief's
    original register-a-new-user flow (id "anchor-timur").

Security: this script never prints the consumer key or the user secret (nor
the personal account's resolved user id, since that's an email address). On
first run it writes SNAPTRADE_USER_ID / SNAPTRADE_USER_SECRET to .env
directly, printing only a confirmation. Safe to re-run: if both are already
in .env, setup is skipped and a fresh connection portal URL is printed
(portal links expire after a few minutes).
"""
from __future__ import annotations

import os

from dotenv import find_dotenv, load_dotenv
from snaptrade_client import SnapTrade

ENV_PATH = find_dotenv(usecwd=True) or ".env"
load_dotenv(ENV_PATH)


def _append_to_env(user_id: str, user_secret: str) -> None:
    """Append SNAPTRADE_USER_ID / SNAPTRADE_USER_SECRET lines to .env,
    skipping any that are already present so re-runs stay idempotent."""
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            existing = f.read()
    except FileNotFoundError:
        existing = ""

    lines_to_add = []
    if "SNAPTRADE_USER_ID=" not in existing:
        lines_to_add.append(f"SNAPTRADE_USER_ID={user_id}")
    if "SNAPTRADE_USER_SECRET=" not in existing:
        lines_to_add.append(f"SNAPTRADE_USER_SECRET={user_secret}")

    if not lines_to_add:
        return

    with open(ENV_PATH, "a", encoding="utf-8") as f:
        if existing and not existing.endswith("\n"):
            f.write("\n")
        for line in lines_to_add:
            f.write(line + "\n")


def _env_has_credentials() -> bool:
    try:
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            existing = f.read()
    except FileNotFoundError:
        return False
    return "SNAPTRADE_USER_ID=" in existing and "SNAPTRADE_USER_SECRET=" in existing


def main() -> None:
    snaptrade = SnapTrade(
        client_id=os.environ["SNAPTRADE_CLIENT_ID"],
        consumer_key=os.environ["SNAPTRADE_CONSUMER_KEY"],
    )

    if _env_has_credentials():
        user_id = os.environ["SNAPTRADE_USER_ID"]
        secret = os.environ.get("SNAPTRADE_USER_SECRET", "")
        print("user credentials already present in .env (setup skipped)")
    else:
        existing_users = snaptrade.authentication.list_snap_trade_users().body
        if existing_users:
            # Personal API key: exactly one user is auto-provisioned at
            # signup; register_snap_trade_user is not available for it.
            user_id = existing_users[0]
            secret = ""
            print(
                "personal SnapTrade key detected: using the auto-provisioned "
                "user (registration skipped, not applicable for personal keys)"
            )
        else:
            # Commercial API key: explicit registration required.
            user_id = "anchor-timur"
            resp = snaptrade.authentication.register_snap_trade_user(user_id=user_id)
            secret = resp.body["userSecret"]
            print("commercial SnapTrade key detected: registered a new user")
        _append_to_env(user_id, secret)
        print("user credentials stored in .env")

    login = snaptrade.authentication.login_snap_trade_user(
        user_id=user_id, user_secret=secret
    )
    print("\nOpen this URL in your browser and connect Fidelity (read-only):")
    print(login.body["redirectURI"])


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # noqa: BLE001 - deliberately broad to sanitize output
        # Never print raw exception bodies here: SnapTrade ApiException.__str__
        # includes the HTTP response body/headers, which could echo request
        # context. Report only the exception type and, if present, HTTP status.
        status = getattr(exc, "status", None)
        print(f"SnapTrade call failed: {type(exc).__name__}" + (f" (HTTP {status})" if status else ""))
        raise SystemExit(1)
