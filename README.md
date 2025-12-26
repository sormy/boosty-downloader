# Boosty Downloader (boosty-dl)

Boosty Downloader (boosty-dl) — the ultimate tool for mirroring Boosty channels
into a local media library, fully compatible with Plex and Jellyfin.

## Features

- Download videos from Boosty channels
- Automatic access token refresh
- Plex and Jellyfin library integration
- Quality selection
- Season/episode naming (s2025e0101 format)
- Video metadata embedding
- Interface binding (Boosty bans some VPNs)

## Installation

### Prerequisites

- `curl` - downloads videos and makes Boosty API requests
- `sendmail` - email notifications (optional)

```sh
apt install curl sendmail # debian/ubuntu
brew install curl # macos
```

### From PyPI (recommended)

```sh
apt install pipx # debian/ubuntu
brew install pipx # macos
pipx install boosty-dl
```

### From source

```sh
git clone https://github.com/sormy/boosty-downloader.git
cd boosty-downloader

# install boosty-dl
python3 -m venv .venv
.venv/bin/pip install -e .
ln -sf $(realpath .venv/bin/boosty-dl) /usr/local/bin/boosty-dl

# install backward compatible script (if needed)
ln -sf $(realpath bin/boosty-downloader) /usr/local/bin/boosty-downloader
```

### Cookies file

Export your Boosty cookies using a browser extension:

- Chrome:
  https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc
- Firefox: https://addons.mozilla.org/en-US/firefox/addon/cookies-txt

**Automatic detection:** If `-c` is not provided, the tool automatically checks
for cookies in:

1. `cookies.txt` (current directory)
2. `.boosty.cookies.txt` (current directory)
3. `~/.boosty.cookies.txt` (home directory)

**Recommendation:** Export cookies from an **incognito/private browser tab**.
This creates a separate session with a unique client ID. This way, access token
refreshes by boosty-dl won't interfere with your regular browser session, and
token refreshes in your browser won't invalidate the boosty-dl cookies file.

The tool uses cookies to authenticate and automatically refreshes the access
token. Without cookies, only free content is available.

## Usage

### Basic usage

```sh
# Download from a single channel
boosty-dl -c boosty.cookies.txt -o ./videos channelname
boosty-dl -c boosty.cookies.txt -o ./videos https://boosty.to/channel

# Download from multiple channels
boosty-dl -c boosty.cookies.txt -o ./videos channel1 channel2 channel3

# Download from a specific post
boosty-dl -c boosty.cookies.txt -o ./videos https://boosty.to/channel/posts/post-id
```

### Options

```
-c, --cookies FILE                  Cookies file (optional, for paid content)
--force-access-token-refresh        Force refresh of access token even if not expired
-o, --output DIR                    Output directory (default: current directory)
-q, --max-quality QUALITY           Maximum quality: tiny, lowest, low, medium, high, full_hd, quad_hd, ultra_hd
--days-back DAYS                    Process last N days only
--update-metadata                   Update metadata for existing files without downloading
--no-season-dir                     Don't create season directories
--no-channel-dir                    Don't create channel directories
--lock-file PATH                    Lock file path
--plex-section NAME/KEY             Plex library section name or key to refresh
--plex-url URL                      Plex server URL (default: http://localhost:32400)
--plex-token TOKEN                  Plex authentication token (or set PLEX_TOKEN env var)
--plex-timeout SEC                  Plex timeout in seconds (default: 30)
--jellyfin-item NAME/ID             Jellyfin library item name or ID to refresh
--jellyfin-url URL                  Jellyfin server URL (default: http://localhost:8096)
--jellyfin-token TOKEN              Jellyfin authentication token (or set JELLYFIN_TOKEN env var)
--jellyfin-timeout SEC              Jellyfin timeout in seconds (default: 30)
--email-to EMAIL                    Email address to send download notifications to
```

**Network interface binding:** Some VPNs or regions may be blocked by Boosty.
Use `CURL_OPTS="--interface eth0"` to bind to a specific network interface that
has proper access.

**Lock file:** When running as a scheduled job, use `--lock-file` to prevent
overlapping downloads if a previous run takes too long.

**Plex/Jellyfin:** Automatically finds library sections/items by name - no need
to look up IDs/keys manually.

### Backward compatibility with v1.x

For users upgrading from v1.x, a backward-compatible shell script wrapper is
available in `bin/boosty-downloader`:

**Usage with environment variables (v1.x style):**

```sh
export COOKIES_FILE="/srv/boosty.cookies.txt"
export TARGET_PATH="/media/MediaFiles/Boosty"
export CHANNELS="blog1 blog2 blog3"
export NOTIFY_EMAIL="user@domain.com"
boosty-downloader
```

The wrapper translates v1.x environment variables to v2.x command-line
arguments.

## Environment Variables

The tool supports the following environment variables:

**Authentication & Security:**

- `PLEX_TOKEN` - Plex authentication token (alternative to `--plex-token`)
- `JELLYFIN_TOKEN` - Jellyfin API key (alternative to `--jellyfin-token`)

**Binary Paths:**

- `CURL_BIN` - Path to curl binary (default: `curl`)
- `SENDMAIL_BIN` - Path to sendmail binary (default: `/usr/sbin/sendmail`)

**Advanced Options:**

- `CURL_OPTS` - Additional curl options (e.g., `--interface eth0`)
- `CURL_DEBUG` - Enable curl debug output (set to `1`)

**v1.x Compatibility (for `boosty-downloader` wrapper):**

- `COOKIES_FILE` - Path to cookies file (maps to `-c`)
- `TARGET_PATH` - Output directory (maps to `-o`)
- `CHANNELS` - Space-separated channel list
- `NOTIFY_EMAIL` - Email for notifications (maps to `--email-to`)

## Scheduled Downloads with Systemd

Set up a systemd timer for automated periodic downloads.

Create service unit `/etc/systemd/system/boosty-dl.service`:

```ini
[Unit]
Description=Boosty Downloader
Wants=boosty-dl.timer
Requires=media-MediaFiles.mount
After=media-MediaFiles.mount

[Service]
Type=oneshot
User=root
Environment="PLEX_TOKEN=YOUR_PLEX_TOKEN"
Environment="JELLYFIN_TOKEN=YOUR_JELLYFIN_TOKEN"
ExecStart=/usr/local/bin/boosty-dl \
    -c /srv/boosty.cookies.txt \
    -o /media/MediaFiles/Boosty \
    --days-back 7 \
    --lock-file /var/run/boosty-dl.lock \
    --plex-url http://localhost:32400 \
    --plex-section "Boosty" \
    --jellyfin-url http://localhost:8096 \
    --jellyfin-item "Boosty" \
    --email-to admin@example.com \
    channel1 channel2 channel3


[Install]
WantedBy=multi-user.target
```

Create timer unit `/etc/systemd/system/boosty-dl.timer`:

```ini
[Unit]
Description=Boosty Downloader Timer
Requires=boosty-dl.service

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
```

Enable and start:

```sh
systemctl daemon-reload
systemctl enable --now boosty-dl.timer
systemctl status boosty-dl.timer
journalctl -u boosty-dl -f
```

**Key options for scheduled downloads:**

- `--days-back 7` - Check only recent posts (reduces API calls)
- `--lock-file` - Prevent overlapping runs
- `--plex-section` or `--jellyfin-item` - Auto-refresh media library
- `--email-to` - Email notifications for new downloads

## Plex Integration

Automatically refreshes your Plex library after downloading. Library sections
are found by name.

**Recommended: Environment variable (prevents token exposure in process
listings):**

```sh
export PLEX_TOKEN="YOUR_TOKEN"
boosty-dl -c cookies.txt -o ./videos \
    --plex-url http://localhost:32400 \
    --plex-section "Boosty" \
    channelname
```

**Alternative: Command-line argument:**

```sh
boosty-dl -c cookies.txt -o ./videos \
    --plex-url http://localhost:32400 \
    --plex-token YOUR_TOKEN \
    --plex-section "Boosty" \
    channelname
```

**Note:** If token starts with `-`, use `--plex-token=-YOUR_TOKEN` format.

**Getting your Plex token:**

1. Open Plex Web
2. Press F12 → Console tab
3. Type: `localStorage.getItem('myPlexAccessToken')`
4. Copy the token (without quotes)

## Jellyfin Integration

Automatically refreshes your Jellyfin library after downloading. Library items
are found by name.

**Recommended: Environment variable (prevents token exposure in process
listings):**

```sh
export JELLYFIN_TOKEN="YOUR_API_KEY"
boosty-dl -c cookies.txt -o ./videos \
    --jellyfin-url http://localhost:8096 \
    --jellyfin-item "Boosty" \
    channelname
```

**Alternative: Command-line argument:**

```sh
boosty-dl -c cookies.txt -o ./videos \
    --jellyfin-url http://localhost:8096 \
    --jellyfin-token YOUR_API_KEY \
    --jellyfin-item "Boosty" \
    channelname
```

**Getting your API key:**

1. Jellyfin Dashboard → API Keys
2. Click "+" to create new key
3. Name it (e.g., "boosty-dl")
4. Copy the generated key

## Development

```sh
# Clone repository
git clone https://github.com/sormy/boosty-downloader.git
cd boosty-downloader

# Install in development mode with dev dependencies
make dev

# Run tests
make test

# Format code
make format

# Run linters
make lint

# Build package
make build

# Publish to PyPI
make publish
```

## License

MIT
