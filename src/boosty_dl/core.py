from functools import lru_cache
import os
import re
from datetime import datetime

from . import api, media, util


def _sanitize_title(title: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", title).strip()


def _generate_name(created_at: datetime, index: int, title: str) -> str:
    dt = created_at
    if index == 0:
        episode = f"s{dt.year}e{dt.month:02d}{dt.day:02d}"
    else:
        episode = f"s{dt.year}e{dt.month:02d}{dt.day:02d}{index:02d}"
    safe_title = _sanitize_title(title)
    return f"{episode} - {safe_title}"


def _generate_filename(
    created_at: datetime, index: int, title: str, video_id: str
) -> str:
    name = _generate_name(created_at, index, title)
    return f"{name} [{video_id}].mp4"


def _generate_dirname(
    output_dir: str,
    channel_name: str,
    created_at: datetime,
    use_channel_dir: bool,
    use_season_dir: bool,
) -> str:
    directory = output_dir

    if use_channel_dir:
        directory = os.path.join(directory, channel_name)
    if use_season_dir:
        directory = os.path.join(directory, f"Season {created_at.year}")

    return directory


@lru_cache(maxsize=1)
def _list_videos_in_directory(directory: str) -> list[str]:
    videos = []
    if not os.path.exists(directory):
        return videos

    for filename in os.listdir(directory):
        if filename.endswith(".mp4"):
            videos.append(filename)

    return videos


def _find_local_filename(
    directory: str, video_id: str, post_id: str, is_single_video: bool
) -> str | None:
    for filename in _list_videos_in_directory(directory):
        if f"[{video_id}]" in filename:
            return filename

        if is_single_video and f"[{post_id}]" in filename:
            return filename

    return None


def _count_valid_videos(post: api.Post) -> int:
    return sum(
        1
        for v in post.get("data", [])
        if v.get("type") == "ok_video" and v.get("complete") and v.get("status") == "ok"
    )


def _select_best_url(
    player_urls: list[api.PlayerUrl] | None, max_quality: str | None
) -> str | None:
    if not player_urls:
        return None

    available = [
        (item["type"], item["url"])
        for item in player_urls
        if item.get("type") in api.QUALITIES and item.get("url")
    ]

    if not available:
        return None

    available.sort(key=lambda x: api.QUALITIES.index(x[0]))

    if max_quality:
        max_idx = api.QUALITIES.index(max_quality)
        for quality, url in reversed(available):
            if api.QUALITIES.index(quality) <= max_idx:
                return url
        return None

    return available[-1][1]


def _download_post_videos(
    channel_name: str,
    output_dir: str,
    post: api.Post,
    max_quality: str | None = None,
    use_season_dir: bool = True,
    use_channel_dir: bool = True,
    update_metadata: bool = False,
    start_video_index: int = 0,
) -> list[str]:
    post_id = post["id"]
    post_title = post["title"]
    created_at = datetime.fromtimestamp(post["createdAt"])
    post_url = f"https://boosty.to/{channel_name}/posts/{post_id}"

    post_name = _generate_name(created_at, 0, post_title or post_id)
    downloaded_files = []

    if not post.get("hasAccess"):
        print(f"Skipping (no access): {post_name}")
        return downloaded_files

    video_count = _count_valid_videos(post)
    if video_count == 0:
        print(f"Skipping (no videos): {post_name}")
        return downloaded_files

    is_single_video = video_count == 1

    video_index = start_video_index

    for item in post.get("data", []):
        if item.get("type") != "ok_video":
            continue

        if not item.get("complete") or item.get("status") != "ok":
            continue

        video_index += 1
        video_id = item["id"]
        video_title = item["title"] or post_title or "untitled"

        video_name = _generate_name(created_at, video_index, video_title or video_id)

        preview_url = item.get("preview") or item.get("defaultPreview")

        url = _select_best_url(item.get("playerUrls"), max_quality)
        if not url:
            print(f"Skipping (no media): {video_name}")
            continue

        directory = _generate_dirname(
            output_dir,
            channel_name,
            created_at,
            use_channel_dir,
            use_season_dir,
        )

        local_filename = _find_local_filename(
            directory, video_id, post_id, is_single_video
        )

        if local_filename:
            filepath = os.path.join(directory, local_filename)
            if update_metadata:
                print(f"Updating metadata: {local_filename}")
                media.download_and_embed_metadata(
                    filepath, channel_name, video_title, preview_url, post_url
                )
            else:
                print(f"Skipping (exists): {local_filename}")
            continue

        if update_metadata:
            continue

        os.makedirs(directory, exist_ok=True)

        filename = _generate_filename(created_at, video_index, video_title, video_id)
        filepath = os.path.join(directory, filename)

        print(f"Downloading: {filename}")
        if media.download_file(filepath, url):
            print(f"Embedding metadata: {filename}")
            media.download_and_embed_metadata(
                filepath, channel_name, video_title, preview_url, post_url
            )
            downloaded_files.append(filename)

    return downloaded_files


def download_post_videos(
    channel_name: str,
    post_id: str,
    output_dir: str,
    access_token: str | None = None,
    max_quality: str | None = None,
    use_season_dir: bool = True,
    use_channel_dir: bool = True,
    update_metadata: bool = False,
) -> list[str]:
    print(f"Fetching post {post_id} for channel {channel_name}...")
    post = api.get_post(channel_name, post_id, access_token)

    return _download_post_videos(
        channel_name,
        output_dir,
        post,
        max_quality,
        use_season_dir,
        use_channel_dir,
        update_metadata,
        0,
    )


def download_channel_videos(
    channel_name: str,
    output_dir: str,
    access_token: str | None = None,
    max_quality: str | None = None,
    days_back: int | None = None,
    use_season_dir: bool = True,
    use_channel_dir: bool = True,
    update_metadata: bool = False,
) -> list[str]:
    suffix = f" (last {days_back} days)" if days_back is not None else ""
    print(f"Fetching posts for channel {channel_name}{suffix}...")
    posts = api.list_posts(channel_name, access_token, days_back)
    print(f"Found {len(posts)} posts for channel {channel_name}{suffix}")

    all_downloaded = []
    last_date = None
    video_index = 0

    for post in posts:
        created_at = datetime.fromtimestamp(post["createdAt"])
        current_date = created_at.date()

        if last_date != current_date:
            video_index = 0
            last_date = current_date

        downloaded = _download_post_videos(
            channel_name,
            output_dir,
            post,
            max_quality,
            use_season_dir,
            use_channel_dir,
            update_metadata,
            video_index,
        )
        all_downloaded.extend(downloaded)

        video_index += _count_valid_videos(post)

    return all_downloaded


def download_links(
    links: list[str],
    output_dir: str,
    access_token: str | None = None,
    max_quality: str | None = None,
    days_back: int | None = None,
    use_season_dir: bool = True,
    use_channel_dir: bool = True,
    update_metadata: bool = False,
) -> list[str]:
    all_downloaded = []
    for link in links:
        channel_name, post_id = util.parse_name_or_url(link)

        if post_id:
            downloaded = download_post_videos(
                channel_name=channel_name,
                post_id=post_id,
                output_dir=output_dir,
                access_token=access_token,
                max_quality=max_quality,
                use_season_dir=use_season_dir,
                use_channel_dir=use_channel_dir,
                update_metadata=update_metadata,
            )
        else:
            downloaded = download_channel_videos(
                channel_name=channel_name,
                output_dir=output_dir,
                access_token=access_token,
                max_quality=max_quality,
                days_back=days_back,
                use_season_dir=use_season_dir,
                use_channel_dir=use_channel_dir,
                update_metadata=update_metadata,
            )

        all_downloaded.extend(downloaded)

    return all_downloaded
