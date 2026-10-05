# Real time (UTC) from the internet. Readings need it: ms-devices rejects readings from the future
# or older than 24 h, so nothing is recorded until the first sync.
import time

try:
    import ntptime
except ImportError:  # only on a PC
    ntptime = None

# MicroPython on ESP32 counts from 2000-01-01, UNIX from 1970-01-01
_EPOCH_OFFSET = 946684800 if time.gmtime(0)[0] == 2000 else 0
_synced_at = None


def sync(host):
    """Sets the RTC from NTP. True if it worked."""
    global _synced_at
    try:
        ntptime.host = host
        ntptime.settime()
        _synced_at = time.ticks_ms()
        print("Clock: synced", unix_now())
        return True
    except (OSError, OverflowError, AttributeError) as error:
        print("Clock: NTP failed -", repr(error))
        return False


def is_synced():
    return _synced_at is not None


def needs_sync(resync_seconds):
    return _synced_at is None or time.ticks_diff(time.ticks_ms(), _synced_at) > resync_seconds * 1000


def unix_now():
    return int(time.time()) + _EPOCH_OFFSET
