# Electrovalve through a relay (HU-019..021). Its state is saved in valve.json so that after a
# power cut the valve comes back as the user left it (a closed valve stays closed).
import machine

import storage
from protocol import OPEN, CLOSED

FILE = "valve.json"


class Valve:
    def __init__(self, pin_number, closed_level, default_state):
        self._pin = machine.Pin(pin_number, machine.Pin.OUT)
        self._closed_level = closed_level
        saved = storage.load(FILE, {}) or {}
        state = saved.get("state")
        self.last_command = saved.get("commandId")
        self._apply(state if state in (OPEN, CLOSED) else default_state)

    def _apply(self, state):
        self._pin.value(self._closed_level if state == CLOSED else 1 - self._closed_level)
        self.state = state

    def execute(self, command_id, action):
        """Obeys an order from the app. The same order twice (MQTT may repeat it) is done once."""
        if command_id != self.last_command:
            self._apply(CLOSED if action == "CLOSE" else OPEN)
            self.last_command = command_id
            storage.save(FILE, {"state": self.state, "commandId": command_id})
            print("Valve:", self.state, "(order", command_id + ")")
        return self.state
