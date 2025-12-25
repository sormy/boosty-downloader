import json
import sys
import urllib.parse
import urllib.request

DEFAULT_TIMEOUT = 30


def _resolve_jellyfin_item_id(
    url: str, token: str, name_or_id: str, timeout: int = DEFAULT_TIMEOUT
) -> str | None:
    params = urllib.parse.urlencode(
        {
            "Recursive": "True",
            "IncludeItemTypes": "CollectionFolder",
        }
    )
    req = urllib.request.Request(
        f"{url}/Items?{params}",
        headers={"Authorization": f'MediaBrowser Token="{token}"'},
    )
    response = urllib.request.urlopen(req, timeout=timeout)
    data = json.loads(response.read())

    for item in data.get("Items", []):
        if item.get("Id") == name_or_id or item.get("Name") == name_or_id:
            return item.get("Id")

    return None


def refresh_jellyfin_library(
    url: str, token: str, item: str, timeout: int = DEFAULT_TIMEOUT
) -> bool:
    print(f"Requesting Jellyfin library item '{item}' refresh")
    try:
        item_id = _resolve_jellyfin_item_id(url, token, item, timeout)
        if not item_id:
            raise RuntimeError(f"Could not resolve Jellyfin item '{item}' ID")
        req = urllib.request.Request(
            f"{url}/Items/{item_id}/Refresh",
            data=urllib.parse.urlencode(
                {
                    "Recursive": "true",
                    "MetadataRefreshMode": "Default",
                    "ImageRefreshMode": "Default",
                    "ReplaceAllImages": "false",
                    "ReplaceAllMetadata": "false",
                }
            ).encode(),
            headers={"Authorization": f'MediaBrowser Token="{token}"'},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=timeout)
        return True
    except Exception as e:
        print(f"WARNING: Jellyfin item '{item}' refresh failed: {e}", file=sys.stderr)
        return False
