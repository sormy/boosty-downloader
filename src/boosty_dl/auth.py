import json
import sys
import time
from typing import TypedDict
from urllib.parse import quote, unquote

from . import api

BOOSTY_COOKIE_DOMAIN = ".boosty.to"

SECONDS_PER_DAY = 86400

TOKEN_REFRESH_THRESHOLD_SECONDS = SECONDS_PER_DAY

AUTH_COOKIE_NAME = "auth"
CLIENT_ID_COOKIE_NAME = "_clientId"


class AuthData(TypedDict):
    accessToken: str  # access token, usually expires is 30 days
    refreshToken: str  # refresh token to refresh access token
    expiresAt: int  # expiration time in seconds since epoch for access token
    clientId: str  # client ID (needed for token refresh)


def _read_cookie(cookies_file: str, name: str) -> str | None:
    try:
        with open(cookies_file) as f:
            for line in f:
                if line.startswith("#") or not line.strip():
                    continue
                parts = line.strip().split("\t")
                if (
                    len(parts) >= 7
                    and parts[0] == BOOSTY_COOKIE_DOMAIN
                    and parts[5] == name
                ):
                    return unquote(parts[6])
    except Exception as e:
        print(f"ERROR: Unable to read cookie '{name}': {e}", file=sys.stderr)
    return None


def _write_cookie(cookies_file: str, name: str, value: str) -> bool:
    try:
        with open(cookies_file) as f:
            lines = f.readlines()

        encoded_value = quote(value)

        for i, line in enumerate(lines):
            if line.startswith("#") or not line.strip():
                continue
            parts = line.strip().split("\t")
            if (
                len(parts) >= 7
                and parts[0] == BOOSTY_COOKIE_DOMAIN
                and parts[5] == name
            ):
                parts[6] = encoded_value
                lines[i] = "\t".join(parts) + "\n"
                with open(cookies_file, "w") as f:
                    f.writelines(lines)
                return True
        return False
    except Exception as e:
        print(f"ERROR: Unable to write cookie '{name}': {e}", file=sys.stderr)
        return False


def _parse_cookie(cookies_file: str) -> AuthData | None:
    auth = _read_cookie(cookies_file, AUTH_COOKIE_NAME)
    client_id = _read_cookie(cookies_file, CLIENT_ID_COOKIE_NAME)

    if auth:
        try:
            auth_data = json.loads(auth)
            auth_data["clientId"] = client_id
            return auth_data
        except json.JSONDecodeError as e:
            print(f"ERROR: Unable to parse auth cookie: {e}", file=sys.stderr)
    else:
        print("ERROR: Required auth cookie not found", file=sys.stderr)

    return None


def _update_cookie(cookies_file: str, auth_data: AuthData) -> bool:
    value = json.dumps(
        {
            "accessToken": auth_data["accessToken"],
            "refreshToken": auth_data["refreshToken"],
            "expiresAt": auth_data["expiresAt"],
        }
    )
    return _write_cookie(cookies_file, AUTH_COOKIE_NAME, value)


def _get_time_until_expiry(expires_at_ms: int) -> float:
    return (expires_at_ms / 1000) - time.time()


def get_access_token(cookies_file: str, force_refresh: bool = False) -> str | None:
    auth_data = _parse_cookie(cookies_file)
    if not auth_data:
        return None

    time_until_expiry = _get_time_until_expiry(auth_data["expiresAt"])

    if force_refresh or time_until_expiry < TOKEN_REFRESH_THRESHOLD_SECONDS:
        if force_refresh:
            print(
                "Forcing access token refresh...",
                file=sys.stderr,
            )
        elif time_until_expiry < 0:
            print(
                "WARNING: Access token expired, refreshing...",
                file=sys.stderr,
            )
        else:
            hours = time_until_expiry / 3600
            print(
                f"WARNING: Access token expires in {hours:.1f} hours, refreshing...",
                file=sys.stderr,
            )

        try:
            if not auth_data["refreshToken"]:
                raise ValueError("No refresh token available")

            new_auth = api.refresh_token(
                auth_data["refreshToken"], auth_data["clientId"]
            )

            if _update_cookie(cookies_file, new_auth):
                expire_in_days = (
                    _get_time_until_expiry(new_auth["expiresAt"]) / SECONDS_PER_DAY
                )
                print(
                    f"Access token refreshed successfully,"
                    f" expires in {expire_in_days:.1f} days"
                )
                return new_auth["accessToken"]
            else:
                raise RuntimeError("Failed to update cookies file")

        except Exception as e:
            print(f"ERROR: Access token refresh failed: {e}", file=sys.stderr)
            if time_until_expiry < 0:
                return None

    expire_in_days = time_until_expiry / SECONDS_PER_DAY
    print(
        f"Access token loaded, expires in {expire_in_days:.1f} days",
        file=sys.stderr,
    )

    return auth_data["accessToken"]
