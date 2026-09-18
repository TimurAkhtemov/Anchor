"""One-time SnapTrade setup: resolve the SnapTrade user, print the hosted
connection portal URL. Timur completes the Fidelity login IN THE BROWSER —
brokerage credentials never touch this codebase.

Account-type adaptation: a *personal* SnapTrade API key has no
register/userSecret model. Current Personal authentication resolves identity
from the signed API key and requires user_id/user_secret to be omitted. A
commercial key retains the explicit register-user flow.

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
from snaptrade_client import SnapTrade, SnapTradeAuth

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
    client_id = os.environ["SNAPTRADE_CLIENT_ID"]
    is_personal = client_id.startswith("PERS-")
    auth_factory = (
        SnapTradeAuth.personal_api_key if is_personal else SnapTradeAuth.commercial_api_key
    )
    snaptrade = SnapTrade(
        auth=auth_factory(
            client_id=client_id,
            consumer_key=os.environ["SNAPTRADE_CONSUMER_KEY"],
        )
    )

    # Personal client IDs currently use the PERS- prefix. No user fields are
    # sent; legacy empty user-secret entries in .env are harmless and ignored.
    if is_personal:
        login = snaptrade.authentication.login_snap_trade_user()
        print("personal SnapTrade key detected (user credentials omitted)")
    elif _env_has_credentials():
        user_id = os.environ["SNAPTRADE_USER_ID"]
        secret = os.environ["SNAPTRADE_USER_SECRET"]
        print("user credentials already present in .env (setup skipped)")
        login = snaptrade.authentication.login_snap_trade_user(
            user_id=user_id, user_secret=secret
        )
    else:
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
