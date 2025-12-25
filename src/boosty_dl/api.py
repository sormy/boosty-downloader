import json
import os
import shlex
import subprocess
import sys
import time
import urllib.parse
from typing import TypedDict, cast

from . import auth


QUALITIES = [
    "tiny",
    "lowest",
    "low",
    "medium",
    "high",
    "full_hd",
    "quad_hd",
    "ultra_hd",
]


class PlayerUrl(TypedDict):
    type: str
    url: str


class PostItem(TypedDict):
    type: str
    complete: bool
    status: str
    id: str
    title: str
    playerUrls: list[PlayerUrl]
    preview: str | None
    defaultPreview: str | None


class Post(TypedDict):
    id: str
    title: str
    createdAt: float
    hasAccess: bool
    data: list[PostItem]


BOOSTY_API_URL = "https://api.boosty.to"

DEFAULT_LIMIT = 25

CURL_BIN = os.environ.get("CURL_BIN", "curl")
CURL_OPTS = shlex.split(os.environ.get("CURL_OPTS", ""))
CURL_DEBUG = os.environ.get("CURL_DEBUG", "0") == "1"


def _http_request(
    url: str,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    data: dict[str, str] | None = None,
) -> dict:
    cmd = [CURL_BIN, "-s", "-X", method]

    if CURL_OPTS:
        cmd.extend(CURL_OPTS)

    if headers:
        for key, value in headers.items():
            cmd.extend(["-H", f"{key}: {value}"])

    if data:
        form_string = "&".join(
            f"{k}={urllib.parse.quote(str(v))}" for k, v in data.items()
        )
        cmd.extend(["-d", form_string])

    cmd.append(url)

    if CURL_DEBUG:
        print(f"DEBUG: curl command: {' '.join(cmd)}", file=sys.stderr)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)

        if CURL_DEBUG:
            print(f"DEBUG: curl stdout: {result.stdout}", file=sys.stderr)

        response = json.loads(result.stdout)

        if type(response) is not dict:
            raise RuntimeError("Invalid API response format")

        if "error" in response:
            error_code = response.get("error", "unknown")
            error_msg = response.get("error_description", "no details")
            raise RuntimeError(f"API error: {error_code} ({error_msg})")

        return response

    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"{CURL_BIN} failed (exit {e.returncode}): {e.stderr}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON parse error: {e}")


def refresh_token(refresh_token: str, client_id: str) -> auth.AuthData:
    response = _http_request(
        f"{BOOSTY_API_URL}/oauth/token/",
        "POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "grant_type": "refresh_token",
            "device_os": "web",
            "device_id": client_id,
            "refresh_token": refresh_token,
        },
    )

    if (
        "access_token" not in response
        or "refresh_token" not in response
        or "expires_in" not in response
    ):
        raise RuntimeError("Invalid token refresh response")

    return auth.AuthData(
        accessToken=response["access_token"],
        refreshToken=response["refresh_token"],
        expiresAt=int(time.time() * 1000) + response["expires_in"] * 1000,
        clientId=client_id,
    )


def get_post(
    channel: str,
    post_id: str,
    access_token: str | None = None,
) -> Post:
    headers: dict[str, str] = {}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"

    return cast(
        Post,
        _http_request(
            f"{BOOSTY_API_URL}/v1/blog/{channel}/post/{post_id}",
            "GET",
            headers=headers if headers else None,
        ),
    )


def list_posts(
    channel: str,
    access_token: str | None,
    days_back: int | None = None,
) -> list[Post]:
    cutoff_timestamp = (
        time.time() - (days_back * 24 * 60 * 60) if days_back is not None else None
    )

    posts: list[Post] = []
    offset = None

    while True:
        params = f"limit={DEFAULT_LIMIT}"
        if offset:
            params += f"&offset={offset}"

        headers: dict[str, str] = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        data = _http_request(
            f"{BOOSTY_API_URL}/v1/blog/{channel}/post/?{params}",
            "GET",
            headers=headers if headers else None,
        )

        if not data:
            break

        post_list = data.get("data", [])

        for post in post_list:
            created_at = post.get("createdAt")

            if cutoff_timestamp and created_at and created_at < cutoff_timestamp:
                return posts

            posts.append(cast(Post, post))

        extra = data.get("extra", {})
        new_offset = extra.get("offset")
        is_last = extra.get("isLast", False)

        if not new_offset or is_last:
            break

        offset = new_offset

    return posts
