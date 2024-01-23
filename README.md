# Boosty Downloader

This simple shell script downloads videos from Boosty using yt-dlp. Designed to
be used as scheduled job to download new videos and make them available in Plex.

## Prerequisites

1. Dependencies: curl bash coreutils sed jq

2. A special patched version of yt-dlp is needed (if boosty support is merged,
   then not needed):

```sh
# install custom fork with boosty support
# this is needed until support will be landed into yt-dlp repo
# boosty support https://github.com/yt-dlp/yt-dlp/pull/8704
cd /srv
git clone https://github.com/megapro17/yt-dlp
cd /srv/yt-dlp
apt install python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip3 install -r requirements.txt

# create wrapper with yt-dlp-boosty name
touch /srv/yt-dlp/yt-dlp-boosty
chmod +x /srv/yt-dlp/yt-dlp-boosty
ln -sf /srv/yt-dlp/yt-dlp-boosty /usr/local/bin/yt-dlp-boosty

nano /srv/yt-dlp/yt-dlp-boosty

#!/usr/bin/bash

YT_DLP_HOME="/srv/yt-dlp"
source "$YT_DLP_HOME/.venv/bin/activate"
export PYTHONPATH="$YT_DLP_HOME"
exec python3 -m yt_dlp "$@"
```

3. Cookies file

Use "Get cookies.txt LOCALLY" extension to dump boosty.to cookies into
boosty.cookies.txt:
https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc?pli=1

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
Environment=YT_DLP="yt-dlp-boosty"
Environment=COOKIES_FILE="/srv/boosty.cookies.txt"
Environment=TARGET_PATH="/media/MediaFiles/Boosty"
Environment=TEMP_PATH="/media/MediaFiles/Boosty.tmp"
Environment=CHANNELS="blog1 blog2 blog3"
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
OnCalendar=*-*-* */1:00:00

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
