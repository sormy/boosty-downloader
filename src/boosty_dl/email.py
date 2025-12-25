import os
import subprocess
import sys

SENDMAIL_BIN = os.environ.get("SENDMAIL_BIN", "/usr/sbin/sendmail")


def send_notification(to_address: str, subject: str, body: str) -> None:
    message = f"To: {to_address}\nSubject: {subject}\n\n{body}"

    try:
        subprocess.run(
            [SENDMAIL_BIN, "-t"],
            input=message,
            text=True,
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"WARNING: Failed to send email: {e.stderr}", file=sys.stderr)
    except FileNotFoundError:
        print(
            f"WARNING: sendmail not found at {SENDMAIL_BIN}, email not sent",
            file=sys.stderr,
        )
