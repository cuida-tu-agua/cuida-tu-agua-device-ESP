# Telemetry readings waiting to be sent. If WiFi or the broker are down, they wait here (RAM).
# Pure Python: also tested on a PC.


class ReadingBuffer:
    def __init__(self, max_items, max_liters_per_reading=100):
        self._items = []   # (ts, lpm, vol, total), oldest first
        self._max = max_items
        self._max_vol = max_liters_per_reading

    def __len__(self):
        return len(self._items)

    def add(self, ts, lpm, vol, total):
        if len(self._items) >= self._max:
            self._make_room()
        self._items.append((ts, lpm, vol, total))

    def _make_room(self):
        # Merge the two oldest: same liters, one reading less. If that would be too big, drop the oldest.
        a, b = self._items[0], self._items[1]
        if a[2] + b[2] <= self._max_vol:
            self._items[1] = (b[0], max(a[1], b[1]), a[2] + b[2], b[3])
        self._items.pop(0)

    def peek(self):
        return self._items[0] if self._items else None

    def pop(self):
        return self._items.pop(0)
