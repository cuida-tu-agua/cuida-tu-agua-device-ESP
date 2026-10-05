# Copy this file as "secrets.py" and fill it in. secrets.py NEVER goes into git
# (it has the broker password and the factory token of this ESP32).
# The home WiFi is NOT here anymore: the user sets it from the phone (setup mode).

# Mosquitto: the LAN IP of the PC that runs docker (ipconfig -> IPv4), never "localhost"
MQTT_HOST = "192.168.X.X"
MQTT_PORT = 1883
MQTT_USER = "sywater-device"           # shared broker user of every ESP32 (see the acl file)
MQTT_PASSWORD = "password-of-sywater-device"

# Factory identity of THIS device (output of new-device.ps1; it is also printed on the label)
DEVICE_SERIAL = "SW-ESP32-000001"
DEVICE_TOKEN = "1gQn7MIHy0iGmO2hDpGM1n_uAdZRQUtJ"

# Password of the setup network "CuidaTuAgua-XXXX" (8 to 63 characters).
# Use the pairing code of the label WITHOUT the dash, e.g. "4HZX-VCDP" -> "4HZXVCDP".
SETUP_PASSWORD = "4HZXVCDP"

# Optional, only for development: if set, used when no WiFi was configured from the phone.
WIFI_SSID = ""
WIFI_PASSWORD = ""
