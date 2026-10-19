# Cuida Tu Agua - ESP32 firmware 2.x
#   HU-012/013  heartbeat to Mosquitto (the device appears "Conectado" in the app)
#   HU-015..018 a flow reading every 10 s (buffered for 1 h if the network is down)
#   HU-019..021 electrovalve: obeys orders from the app and reports its real state
#   Setup mode: own WiFi network "CuidaTuAgua-XXXX" + page http://192.168.4.1
# main.py runs by itself every time the ESP32 starts.
import machine
import time

import config

# The valve goes back to its last state FIRST, before anything else (a closed valve stays closed
# after a power cut or a restart; the pin is not left floating during the 3 s pause below)
from valve import Valve

valve = Valve(config.VALVE_PIN, config.VALVE_CLOSED_LEVEL, config.VALVE_DEFAULT_STATE)

import clock  # noqa: E402
import protocol  # noqa: E402
import secrets  # noqa: E402
import wifi  # noqa: E402
from flow import FlowMeter  # noqa: E402
from link import MqttLink  # noqa: E402
from readings import ReadingBuffer  # noqa: E402
from setup_portal import Portal  # noqa: E402

print("Cuida Tu Agua", config.FIRMWARE_VERSION, "-", secrets.DEVICE_SERIAL, "- valve", valve.state)
print("Press Ctrl+C in the next 3 s to stop and get the REPL")
time.sleep(3)

led = machine.Pin(config.STATUS_LED_PIN, machine.Pin.OUT)
button = machine.Pin(config.SETUP_BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
watchdog = machine.WDT(timeout=config.WATCHDOG_MS) if config.USE_WATCHDOG else None


def feed():
    if watchdog:
        watchdog.feed()


_pressed_since = None


def setup_requested():
    """True when BOOT has been held SETUP_HOLD_SECONDS. Measured by time (not by loops), so it also
    works while connect() is waiting for a WiFi that is not around. The LED stays on while held."""
    global _pressed_since
    if button.value() != 0:
        _pressed_since = None
        return False
    if _pressed_since is None:
        _pressed_since = time.ticks_ms()
        print("Setup button: hold it", config.SETUP_HOLD_SECONDS, "s to forget the WiFi")
    led.on()
    return time.ticks_diff(time.ticks_ms(), _pressed_since) >= config.SETUP_HOLD_SECONDS * 1000


def forget_wifi_and_restart():
    print("Setup button: forgetting the WiFi")
    wifi.forget()
    machine.reset()


def credentials():
    data = wifi.saved()
    if data is None and getattr(secrets, "WIFI_SSID", ""):
        data = {"ssid": secrets.WIFI_SSID, "password": secrets.WIFI_PASSWORD, "verified": True}   # dev only
    return data


def setup_mode(last_error=None):
    Portal(secrets.DEVICE_SERIAL, secrets.SETUP_PASSWORD, config.FIRMWARE_VERSION,
           config.PORTAL_PORT, last_error).run(feed, led)


class Every:
    """A timer that fires every `seconds` (first time: right away)."""

    def __init__(self, seconds):
        self.ms = seconds * 1000
        self.next = time.ticks_ms()

    def due(self):
        return time.ticks_diff(time.ticks_ms(), self.next) >= 0

    def again(self, seconds=None):
        self.next = time.ticks_add(time.ticks_ms(), seconds * 1000 if seconds is not None else self.ms)

    def now(self):
        self.next = time.ticks_ms()


def run():
    creds = credentials()
    if creds is None:
        setup_mode()                       # never returns: restarts when the user saves the WiFi

    meter = FlowMeter(config.FLOW_SENSOR_PIN, config.CALIBRATION_FACTOR)
    link = MqttLink(secrets, config)
    buffer = ReadingBuffer(config.BUFFER_MAX)
    t = protocol.topics(secrets.DEVICE_SERIAL)
    token = secrets.DEVICE_TOKEN

    heartbeat = Every(config.HEARTBEAT_SECONDS)
    valve_report = Every(config.VALVE_REPORT_SECONDS)
    ntp = Every(30)
    reconnect = Every(config.RETRY_SECONDS)
    started = time.ticks_ms()
    interval_start = time.ticks_ms()
    interval_pulses = 0

    while True:
        loop_start = time.ticks_ms()
        feed()

        # 0) BOOT held 5 s → forget the WiFi and go to setup mode
        if setup_requested():
            forget_wifi_and_restart()

        # 1) WiFi (if it fell, reconnect; the sensor keeps counting meanwhile)
        if not wifi.is_connected():
            led.off()
            link.close()  # the old socket is dead
            if wifi.connect(creds["ssid"], creds.get("password", ""), config.WIFI_TIMEOUT_SECONDS, feed,
                            setup_requested):
                wifi.mark_verified(creds)
            elif setup_requested():
                forget_wifi_and_restart()
            elif not creds.get("verified") and \
                    time.ticks_diff(time.ticks_ms(), started) > config.FIRST_CONNECT_SECONDS * 1000:
                # A WiFi that NEVER worked (wrong password?) → back to setup mode with the reason
                wifi.forget()
                setup_mode("No se pudo conectar a «{}». Revisa la contraseña.".format(creds["ssid"]))

        online = wifi.is_connected()

        # 2) Clock (UTC): needed to date the readings
        if online and ntp.due() and clock.needs_sync(config.NTP_RESYNC_SECONDS):
            ntp.again(config.NTP_RESYNC_SECONDS if clock.sync(config.NTP_HOST) else 60)

        # 3) Flow: a reading every TELEMETRY_SECONDS (until the clock is synced, the liters keep adding up)
        interval_pulses += meter.take()
        elapsed = time.ticks_diff(time.ticks_ms(), interval_start) / 1000
        if elapsed >= config.TELEMETRY_SECONDS and clock.is_synced():
            liters = meter.liters(interval_pulses)
            lpm = min(liters * 60 / elapsed, config.MAX_FLOW_LPM)
            now = clock.unix_now()
            # A long wait for the clock can pile up many liters: split them into valid readings,
            # one second apart (ms-devices drops a reading above 100 L and a repeated timestamp)
            chunks = []
            while liters > config.MAX_LITERS_PER_READING:
                chunks.append(config.MAX_LITERS_PER_READING)
                liters -= config.MAX_LITERS_PER_READING
            chunks.append(liters)
            total = meter.total_liters
            for i, vol in enumerate(chunks):
                buffer.add(now - (len(chunks) - 1 - i), lpm, vol, total)
            if interval_pulses:
                print("Flow: {:.2f} L/min | {:.3f} L | {} waiting".format(lpm, meter.liters(interval_pulses), len(buffer)))
            interval_pulses = 0
            interval_start = time.ticks_ms()
        elif elapsed >= 60 and not clock.is_synced() and int(elapsed) % 60 == 0:
            print("Clock: still not synced - readings wait (is UDP 123 / internet blocked?)")

        # 4) MQTT
        if online and not link.connected and reconnect.due():
            if link.ensure_connected():
                heartbeat.now()
                valve_report.now()          # tell valve-service the real state right away
            reconnect.again()               # broker down: try again in RETRY_SECONDS, not every second

        if link.connected:
            link.poll()
            # 4a) Orders from the app: do it, then confirm with the SAME commandId (HU-020/021)
            while link.commands and link.connected:
                command_id, action = link.commands[0]
                new_state = valve.execute(command_id, action)
                ts = clock.unix_now() if clock.is_synced() else None
                if link.publish(t["valve_state"], protocol.valve_state(token, new_state, command_id, ts)):
                    link.commands.pop(0)
                    valve_report.again()

            if link.connected and heartbeat.due():
                if link.publish(t["heartbeat"], protocol.heartbeat(token, config.FIRMWARE_VERSION)):
                    print("Heartbeat OK")
                heartbeat.again()

            if link.connected and valve_report.due():
                ts = clock.unix_now() if clock.is_synced() else None
                link.publish(t["valve_state"], protocol.valve_state(token, valve.state, None, ts))
                valve_report.again()

            # 4b) Readings, oldest first (catches up after an outage)
            sent = 0
            while link.connected and sent < config.FLUSH_PER_LOOP and buffer.peek():
                ts, lpm, vol, total = buffer.peek()
                if not link.publish(t["telemetry"], protocol.telemetry(token, ts, lpm, vol, total)):
                    break
                buffer.pop()
                sent += 1

        # LED: on = connected to the broker, off = no WiFi/broker
        led.value(1 if link.connected else 0)

        time.sleep_ms(max(0, 1000 - time.ticks_diff(time.ticks_ms(), loop_start)))


try:
    run()
except KeyboardInterrupt:
    print("Stopped (Ctrl+C)")
except Exception as error:
    # Anything unexpected: log it and start over clean, instead of staying frozen
    print("Fatal error:", repr(error), "- restarting in 5 s")
    time.sleep(5)
    machine.reset()
