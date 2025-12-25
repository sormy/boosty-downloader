import os
import shlex
import subprocess
import sys

CURL_BIN = os.environ.get("CURL_BIN", "curl")
CURL_OPTS = shlex.split(os.environ.get("CURL_OPTS", ""))
EXIFTOOL_BIN = os.environ.get("EXIFTOOL_BIN", "exiftool")


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
    cmd = [EXIFTOOL_BIN, f"-Title={title}", f"-Artist={channel_name}"]

    if preview_filepath:
        cmd.append(f"-CoverArt<={preview_filepath}")
    if post_url:
        cmd.append(f"-Comment={post_url}")

    cmd.extend(["-overwrite_original", "-q", media_filepath])

    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as e:
        print(
            f"WARNING: exiftool failed to set metadata: {e.stderr}",
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
