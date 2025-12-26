import os
import shlex
import subprocess
import sys

from mutagen.mp4 import MP4, MP4Cover

CURL_BIN = os.environ.get("CURL_BIN", "curl")
CURL_OPTS = shlex.split(os.environ.get("CURL_OPTS", ""))

MP4_TITLE = "\xa9nam"
MP4_ARTIST = "\xa9ART"
MP4_COMMENT = "\xa9cmt"
MP4_COVERART = "covr"


def _get_remote_file_size(url: str) -> int | None:
    cmd = [CURL_BIN, "-sI", "-L"]
    if CURL_OPTS:
        cmd.extend(CURL_OPTS)
    cmd.append(url)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        for line in result.stdout.split("\n"):
            if line.lower().startswith("content-length:"):
                return int(line.split(":", 1)[1].strip())
    except Exception as e:
        print(f"ERROR: Unable to get remote file size: {e}", file=sys.stderr)
    return None


def _download_preview(url: str, filepath: str) -> bool:
    cmd = [CURL_BIN, "-s", "-L", "-o", filepath]
    if CURL_OPTS:
        cmd.extend(CURL_OPTS)
    cmd.append(url)

    try:
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"ERROR: Unable to download preview: {e}", file=sys.stderr)
        return False


def _embed_metadata(
    media_filepath: str,
    channel_name: str,
    title: str,
    preview_filepath: str | None = None,
    post_url: str | None = None,
) -> None:
    try:
        mp4 = MP4(media_filepath)

        changed = False
        existing_title = (mp4.get(MP4_TITLE) or [None])[0]
        if existing_title != title:
            mp4[MP4_TITLE] = title
            changed = True

        existing_artist = (mp4.get(MP4_ARTIST) or [None])[0]
        if existing_artist != channel_name:
            mp4[MP4_ARTIST] = channel_name
            changed = True

        if preview_filepath and os.path.exists(preview_filepath):
            with open(preview_filepath, "rb") as f:
                cover_data = f.read()
                existing_cover = (mp4.get(MP4_COVERART) or [None])[0]
                if existing_cover is None or bytes(existing_cover) != cover_data:
                    mp4[MP4_COVERART] = [MP4Cover(cover_data)]
                    changed = True

        if post_url:
            existing_comment = (mp4.get(MP4_COMMENT) or [None])[0]
            if existing_comment != post_url:
                mp4[MP4_COMMENT] = post_url
                changed = True

        if changed:
            mp4.save()
        else:
            print(f"Metadata already up to date: {os.path.basename(media_filepath)}")
    except Exception as e:
        print(
            f"WARNING: Failed to set metadata: {e}",
            file=sys.stderr,
        )


def download_and_embed_metadata(
    media_filepath: str,
    channel_name: str,
    title: str,
    preview_url: str | None = None,
    post_url: str | None = None,
):
    preview_path = None
    if preview_url:
        # not sure how fair is to assume preview is always jpg
        preview_path = media_filepath + ".preview.jpg"
        if not _download_preview(preview_url, preview_path):
            preview_path = None

    result = _embed_metadata(
        media_filepath, channel_name, title, preview_path, post_url
    )

    if preview_path and os.path.exists(preview_path):
        os.remove(preview_path)

    return result


def download_file(
    filepath: str,
    url: str,
    show_progress: bool = True,
) -> bool:
    part_filepath = filepath + ".part"
    cmd = [CURL_BIN, "-L"]

    if os.path.exists(filepath):
        print(
            f"WARNING: {filepath} already exists, removing",
            file=sys.stderr,
        )
        os.remove(filepath)

    if os.path.exists(part_filepath):
        local_size = os.path.getsize(part_filepath)
        remote_size = _get_remote_file_size(url)

        if remote_size and local_size > remote_size:
            print(
                f"WARNING: Corrupted {part_filepath} "
                f"({local_size} > {remote_size} bytes), removing",
                file=sys.stderr,
            )
            os.remove(part_filepath)
        elif remote_size and local_size == remote_size:
            os.rename(part_filepath, filepath)
            return True
        else:
            cmd.extend(["-C", "-"])

    cmd.extend(["-o", part_filepath])

    if CURL_OPTS:
        cmd.extend(CURL_OPTS)

    if show_progress and sys.stdout.isatty():
        cmd.append("--progress-bar")
    else:
        cmd.append("-s")

    cmd.append(url)

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=not sys.stdout.isatty(),
        )

        os.rename(part_filepath, filepath)

        return True
    except subprocess.CalledProcessError as e:
        print(
            f"ERROR: Download failed {filepath} "
            f"({CURL_BIN} exit {e.returncode}): {e.stderr}",
            file=sys.stderr,
        )
        return False
