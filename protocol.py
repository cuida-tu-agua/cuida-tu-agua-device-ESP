# MQTT contract with ms-devices (CONTRACTS.md). Pure functions: no hardware, no network,
# so they also run (and are tested) on a PC.
#   ESP32 -> sywater/devices/{serial}/heartbeat     {"token","fw"}
#   ESP32 -> sywater/devices/{serial}/telemetry     {"token","ts","lpm","vol","total"}
#   ESP32 -> sywater/devices/{serial}/valve/state   {"token","state","commandId","ts"}
#   server-> sywater/devices/{serial}/valve/set     {"commandId","action"}
import json

PREFIX = "sywater/devices/"
MAX_PAYLOAD_LENGTH = 512      # ms-devices ignores anything bigger
OPEN = "OPEN"
CLOSED = "CLOSED"


def topics(serial):
    serial = serial.strip().upper()
    # "/", "+" and "#" have a special meaning in MQTT topics
    if not serial or "/" in serial or "+" in serial or "#" in serial:
        raise ValueError("invalid serial: " + serial)
    base = PREFIX + serial + "/"
    return {
        "heartbeat": base + "heartbeat",
        "telemetry": base + "telemetry",
        "valve_state": base + "valve/state",
        "valve_set": base + "valve/set",
    }


def _dump(data):
    text = json.dumps(data)
    if len(text) > MAX_PAYLOAD_LENGTH:
        raise ValueError("payload too long")
    return text


def heartbeat(token, firmware_version):
    if not token:
        raise ValueError("DEVICE_TOKEN is empty")
    return _dump({"token": token, "fw": firmware_version})


def telemetry(token, ts, lpm, vol, total):
    return _dump({"token": token, "ts": int(ts), "lpm": round(lpm, 2), "vol": round(vol, 3), "total": round(total, 3)})


def valve_state(token, state, command_id=None, ts=None):
    data = {"token": token, "state": state, "commandId": command_id}
    if ts:
        data["ts"] = int(ts)   # optional: ms-devices uses its own clock if missing
    return _dump(data)


def _looks_like_guid(text):
    if not isinstance(text, str) or len(text) != 36:
        return False
    for i, ch in enumerate(text):
        if i in (8, 13, 18, 23):
            if ch != "-":
                return False
        elif ch not in "0123456789abcdefABCDEF":
            return False
    return True


def parse_command(payload):
    """valve/set payload -> (command_id, "OPEN"|"CLOSE"), or None if it is not a valid order."""
    try:
        if isinstance(payload, (bytes, bytearray)):
            payload = payload.decode()
        if len(payload) > MAX_PAYLOAD_LENGTH:
            return None
        data = json.loads(payload)
        command_id = data.get("commandId")
        action = str(data.get("action", "")).strip().upper()
    except (ValueError, AttributeError, UnicodeError):
        return None
    if action not in ("OPEN", "CLOSE") or not _looks_like_guid(command_id):
        return None
    return command_id.lower(), action
