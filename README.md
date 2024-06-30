# Boosty Downloader

This simple shell script downloads videos from Boosty using yt-dlp. Designed to
be used as scheduled job to download new videos and make them available in Plex.

## Prerequisites

1. Dependencies: curl bash coreutils sed jq

2. A last version of yt-dlp is needed:

```sh
# install latest yt-dlp using pip in virtual environment
mkdir -p /srv/yt-dlp
cd /srv/yt-dlp
apt install python3-venv
python3 -m venv .
./bin/pip3 install yt-dlp

# update existing yt-dlp (if was already installed)
./bin/pip3 install --upgrade yt-dlp

# check version of installed yt-dlp to be 2024.03.10+
./bin/yt-dlp --version

# for convinience, create symlink in search path
ln -sf /srv/yt-dlp/bin/yt-dlp /usr/local/bin/yt-dlp

# update shell search path and check version again
hash -r
yt-dlp --version
```

3. Cookies file

Use browser plugion to do to dump boosty.to cookies into `boosty.cookies.txt`
(authenticate before):

- Chrome: https://chromewebstore.google.com/detail/get-cookiestxt-locally
- Firefox: https://addons.mozilla.org/en-US/firefox/addon/cookies-txt

## Installation

```sh
cd /srv
git clone https://github.com/sormy/boosty-downloader.git
ln -sfv /srv/boosty-downloader/boosty-downloader /usr/local/bin/boosty-downloader
```

## Usage

```sh
export COOKIES_FILE="/srv/boosty.cookies.txt"
export TARGET_PATH="/media/MediaFiles/Boosty"
export CHANNELS="blog1 blog2 blog3"
# if boosty support will be merged into upstream
# export YT_DLP="yt-dlp"
boosty-downloader
```

## Service

Create service unit:

```
nano /etc/systemd/system/boosty-downloader.service

[Unit]
Wants=boosty-downloader.timer

[Service]
Type=oneshot
User=root
Environment="YT_DLP=/usr/local/bin/yt-dlp"
Environment="COOKIES_FILE=/srv/boosty.cookies.txt"
Environment="TARGET_PATH=/media/MediaFiles/Boosty"
Environment="TEMP_PATH=/media/MediaFiles/Boosty.tmp"
Environment="CHANNELS=blog1 blog2 blog3"
Environment="NOTIFY_EMAIL=user@domain.com"
ExecStart=boosty-downloader

[Install]
WantedBy=multi-user.target
```

Create timer unit:

```
nano /etc/systemd/system/boosty-downloader.timer

[Unit]
Requires=boosty-downloader.service

[Timer]
Unit=boosty-downloader.service
OnCalendar=hourly

[Install]
WantedBy=timers.target
```

```sh
# reload units
systemctl daemon-reload
# try to start once
systemctl start boosty-downloader
# check status and logs
systemctl status boosty-downloader
journalctl -u boosty-downloader
# if all is ok, enable timer
systemctl enable boosty-downloader.timer
```

## Plex rescan

Login to Plex console, open debug console, open local storage and grab value of
"myPlexAccessToken".

Find section IDs:

```sh
curl -L -X GET 'http://localhost:32400/library/sections' \
    -H 'Accept: application/json' \
    -H 'X-Plex-Token: <TOKEN>' \
    | jq '.MediaContainer.Directory[] | { key: .key, title: .title }'
```

Edit `boosty-downloader.service`:

```
nano /etc/systemd/system/boosty-downloader.service

[Service]
...
Environment="PLEX_SECTION=<PLEX_SECTION_ID>"
Environment="PLEX_TOKEN=<PLEX_TOKEN>"
# see more https://support.plex.tv/articles/201638786-plex-media-server-url-commands/
ExecStartPost=curl -sS -L -X GET \
    'http://localhost:32400/library/sections/${PLEX_SECTION}/refresh' \
    -H 'X-Plex-Token: ${PLEX_TOKEN}'
```

## Jellyfin rescan

Login to Jellyfin console, open settings and create new api key.

Find item IDs:

```sh
curl -sS -L -X GET -G \
    "http://localhost:8096/Items" \
    -H 'Authorization: MediaBrowser Token=<JELLYFIN_API_KEY>' \
    -d 'Recursive=True' \
    -d 'IncludeItemTypes=CollectionFolder' \
    | jq '.Items[] | { id: .Id, name: .Name }'
```

Edit `boosty-downloader.service`:

```
nano /etc/systemd/system/boosty-downloader.service

[Service]
...
Environment="JELLYFIN_ITEM=<JELLYFIN_ITEM_ID>"
Environment="JELLYFIN_TOKEN=<JELLYFIN_API_KEY>"
# see more https://api.jellyfin.org/#tag/ItemRefresh/operation/RefreshItem
ExecStartPost=curl -sS -L -X POST \
    'http://localhost:8096/Items/${JELLYFIN_ITEM}/Refresh' \
    -H 'Authorization: MediaBrowser Token="${JELLYFIN_TOKEN}"' \
    -d 'Recursive=true' \
    -d 'MetadataRefreshMode=Default' \
    -d 'ImageRefreshMode=Default' \
    -d 'ReplaceAllImages=false' \
    -d 'ReplaceAllMetadata=false'
```
