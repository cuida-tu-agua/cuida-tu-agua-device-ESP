# YF-S201 flow sensor: counts pulses with a hardware interrupt.
# Liters are computed from PULSES (whole numbers), so nothing is lost to rounding.
import machine


class FlowMeter:
    def __init__(self, pin_number, calibration_factor):
        self._pulses = 0
        self.total_pulses = 0
        self._pulses_per_liter = calibration_factor * 60  # 7.5 x 60 = 450 pulses per liter
        pin = machine.Pin(pin_number, machine.Pin.IN, machine.Pin.PULL_UP)
        try:
            # hard=True: counted right inside the interrupt, so no pulse is lost while WiFi or the
            # flash keep the CPU busy (the handler only adds 1, which is allowed in a hard IRQ)
            pin.irq(trigger=machine.Pin.IRQ_FALLING, handler=self._on_pulse, hard=True)
        except TypeError:
            pin.irq(trigger=machine.Pin.IRQ_FALLING, handler=self._on_pulse)
        self._pin = pin  # keep a reference so the interrupt is not lost

    def _on_pulse(self, _pin):
        # Runs inside the interrupt: only add 1, nothing else (no prints, no allocations)
        self._pulses += 1

    def take(self):
        """Pulses since the last call (and resets the counter)."""
        state = machine.disable_irq()  # a pulse cannot sneak in between read and reset
        pulses = self._pulses
        self._pulses = 0
        machine.enable_irq(state)
        self.total_pulses += pulses
        return pulses

    def liters(self, pulses):
        return pulses / self._pulses_per_liter

    @property
    def total_liters(self):
        return self.total_pulses / self._pulses_per_liter
