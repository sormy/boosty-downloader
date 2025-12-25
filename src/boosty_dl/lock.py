import atexit
import fcntl
import os
import sys


def acquire_lock(lock_file: str) -> int | None:
    try:
        fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)

        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.ftruncate(fd, 0)
            os.write(fd, str(os.getpid()).encode())

            def cleanup():
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                    os.close(fd)
                    os.remove(lock_file)
                except Exception:
                    pass

            atexit.register(cleanup)
            return fd
        except BlockingIOError:
            os.close(fd)
            return None
    except Exception as e:
        print(f"ERROR: Unable to acquire lock: {e}", file=sys.stderr)
        return None
