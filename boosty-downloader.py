#!/usr/bin/env python3
"""Boosty downloader - simple video list tool"""

import argparse
import atexit
import fcntl
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
from collections import defaultdict
from datetime import datetime


class BoostyDownloader:
    QUALITY_ORDER = [
        "tiny",
        "lowest",
        "low",
        "medium",
        "high",
        "full_hd",
        "quad_hd",
        "ultra_hd",
    ]

    def __init__(
        self,
        cookies_file,
        interface=None,
        max_quality=None,
        debug=False,
        download=False,
        target_dir=None,
        use_season_dir=False,
        use_channel_dir=False,
        days_back=None,
        plex_url=None,
        plex_token=None,
        plex_section=None,
        jellyfin_url=None,
        jellyfin_token=None,
        jellyfin_item=None,
        notify_email=None,
    ):
        self.cookies_file = cookies_file
        self.interface = interface
        self.max_quality = max_quality
        self.debug = debug
        self.download = download
        self.target_dir = target_dir
        self.use_season_dir = use_season_dir
        self.use_channel_dir = use_channel_dir
        self.days_back = days_back
        self.plex_url = plex_url
        self.plex_token = plex_token
        self.plex_section = plex_section
        self.jellyfin_url = jellyfin_url
        self.jellyfin_token = jellyfin_token
        self.jellyfin_item = jellyfin_item
        self.notify_email = notify_email
        self.downloaded_files = []  # Track downloaded files for notification
        self.auth_data = None
        self.auth_token = self._get_auth_token()

    def _get_auth_token(self):
        """Extract Bearer token from auth cookie and check expiration"""
        try:
            with open(self.cookies_file) as f:
                for line in f:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.strip().split("\t")
                    if (
                        len(parts) >= 7
                        and parts[0] == ".boosty.to"
                        and parts[5] == "auth"
                    ):
                        auth_cookie_value = parts[6]
                        self.auth_data = json.loads(urllib.parse.unquote(auth_cookie_value))

                        # Check if token is expired or expiring soon
                        expires_at = self.auth_data.get("expiresAt", 0) / 1000  # Convert to seconds
                        time_until_expiry = expires_at - time.time()

                        if self.debug:
                            from datetime import datetime
                            exp_date = datetime.fromtimestamp(expires_at)
                            print(f"DEBUG: Token expires at {exp_date} ({time_until_expiry/86400:.1f} days)", file=sys.stderr)

                        # Auto-refresh if token is expired or expiring soon
                        if time_until_expiry < 86400:  # Less than 1 day
                            if time_until_expiry < 0:
                                print("WARNING: Access token has expired! Attempting to refresh...", file=sys.stderr)
                            else:
                                print(f"WARNING: Access token expires in {time_until_expiry/3600:.1f} hours. Attempting to refresh...", file=sys.stderr)

                            if self._refresh_token():
                                print("SUCCESS: Token refreshed successfully!", file=sys.stderr)
                            else:
                                print("ERROR: Failed to refresh token. Please update your cookies manually.", file=sys.stderr)
                                if time_until_expiry < 0:
                                    sys.exit(1)

                        return self.auth_data.get("accessToken")
        except (FileNotFoundError, json.JSONDecodeError, KeyError, IndexError) as e:
            print(f"Error: Failed to extract auth token: {e}", file=sys.stderr)
            sys.exit(1)
        return None

    def _get_device_id(self):
        """Extract device_id (_clientId) from cookies file"""
        try:
            with open(self.cookies_file) as f:
                for line in f:
                    if line.startswith("#") or not line.strip():
                        continue
                    parts = line.strip().split("\t")
                    if (
                        len(parts) >= 7
                        and parts[0] == ".boosty.to"
                        and parts[5] == "_clientId"
                    ):
                        return parts[6]
        except Exception:
            pass
        return None

    def _refresh_token(self):
        """Refresh access token using refresh token"""
        if not self.auth_data:
            return False

        refresh_token = self.auth_data.get("refreshToken")
        if not refresh_token:
            print("ERROR: No refresh token available", file=sys.stderr)
            return False

        device_id = self._get_device_id()
        if not device_id:
            print("WARNING: No device_id found in cookies, using default", file=sys.stderr)
            device_id = "web-client"

        # Prepare form data
        form_data = {
            "device_id": device_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "device_os": "web",
        }

        # Build curl command for form-urlencoded POST
        cmd = ["curl", "-s", "-X", "POST"]
        cmd.extend(["-H", "Content-Type: application/x-www-form-urlencoded"])

        if self.interface:
            cmd.extend(["--interface", self.interface])

        # Add form data (URL-encode values)
        form_string = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in form_data.items())
        cmd.extend(["-d", form_string])

        cmd.append("https://api.boosty.to/oauth/token/")

        if self.debug:
            print(f"DEBUG: Refresh request data: {form_data}", file=sys.stderr)
            print(f"DEBUG: Refresh curl command: {' '.join(cmd)}", file=sys.stderr)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            response = json.loads(result.stdout)

            if self.debug:
                print(f"DEBUG: Refresh response: {response}", file=sys.stderr)

            # Update auth data with new tokens
            if "access_token" in response and "refresh_token" in response:
                self.auth_data["accessToken"] = response["access_token"]
                self.auth_data["refreshToken"] = response["refresh_token"]
                self.auth_data["expiresAt"] = response.get("expires_in", 0) * 1000 + int(time.time() * 1000)
                self.auth_token = response["access_token"]

                # Update cookies file
                self._update_cookies_file()
                return True
            else:
                print(f"ERROR: Token refresh failed: {response}", file=sys.stderr)
                return False
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            print(f"ERROR: Token refresh request failed: {e}", file=sys.stderr)
            return False

    def _update_cookies_file(self):
        """Update the auth cookie in the cookies file with new token data"""
        try:
            # Read all lines
            with open(self.cookies_file, 'r') as f:
                lines = f.readlines()

            # Find and update the auth cookie line
            new_auth_value = urllib.parse.quote(json.dumps(self.auth_data))
            updated = False

            for i, line in enumerate(lines):
                if not line.startswith("#") and line.strip():
                    parts = line.strip().split("\t")
                    if (
                        len(parts) >= 7
                        and parts[0] == ".boosty.to"
                        and parts[5] == "auth"
                    ):
                        parts[6] = new_auth_value
                        lines[i] = "\t".join(parts) + "\n"
                        updated = True
                        break

            if updated:
                # Write back to file
                with open(self.cookies_file, 'w') as f:
                    f.writelines(lines)
                if self.debug:
                    print("DEBUG: Cookies file updated with new tokens", file=sys.stderr)
            else:
                print("WARNING: Could not find auth cookie to update", file=sys.stderr)

        except Exception as e:
            print(f"ERROR: Failed to update cookies file: {e}", file=sys.stderr)

    def _refresh_plex_library(self):
        """Refresh Plex library section (non-fatal if fails)"""
        if not self.plex_url or not self.plex_token or not self.plex_section:
            return

        try:
            url = f"{self.plex_url}/library/sections/{self.plex_section}/refresh"
            cmd = ["curl", "-sS", "-L", "-X", "GET"]
            cmd.extend(["-H", f"X-Plex-Token: {self.plex_token}"])
            cmd.append(url)

            if self.debug:
                print(f"DEBUG: Refreshing Plex library section {self.plex_section}", file=sys.stderr)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                print(f"Plex library section {self.plex_section} refresh triggered successfully", file=sys.stderr)
            else:
                print(f"WARNING: Plex refresh failed (exit code {result.returncode})", file=sys.stderr)
                if self.debug and result.stderr:
                    print(f"DEBUG: Plex error: {result.stderr}", file=sys.stderr)

        except subprocess.TimeoutExpired:
            print("WARNING: Plex refresh timed out after 30 seconds", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: Plex refresh failed: {e}", file=sys.stderr)

    def _refresh_jellyfin_library(self):
        """Refresh Jellyfin library item (non-fatal if fails)"""
        if not self.jellyfin_url or not self.jellyfin_token or not self.jellyfin_item:
            return

        try:
            url = f"{self.jellyfin_url}/Items/{self.jellyfin_item}/Refresh"
            cmd = ["curl", "-sS", "-L", "-X", "POST"]
            cmd.extend(["-H", f"Authorization: MediaBrowser Token=\"{self.jellyfin_token}\""])

            # Add POST data parameters
            cmd.extend(["-d", "Recursive=true"])
            cmd.extend(["-d", "MetadataRefreshMode=Default"])
            cmd.extend(["-d", "ImageRefreshMode=Default"])
            cmd.extend(["-d", "ReplaceAllImages=false"])
            cmd.extend(["-d", "ReplaceAllMetadata=false"])

            cmd.append(url)

            if self.debug:
                print(f"DEBUG: Refreshing Jellyfin library item {self.jellyfin_item}", file=sys.stderr)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                print(f"Jellyfin library item {self.jellyfin_item} refresh triggered successfully", file=sys.stderr)
            else:
                print(f"WARNING: Jellyfin refresh failed (exit code {result.returncode})", file=sys.stderr)
                if self.debug and result.stderr:
                    print(f"DEBUG: Jellyfin error: {result.stderr}", file=sys.stderr)

        except subprocess.TimeoutExpired:
            print("WARNING: Jellyfin refresh timed out after 30 seconds", file=sys.stderr)
        except Exception as e:
            print(f"WARNING: Jellyfin refresh failed: {e}", file=sys.stderr)

    def _api_request(self, url):
        """Make API request using curl"""
        cmd = ["curl", "-s"]

        # Use Bearer token for authentication (extracted from cookies file)
        if self.auth_token:
            cmd.extend(["-H", f"Authorization: Bearer {self.auth_token}"])

        if self.interface:
            cmd.extend(["--interface", self.interface])

        cmd.append(url)

        if self.debug:
            print(f"DEBUG: Curl command: {' '.join(cmd)}", file=sys.stderr)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            if self.debug:
                print(
                    f"DEBUG: Curl response: {result.stdout}",
                    file=sys.stderr,
                )

            response = json.loads(result.stdout)

            # Check for API error responses
            if "error" in response:
                error_msg = response.get("error_description", response.get("error", "Unknown error"))
                print(f"ERROR: API request failed: {error_msg}", file=sys.stderr)

                # Provide helpful suggestions based on error type
                if response.get("error") == "unauthorized":
                    print("ERROR: Authorization failed. Possible causes:", file=sys.stderr)
                    print("  1. Access token has expired - the script should have refreshed it automatically", file=sys.stderr)
                    print("  2. Cookies file is invalid or outdated", file=sys.stderr)
                    print("  3. The 'auth' cookie is missing or malformed", file=sys.stderr)
                    print("\nPlease export fresh cookies from your browser and try again.", file=sys.stderr)
                    sys.exit(1)

                return {}

            return response
        except subprocess.CalledProcessError as e:
            print(f"ERROR: API request failed: {e}", file=sys.stderr)
            if self.debug and e.stderr:
                print(f"DEBUG: Curl error: {e.stderr}", file=sys.stderr)
            return {}
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse API response: {e}", file=sys.stderr)
            return {}

    def _get_sorted_urls(self, player_urls):
        """Get all MP4 URLs sorted from worst to best quality"""
        if not player_urls:
            return []

        # Filter only MP4 qualities and those with actual URLs
        available = []
        for item in player_urls:
            quality = item.get("type")
            url = item.get("url", "")
            if quality in self.QUALITY_ORDER and url:
                available.append({"type": quality, "url": url})

        # Sort by quality (worst to best)
        available.sort(key=lambda x: self.QUALITY_ORDER.index(x["type"]))

        return available

    def _generate_filename(self, publish_time, day_index, title, video_id):
        """Generate filename in format: Season YYYY/sYYYYeMMDDXX - title [video_id].mp4"""
        dt = datetime.fromtimestamp(publish_time)
        season = f"Season {dt.year}"
        episode = f"s{dt.year}e{dt.month:02d}{dt.day:02d}{day_index:02d}"

        # Sanitize title for filesystem
        safe_title = re.sub(r'[<>:"/\\|?*]', "", title)
        safe_title = safe_title.strip()

        filename = f"{episode} - {safe_title} [{video_id}].mp4"
        return season, filename

    def _find_existing_file(self, directory, video_id, post_id, is_single_video):
        """Find existing file with given ID and return filepath, or None if not found"""
        if not os.path.exists(directory):
            return None

        # Look for files containing the video_id
        for filename in os.listdir(directory):
            if not filename.endswith(".mp4"):
                continue

            filepath = os.path.join(directory, filename)

            # Check if video_id is in filename
            if f"[{video_id}]" in filename:
                return filepath

            # For single video posts, also check post_id for compatibility
            if is_single_video and f"[{post_id}]" in filename:
                return filepath

        return None

    def _get_remote_file_size(self, url):
        """Get the size of remote file using curl HEAD request"""
        cmd = ["curl", "-sI", "-L"]

        if self.interface:
            cmd.extend(["--interface", self.interface])

        cmd.append(url)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            # Parse Content-Length from headers
            for line in result.stdout.split("\n"):
                if line.lower().startswith("content-length:"):
                    size_str = line.split(":", 1)[1].strip()
                    return int(size_str)
        except (subprocess.CalledProcessError, ValueError):
            pass

        return None

    def _is_file_complete(self, filepath, url):
        """Check if local file is complete by comparing size with remote"""
        if not os.path.exists(filepath):
            return False

        local_size = os.path.getsize(filepath)
        remote_size = self._get_remote_file_size(url)

        if remote_size is None:
            # Can't determine remote size, assume incomplete to be safe
            return False

        return local_size == remote_size

    def _download_file(self, url, filepath, resume=False, title=None, channel=None):
        """Download file using curl with progress if terminal is interactive

        Args:
            url: URL to download from
            filepath: Local path to save file (without .part extension)
            resume: If True, resume partial download if .part file exists
            title: Optional title to add as metadata
            channel: Optional channel name to add as artist metadata
        """
        part_filepath = filepath + ".part"
        cmd = ["curl", "-L"]

        # Check if final file already exists (complete download)
        if os.path.exists(filepath) and not resume:
            # File already exists and complete
            return True

        # Enable resume if .part file exists
        if os.path.exists(part_filepath):
            # Check if partial file is larger than remote file (corrupted)
            local_size = os.path.getsize(part_filepath)
            remote_size = self._get_remote_file_size(url)

            if remote_size and local_size > remote_size:
                print(f"  WARNING: Partial file ({local_size} bytes) is larger than remote ({remote_size} bytes). Deleting corrupted file.", file=sys.stderr)
                os.remove(part_filepath)
            elif remote_size and local_size == remote_size:
                # Part file is complete, just rename it
                os.rename(part_filepath, filepath)
                return True
            else:
                # Resume from where we left off
                cmd.extend(["-C", "-"])

        # Download to .part file
        cmd.extend(["-o", part_filepath])

        if self.interface:
            cmd.extend(["--interface", self.interface])

        # Add progress bar if stdout is a terminal (interactive)
        if sys.stdout.isatty():
            cmd.append("--progress-bar")
        else:
            cmd.append("-s")

        cmd.append(url)

        try:
            # Don't capture output if we want to show progress
            if sys.stdout.isatty():
                subprocess.run(cmd, check=True)
            else:
                result = subprocess.run(cmd, check=True, capture_output=True)

            # Download successful, rename .part to final filename
            os.rename(part_filepath, filepath)
            return True
        except subprocess.CalledProcessError as e:
            print(f"ERROR: Download failed with exit code {e.returncode}: {filepath}", file=sys.stderr)

            # Provide specific error messages based on curl exit codes
            if e.returncode == 6:
                print("  Curl error 6: Could not resolve host (DNS issue)", file=sys.stderr)
            elif e.returncode == 7:
                print("  Curl error 7: Failed to connect to host", file=sys.stderr)
            elif e.returncode == 8:
                print("  Curl error 8: Server returned error or weird server reply", file=sys.stderr)
                if self.interface:
                    print(f"  Note: Using network interface '{self.interface}' - verify it's correct and has connectivity", file=sys.stderr)
            elif e.returncode == 28:
                print("  Curl error 28: Operation timeout", file=sys.stderr)
            elif e.returncode == 35:
                print("  Curl error 35: SSL connection error", file=sys.stderr)

            if self.debug:
                print(f"DEBUG: Failed command: {' '.join(cmd)}", file=sys.stderr)
                if hasattr(e, 'stderr') and e.stderr:
                    print(f"DEBUG: Curl stderr: {e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr}", file=sys.stderr)

            # Keep .part file - it can be resumed later
            return False

    def list_posts(self, channel):
        """List all posts from a channel"""
        # Extract channel name from URL if needed
        if channel.startswith("http"):
            channel = channel.rstrip("/").split("/")[-1]

        offset = None
        posts = []

        # Calculate cutoff timestamp if days_back is specified
        cutoff_timestamp = None
        if self.days_back is not None:
            cutoff_timestamp = time.time() - (self.days_back * 24 * 60 * 60)
            if self.debug:
                print(
                    f"DEBUG: Looking back {self.days_back} days (cutoff: {datetime.fromtimestamp(cutoff_timestamp)})",
                    file=sys.stderr,
                )

        # Download statistics
        stats = {
            "new": 0,
            "skipped_existing": 0,
            "skipped_no_access": 0,
            "skipped_unavailable": 0,
            "skipped_non_video": 0,
            "skipped_old": 0,
            "downloaded": 0,
            "failed": 0,
        }

        should_stop = False

        while True:
            params = "limit=25"
            if offset:
                params += f"&offset={offset}"

            url = f"https://api.boosty.to/v1/blog/{channel}/post/?{params}"
            data = self._api_request(url)

            if not data:
                break

            post_list = data.get("data", [])
            if self.debug:
                print(
                    f"DEBUG: Fetched {len(post_list)} posts, offset={offset}",
                    file=sys.stderr,
                )

            # Group posts by date for episode numbering
            posts_by_date = defaultdict(list)
            for post in post_list:
                created_at = post.get("createdAt")
                if created_at:
                    dt = datetime.fromtimestamp(created_at)
                    date_key = dt.strftime("%Y%m%d")
                    posts_by_date[date_key].append(post)

            # Process posts
            for post in post_list:
                post_id = post.get("id")
                title = post.get("title", "Untitled")
                created_at = post.get("createdAt")
                has_access = post.get("hasAccess", False)

                # Check if post is too old
                if cutoff_timestamp is not None and created_at and created_at < cutoff_timestamp:
                    if self.debug:
                        print(
                            f"DEBUG: Post {post_id} is older than {self.days_back} days, stopping pagination",
                            file=sys.stderr,
                        )
                    should_stop = True
                    break

                # Get video data
                video_data = post.get("data", [])

                if not video_data:
                    # No video content
                    stats["skipped_non_video"] += 1
                    continue

                # Count videos in this post
                video_count = sum(1 for v in video_data if v.get("type") == "ok_video")
                is_single_video = video_count == 1

                # Get day index for this post
                dt = datetime.fromtimestamp(created_at)
                date_key = dt.strftime("%Y%m%d")
                day_posts = posts_by_date[date_key]
                day_index = day_posts.index(post) + 1

                # Process all content items in this post
                content_items = []
                video_index_in_post = 0

                for video in video_data:
                    video_type = video.get("type")
                    if video_type != "ok_video":
                        stats["skipped_non_video"] += 1
                        continue

                    video_index_in_post += 1
                    video_id = video.get("id")
                    video_title = video.get("title", "")
                    duration = video.get("duration", 0)
                    complete = video.get("complete", False)
                    status = video.get("status")
                    upload_status = video.get("uploadStatus")

                    # Use video title if available, otherwise use post title
                    display_title = video_title if video_title else title

                    # Determine status string and get URLs
                    if not has_access:
                        status_str = "no access"
                        urls = []
                        stats["skipped_no_access"] += 1
                    elif not complete or status != "ok" or upload_status != "ok":
                        status_str = "unavailable"
                        urls = []
                        stats["skipped_unavailable"] += 1
                    else:
                        status_str = "ok"
                        # Get all URLs sorted by quality
                        player_urls = video.get("playerUrls", [])
                        urls = self._get_sorted_urls(player_urls)

                    content_items.append(
                        {
                            "id": video_id,
                            "type": video_type,
                            "title": video_title,
                            "status": status_str,
                            "duration": duration,
                            "urls": urls,
                        }
                    )

                    # Download if enabled
                    if (
                        self.download
                        and self.target_dir
                        and status_str == "ok"
                        and urls
                    ):
                        # Adjust day_index for multiple videos in same post
                        adjusted_day_index = (
                            day_index
                            if is_single_video
                            else day_index * 10 + video_index_in_post
                        )

                        season, filename = self._generate_filename(
                            created_at, adjusted_day_index, display_title, video_id
                        )

                        # Build directory path based on options
                        download_dir = self.target_dir
                        display_path = ""

                        if self.use_channel_dir:
                            download_dir = os.path.join(download_dir, channel)
                            display_path = f"{channel}/"

                        if self.use_season_dir:
                            download_dir = os.path.join(download_dir, season)
                            display_path += f"{season}/"

                        display_path += filename

                        # Get best quality URL (or max_quality if specified)
                        selected_url = None
                        if self.max_quality:
                            # Find the best quality up to max_quality
                            max_idx = self.QUALITY_ORDER.index(self.max_quality)
                            for url_info in reversed(urls):
                                if (
                                    self.QUALITY_ORDER.index(url_info["type"])
                                    <= max_idx
                                ):
                                    selected_url = url_info["url"]
                                    break
                        else:
                            # Get the best quality available
                            selected_url = urls[-1]["url"]

                        if not selected_url:
                            continue

                        # Create directory if needed
                        os.makedirs(download_dir, exist_ok=True)

                        # Check if complete file exists
                        existing_file = self._find_existing_file(
                            download_dir, video_id, post_id, is_single_video
                        )

                        if existing_file:
                            # Complete file exists, skip it
                            print(f"[EXISTS] {display_path}", flush=True)
                            stats["skipped_existing"] += 1
                        else:
                            # File doesn't exist, check for .part file or start new download
                            filepath = os.path.join(download_dir, filename)
                            part_file = filepath + ".part"

                            # Check if .part file is complete
                            if os.path.exists(part_file):
                                if self._is_file_complete(part_file, selected_url):
                                    # Part file is complete, just rename it
                                    os.rename(part_file, filepath)
                                    print(f"[EXISTS] {display_path} (renamed from .part)", flush=True)
                                    stats["skipped_existing"] += 1
                                    continue
                                else:
                                    print(f"[RESUME] {display_path}", flush=True)
                            else:
                                print(f"[NEW] {display_path}", flush=True)

                            stats["new"] += 1

                            if self._download_file(selected_url, filepath, resume=False):
                                print(f"[DOWNLOADED] {display_path}", flush=True)
                                stats["downloaded"] += 1
                                self.downloaded_files.append(display_path)
                            else:
                                print(f"[FAILED] {display_path}", flush=True)
                                stats["failed"] += 1

                if content_items:
                    posts.append(
                        {
                            "created_at": created_at,
                            "post_id": post_id,
                            "post_title": title,
                            "has_access": has_access,
                            "content": content_items,
                        }
                    )

            # Stop if we've reached the date cutoff
            if should_stop:
                if self.debug:
                    print("DEBUG: Stopping pagination due to date cutoff", file=sys.stderr)
                break

            # Check for next page
            extra = data.get("extra", {})
            new_offset = extra.get("offset")
            is_last = extra.get("isLast", False)
            if self.debug:
                print(
                    f"DEBUG: next offset={new_offset}, isLast={is_last}",
                    file=sys.stderr,
                )

            if not new_offset or is_last:
                break

            offset = new_offset

        # Sort by created time (newest first)
        posts.sort(key=lambda p: p["created_at"] or 0, reverse=True)

        if self.debug:
            print(f"DEBUG: Total posts with videos: {len(posts)}", file=sys.stderr)

        # Return stats/posts based on mode
        if self.download:
            return stats
        else:
            return posts


def acquire_lock(lock_file):
    """Acquire an exclusive lock on the lock file.

    Returns the file descriptor if lock is acquired, None if already locked.
    """
    try:
        # Open/create lock file
        fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)

        # Try to acquire exclusive lock (non-blocking)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Write PID to lock file
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())

            # Register cleanup on exit
            def cleanup():
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    os.remove(lock_file)
                except:
                    pass

            atexit.register(cleanup)

            return fd
        except BlockingIOError:
            # Lock is held by another process
            os.close(fd)
            return None
    except Exception as e:
        print(f"Error acquiring lock: {e}", file=sys.stderr)
        return None


def main():
    # Check for environment variable defaults
    env_cookies = os.environ.get("COOKIES_FILE")
    env_output = os.environ.get("TARGET_PATH")
    env_channels = os.environ.get("CHANNELS", "").split()
    env_notify_email = os.environ.get("NOTIFY_EMAIL")

    parser = argparse.ArgumentParser(
        description="List or download videos from Boosty channel"
    )
    parser.add_argument(
        "channels",
        nargs='*',  # Changed to '*' to allow env var fallback
        help="One or more channel names or URLs (e.g., 'historipi' or 'https://boosty.to/historipi'). Can be set via CHANNELS env var.",
    )
    parser.add_argument(
        "-c",
        "--cookies",
        default=env_cookies,
        required=not env_cookies,  # Not required if env var is set
        help="Path to cookies file in Netscape format (must include 'auth' and '_clientId' cookies from .boosty.to domain). Can be set via COOKIES_FILE env var.",
    )
    parser.add_argument("-i", "--interface", help="Network interface to use for curl")
    parser.add_argument(
        "-q",
        "--max-quality",
        choices=BoostyDownloader.QUALITY_ORDER,
        help="Maximum video quality to select",
    )
    parser.add_argument(
        "-d", "--debug", action="store_true", help="Enable debug output to stderr"
    )
    parser.add_argument(
        "--download", action="store_true", help="Download videos instead of listing"
    )
    parser.add_argument(
        "-o",
        "--output",
        default=env_output or ".",
        help="Target directory for downloads (default: current directory). Can be set via TARGET_PATH env var.",
    )
    parser.add_argument(
        "--season-dir",
        action="store_true",
        help="Create season subdirectories (Season YYYY)",
    )
    parser.add_argument(
        "--channel-dir",
        action="store_true",
        help="Create channel subdirectory",
    )
    parser.add_argument(
        "--days-back",
        type=int,
        help="Only process posts from the last N days (default: process all posts)",
    )
    parser.add_argument(
        "--lock-file",
        help="Lock file path to prevent multiple instances (useful for cron jobs)",
    )
    parser.add_argument(
        "--plex-url",
        default="http://localhost:32400",
        help="Plex server URL (default: http://localhost:32400)",
    )
    parser.add_argument(
        "--plex-token",
        help="Plex authentication token (X-Plex-Token)",
    )
    parser.add_argument(
        "--plex-section",
        help="Plex library section ID to refresh after downloads",
    )
    parser.add_argument(
        "--jellyfin-url",
        default="http://localhost:8096",
        help="Jellyfin server URL (default: http://localhost:8096)",
    )
    parser.add_argument(
        "--jellyfin-token",
        help="Jellyfin authentication token",
    )
    parser.add_argument(
        "--jellyfin-item",
        help="Jellyfin library item ID to refresh after downloads",
    )
    parser.add_argument(
        "--notify-email",
        default=env_notify_email,
        help="Email address to notify about new downloads using sendmail. Can be set via NOTIFY_EMAIL env var.",
    )

    args = parser.parse_args()

    # Use environment variable channels if none provided via command line
    using_env_channels = False
    if not args.channels and env_channels:
        args.channels = env_channels
        using_env_channels = True
    elif not args.channels:
        parser.error("channels are required (via argument or CHANNELS env var)")

    # Auto-enable download, channel-dir and season-dir for backward compatibility when using CHANNELS env var
    if using_env_channels:
        if not args.download:
            args.download = True
        if not args.channel_dir:
            args.channel_dir = True
        if not args.season_dir:
            args.season_dir = True
    # Auto-enable channel-dir if multiple channels are specified via command line
    elif len(args.channels) > 1 and not args.channel_dir:
        args.channel_dir = True

    # Acquire lock if lock file is specified
    if args.lock_file:
        lock_fd = acquire_lock(args.lock_file)
        if lock_fd is None:
            print(
                f"Another instance is already running (lock file: {args.lock_file})",
                file=sys.stderr,
            )
            sys.exit(1)

    # Initialize aggregation variables
    total_stats = {
        "new": 0,
        "downloaded": 0,
        "failed": 0,
        "skipped_existing": 0,
        "skipped_no_access": 0,
        "skipped_unavailable": 0,
        "skipped_non_video": 0,
    }
    all_downloaded_files = []
    all_posts = {}  # Dictionary to group posts by channel

    # Process each channel
    for channel in args.channels:
        if args.download and len(args.channels) > 1:
            print(f"\n{'=' * 60}")
            print(f"Processing channel: {channel}")
            print(f"{'=' * 60}\n")

        lister = BoostyDownloader(
            args.cookies,
            args.interface,
            args.max_quality,
            args.debug,
            args.download,
            args.output,
            args.season_dir,
            args.channel_dir,
            args.days_back,
            args.plex_url,
            args.plex_token,
            args.plex_section,
            args.jellyfin_url,
            args.jellyfin_token,
            args.jellyfin_item,
            args.notify_email,
        )
        result = lister.list_posts(channel)

        # Aggregate based on mode
        if args.download:
            # Aggregate stats if downloading
            for key in total_stats:
                total_stats[key] += result[key]
            all_downloaded_files.extend(lister.downloaded_files)
        else:
            # Extract channel name from URL if needed
            channel_name = channel
            if channel.startswith("http"):
                channel_name = channel.rstrip("/").split("/")[-1]
            all_posts[channel_name] = result

    # Print aggregated results based on mode
    if args.download:
        if len(args.channels) > 1:
            print("\n" + "=" * 60)
            print("Overall Download Summary (All Channels):")
            print("=" * 60)
        else:
            print("\n" + "=" * 60)
            print("Download Summary:")
            print("=" * 60)
        print(f"New files found:       {total_stats['new']}")
        print(f"Successfully downloaded: {total_stats['downloaded']}")
        print(f"Failed downloads:      {total_stats['failed']}")
        print(f"Already existing:      {total_stats['skipped_existing']}")
        print(f"Skipped (no access):   {total_stats['skipped_no_access']}")
        print(f"Skipped (unavailable): {total_stats['skipped_unavailable']}")
        print(f"Skipped (non-video):   {total_stats['skipped_non_video']}")
        print("=" * 60)

        # Trigger media server library refresh and email notification if any files were downloaded
        if total_stats['downloaded'] > 0:
            # Use the last lister instance for refresh operations (shares same config)
            lister._refresh_plex_library()
            lister._refresh_jellyfin_library()

            # Send aggregated email notification
            if lister.notify_email:
                lister.downloaded_files = all_downloaded_files
                lister._send_email_notification()
    else:
        # Print list results as hierarchical JSON: channels -> posts -> videos
        print(json.dumps(all_posts, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
