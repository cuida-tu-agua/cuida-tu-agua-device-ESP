# Settings that are the same for every device (they CAN go into git).

FIRMWARE_VERSION = "2.0.0"

# --- Times (seconds) -----------------------------------------------------------
HEARTBEAT_SECONDS = 30        # HU-013: "Desconectado" after 10 min without one
TELEMETRY_SECONDS = 10        # one reading every 10 s (HU-015..018)
VALVE_REPORT_SECONDS = 60     # HU-019: valve-service shows "Sin comunicación" after 3 min without one
RETRY_SECONDS = 5             # after a failed connection, try again sooner
NTP_RESYNC_SECONDS = 6 * 3600 # the ESP32 clock drifts a few seconds per day
NTP_HOST = "pool.ntp.org"

WIFI_TIMEOUT_SECONDS = 20
MQTT_TIMEOUT_SECONDS = 10
MQTT_KEEPALIVE_SECONDS = 60   # > HEARTBEAT_SECONDS: each heartbeat keeps the session alive

# Offline buffer: 360 readings x 10 s = 1 hour without WiFi or broker, nothing is lost.
# When full, the two oldest readings are merged (the liters are kept, only detail is lost).
BUFFER_MAX = 360
FLUSH_PER_LOOP = 20           # readings sent per second when catching up

# --- Hardware (Arquitectura_Fisica_Dispositivo_IoT.md) ---------------------------
FLOW_SENSOR_PIN = 4           # YF-S201 yellow wire
STATUS_LED_PIN = 2            # blue LED on the board
SETUP_BUTTON_PIN = 0          # "BOOT" button of the board
CALIBRATION_FACTOR = 7.5      # YF-S201: pulses per second = 7.5 x (L/min)
MAX_FLOW_LPM = 60             # ms-devices rejects more than this
MAX_LITERS_PER_READING = 50   # ms-devices rejects more than 100 L in one reading: bigger backlogs are split

# Relay IN1 -> 12 V solenoid valve (Arquitectura_Fisica_Dispositivo_IoT.md: GPIO5).
# GPIO5 is a "strapping" pin: the ESP32 moves it by itself for a moment while it boots. If the relay
# clicks on every restart, move the wire to GPIO26 and set VALVE_PIN = 26 (any of 25/26/27/32/33).
VALVE_PIN = 5
# Level of VALVE_PIN that CLOSES the water. Our hardware uses a normally-CLOSED valve:
#   GPIO HIGH -> relay ON -> valve energized = OPEN;  GPIO LOW -> relay OFF -> valve CLOSED (fail-safe)
# So CLOSED = 0. (If your relay module is "active LOW", it is the other way around: use 1.)
VALVE_CLOSED_LEVEL = 0
VALVE_DEFAULT_STATE = "OPEN"  # first boot ever (later the last state is restored from valve.json)

# --- Setup mode (the ESP32's own WiFi network) -----------------------------------
SETUP_HOLD_SECONDS = 5        # hold BOOT this long (while running) to forget the WiFi and go to setup
PORTAL_PORT = 80              # http://192.168.4.1
FIRST_CONNECT_SECONDS = 60    # new WiFi that never worked: after this, back to setup mode

# The watchdog restarts the ESP32 if the program freezes (e.g. a socket that never answers).
# Set it to False while you are developing with Thonny.
USE_WATCHDOG = False
WATCHDOG_MS = 60_000
