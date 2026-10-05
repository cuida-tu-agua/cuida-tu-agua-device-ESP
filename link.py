# Connection with Mosquitto: publishes heartbeats, readings and valve reports, and receives the
# valve orders of THIS device (the acl only lets it subscribe to its own valve/set).
from umqtt.simple import MQTTClient, MQTTException

import protocol


class MqttLink:
    def __init__(self, secrets, config):
        self._client = None
        self._secrets = secrets
        self._config = config
        self.topics = protocol.topics(secrets.DEVICE_SERIAL)
        self.commands = []          # orders received, done by main.py (never inside the callback)

    @property
    def connected(self):
        return self._client is not None

    def _on_message(self, topic, msg):
        command = protocol.parse_command(msg)
        if command is None:
            print("MQTT: invalid order ignored")
        elif command not in self.commands:
            self.commands.append(command)

    def _restore_timeout(self):
        # check_msg() leaves the socket blocking with NO timeout: put it back
        self._client.sock.settimeout(self._config.MQTT_TIMEOUT_SECONDS)

    def ensure_connected(self):
        """Connects and subscribes if needed. True if connected."""
        if self._client is not None:
            return True
        s, c = self._secrets, self._config
        client = MQTTClient(
            # The serial is unique per device. Two clients with the SAME id kick each other out.
            # The acl uses it (%c) to let each ESP32 read only its own orders.
            client_id=s.DEVICE_SERIAL,
            server=s.MQTT_HOST,
            port=s.MQTT_PORT,
            user=s.MQTT_USER,
            password=s.MQTT_PASSWORD,
            keepalive=c.MQTT_KEEPALIVE_SECONDS,
        )
        client.set_callback(self._on_message)
        try:
            try:
                client.connect(timeout=c.MQTT_TIMEOUT_SECONDS)
            except TypeError:
                client.connect()     # older umqtt.simple without "timeout"
            self._client = client
            self._restore_timeout()
            client.subscribe(self.topics["valve_set"], qos=1)
            self._restore_timeout()
            print("MQTT: connected to", s.MQTT_HOST, s.MQTT_PORT, "and listening for valve orders")
            return True
        except MQTTException as error:
            # CONNACK 4/5 = Mosquitto rejected MQTT_USER / MQTT_PASSWORD (check secrets.py and passwd)
            print("MQTT: broker rejected the connection, code", error.args[0] if error.args else "?")
        except (OSError, AssertionError) as error:
            print("MQTT: no answer from", s.MQTT_HOST, "-", repr(error))
        # The socket of a failed attempt must be closed too, or each retry leaks one (lwIP has few)
        try:
            if client.sock:
                client.sock.close()
        except Exception:
            pass
        self._client = None
        return False

    def publish(self, topic, payload):
        """QoS 1: waits for the broker's PUBACK. True if it arrived. On error the link is closed."""
        if self._client is None:
            return False
        try:
            # umqtt's wait_msg() leaves the socket WITHOUT timeout after every call: set it again each
            # time, or a half-open connection (router reboot) would block here forever
            self._restore_timeout()
            self._client.publish(topic, payload, qos=1)
            return True
        except (MQTTException, OSError, AssertionError) as error:
            print("MQTT: publish failed -", repr(error))
            self.close()
            return False

    def poll(self, max_messages=5):
        """Reads the orders that arrived (does not wait if there are none)."""
        if self._client is None:
            return
        try:
            for _ in range(max_messages):
                if self._client.check_msg() is None:
                    break
        except (MQTTException, OSError, AssertionError) as error:
            print("MQTT: connection lost -", repr(error))
            self.close()
            return
        self._restore_timeout()

    def close(self):
        if self._client is not None:
            try:
                self._client.sock.close()
            except Exception:
                pass
        self._client = None
