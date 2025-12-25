import json
import sys
import urllib.request

DEFAULT_TIMEOUT = 30


def _resolve_plex_section_id(
    url: str, token: str, name_or_key: str, timeout: int = DEFAULT_TIMEOUT
) -> str | None:
    req = urllib.request.Request(
        f"{url}/library/sections",
        headers={
            "X-Plex-Token": token,
            "Accept": "application/json",
        },
    )
    response = urllib.request.urlopen(req, timeout=timeout)
    data = json.loads(response.read())

    for directory in data.get("MediaContainer", {}).get("Directory", []):
        if directory.get("key") == name_or_key or directory.get("title") == name_or_key:
            return directory.get("key")

    return None


def refresh_plex_library(
    url: str, token: str, section: str, timeout: int = DEFAULT_TIMEOUT
) -> bool:
    print(f"Requesting Plex library section '{section}' refresh")
    try:
        section_id = _resolve_plex_section_id(url, token, section, timeout)
        if not section_id:
            raise RuntimeError(f"Could not resolve Plex section '{section}' ID")
        endpoint = f"{url}/library/sections/{section_id}/refresh"
        req = urllib.request.Request(endpoint, headers={"X-Plex-Token": token})
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception as e:
        print(f"WARNING: Plex section '{section}' refresh failed: {e}", file=sys.stderr)
        return False
