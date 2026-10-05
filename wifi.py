import network
import time

import storage

FILE = "wifi.json"   # {"ssid", "password", "verified"} written by the setup portal


def saved():
    data = storage.load(FILE)
    return data if data and data.get("ssid") else None


def save(ssid, password):
    storage.save(FILE, {"ssid": ssid, "password": password, "verified": False})


def mark_verified(data):
    if not data.get("verified"):
        data["verified"] = True
        storage.save(FILE, data)


def forget():
    storage.remove(FILE)


def connect(ssid, password, timeout_seconds, feed=None):
    """Connects to the WiFi. Returns True/False, never blocks longer than timeout_seconds."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected():
        return True

    print("WiFi: connecting to", ssid)
    try:
        wlan.connect(ssid, password)
    except OSError as error:
        # "Wifi Internal State Error": the radio is still reconnecting by itself. Wait for it below.
        print("WiFi: connect() busy -", repr(error))
    start = time.ticks_ms()
    while not wlan.isconnected():
        if time.ticks_diff(time.ticks_ms(), start) > timeout_seconds * 1000:
            print("WiFi: no connection after", timeout_seconds, "s")
            try:
                wlan.disconnect()
            except OSError:
                pass
            return False
        if feed:
            feed()
        time.sleep_ms(250)

    print("WiFi: connected, IP", wlan.ifconfig()[0])
    return True


def is_connected():
    return network.WLAN(network.STA_IF).isconnected()


def scan():
    """Names of the 2.4 GHz networks around, strongest first, without repeats."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        found = sorted(wlan.scan(), key=lambda n: -n[3])
    except OSError:
        return []
    names = []
    for net in found:
        try:
            name = net[0].decode() if isinstance(net[0], bytes) else str(net[0])
        except UnicodeError:
            continue
        if name and name not in names:
            names.append(name)
    return names[:15]
