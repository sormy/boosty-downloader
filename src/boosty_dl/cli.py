import argparse
import os
import sys

from . import auth, api, core, email, jellyfin, lock, plex


def _find_default_cookies_file() -> str | None:
    candidates = [
        "cookies.txt",
        ".boosty.cookies.txt",
        os.path.expanduser("~/.boosty.cookies.txt"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Download videos from Boosty channels")
    parser.add_argument("channels", nargs="+", help="Channel names or URLs")
    parser.add_argument(
        "-c", "--cookies", help="Cookies file (optional, for paid content)"
    )
    parser.add_argument(
        "--force-access-token-refresh",
        action="store_true",
        help="Force refresh of access token even if not expired",
    )
    parser.add_argument("-o", "--output", default=".", help="Output directory")
    parser.add_argument(
        "-q", "--max-quality", choices=api.QUALITIES, help="Maximum quality"
    )
    parser.add_argument("--days-back", type=int, help="Process last N days only")
    parser.add_argument(
        "--update-metadata",
        action="store_true",
        help="Update metadata for existing files without downloading",
    )
    parser.add_argument(
        "--no-season-dir", action="store_true", help="Don't create season directories"
    )
    parser.add_argument(
        "--no-channel-dir", action="store_true", help="Don't create channel directories"
    )
    parser.add_argument("--lock-file", help="Lock file path")
    parser.add_argument(
        "--plex-section", help="Plex library section name or key to refresh"
    )
    parser.add_argument("--plex-url", default="http://localhost:32400", help="Plex URL")
    parser.add_argument(
        "--plex-token",
        default=os.environ.get("PLEX_TOKEN"),
        help="Plex authentication token (or set PLEX_TOKEN env var)",
    )
    parser.add_argument(
        "--plex-timeout", type=int, default=30, help="Plex timeout (sec)"
    )
    parser.add_argument(
        "--jellyfin-item", help="Jellyfin library item name or ID to refresh"
    )
    parser.add_argument(
        "--jellyfin-url", default="http://localhost:8096", help="Jellyfin URL"
    )
    parser.add_argument(
        "--jellyfin-token",
        default=os.environ.get("JELLYFIN_TOKEN"),
        help="Jellyfin authentication token (or set JELLYFIN_TOKEN env var)",
    )
    parser.add_argument(
        "--jellyfin-timeout", type=int, default=30, help="Jellyfin timeout (sec)"
    )
    parser.add_argument(
        "--email-to", help="Email address to send download notifications to"
    )

    args = parser.parse_args()

    # flush output after each line
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]

    try:
        # find default cookies file if not provided
        if not args.cookies:
            args.cookies = _find_default_cookies_file()

        # disable multiple instances if lock file specified
        if args.lock_file and lock.acquire_lock(args.lock_file) is None:
            raise RuntimeError(f"Another instance running (lock: {args.lock_file})")

        # if downloading to network location, ensure it exists
        if os.path.exists(args.output) is False:
            raise RuntimeError(f"Output directory does not exist: {args.output}")

        # get access token if cookies provided
        access_token = None
        if args.cookies:
            access_token = auth.get_access_token(
                args.cookies, force_refresh=args.force_access_token_refresh
            )
            if not access_token:
                print(
                    "WARNING: No valid access token, only free content available",
                    file=sys.stderr,
                )

        # process each channel or post
        all_downloaded_files = core.download_links(
            links=args.channels,
            output_dir=args.output,
            access_token=access_token,
            max_quality=args.max_quality,
            days_back=args.days_back,
            use_season_dir=not args.no_season_dir,
            use_channel_dir=not args.no_channel_dir,
            update_metadata=args.update_metadata,
        )

        # refresh Plex library if requested
        if all_downloaded_files and args.plex_section and args.plex_token:
            plex.refresh_plex_library(
                args.plex_url, args.plex_token, args.plex_section, args.plex_timeout
            )

        # refresh Jellyfin library if requested
        if all_downloaded_files and args.jellyfin_item and args.jellyfin_token:
            jellyfin.refresh_jellyfin_library(
                args.jellyfin_url,
                args.jellyfin_token,
                args.jellyfin_item,
                args.jellyfin_timeout,
            )

        # send email notification if requested
        if all_downloaded_files and args.email_to:
            count = len(all_downloaded_files)
            subject = f"Boosty: {count} new file{'s' if count != 1 else ''} downloaded"
            body = f"Downloaded {count} file(s):\n\n" + "\n".join(
                f"- {f}" for f in all_downloaded_files
            )
            email.send_notification(args.email_to, subject, body)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
