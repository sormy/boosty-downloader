def parse_name_or_url(name_or_url: str) -> tuple[str, str | None]:
    if not name_or_url.startswith("https://"):
        return (name_or_url, None)

    if not name_or_url.startswith("https://boosty.to/"):
        raise ValueError(f"Invalid Boosty URL: {name_or_url}")

    url = name_or_url.split("?")[0].rstrip("/")
    parts = url.replace("https://boosty.to/", "").split("/")

    channel_name = parts[0]
    post_id = parts[2] if len(parts) >= 3 and parts[1] == "posts" else None

    return (channel_name, post_id)
