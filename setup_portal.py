# Setup mode: the ESP32 creates its own WiFi network "CuidaTuAgua-XXXX" and serves a small page at
# http://192.168.4.1 where the user picks the home WiFi and types its password.
# Used the first time, or after holding BOOT 5 s. Ends with a restart.
import json
import machine
import network
import socket
import time

import wifi

AP_IP = "192.168.4.1"
MAX_REQUEST = 2048


def ap_name(serial):
    return "CuidaTuAgua-" + serial.strip()[-4:].upper()


def _escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def _unquote_plus(text):
    """Form fields arrive url-encoded ("Mi+Casa%21" -> "Mi Casa!"). MicroPython has no urllib."""
    text = text.replace("+", " ")
    out = bytearray()
    i = 0
    raw = text.encode()
    while i < len(raw):
        ch = raw[i]
        if ch == 0x25 and i + 2 < len(raw):   # "%41" -> "A"
            try:
                out.append(int(raw[i + 1:i + 3].decode(), 16))
                i += 3
                continue
            except ValueError:
                pass
        out.append(ch)
        i += 1
    return out.decode()


def parse_form(body):
    fields = {}
    for pair in body.split("&"):
        if "=" in pair:
            key, value = pair.split("=", 1)
            fields[_unquote_plus(key)] = _unquote_plus(value)
    return fields


def validate(ssid, password):
    """None if OK, otherwise the message for the user (WPA2 rules)."""
    if not ssid or len(ssid.encode()) > 32:
        return "Escribe el nombre de la red (máximo 32 caracteres)."
    if password and not 8 <= len(password) <= 63:
        return "La contraseña del WiFi debe tener entre 8 y 63 caracteres (o vacía si la red es abierta)."
    return None


PAGE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Cuida Tu Agua</title>
<style>body{{font-family:system-ui,sans-serif;max-width:420px;margin:24px auto;padding:0 16px;color:#0f2d3d}}
h1{{font-size:22px}}label{{display:block;margin-top:16px;font-weight:600}}
input,select{{width:100%;box-sizing:border-box;padding:12px;margin-top:6px;font-size:16px;border:1px solid #9bb;border-radius:8px}}
button{{width:100%;margin-top:24px;padding:14px;font-size:17px;border:0;border-radius:8px;background:#0b7fab;color:#fff}}
.err{{background:#fde8e8;color:#9b1c1c;padding:12px;border-radius:8px}}.ok{{background:#e6f6ec;color:#1e6b3a;padding:12px;border-radius:8px}}
small{{color:#567}}</style></head><body>
<h1>Conectar medidor a tu WiFi</h1><p><small>Equipo {serial} · firmware {fw}</small></p>{message}
<form method="post" action="/save">
<label>Red WiFi (solo 2.4 GHz)</label><select name="ssid_pick" onchange="document.getElementById('s').value=this.value">
<option value="">Elige una red…</option>{options}</select>
<label>Nombre de la red</label><input id="s" name="ssid" maxlength="32" required value="{ssid}">
<label>Contraseña</label><input name="password" type="password" maxlength="63" autocomplete="off">
<button type="submit">Guardar y conectar</button></form>
<p><small>Después de guardar, el equipo se reinicia. Vuelve a tu WiFi de siempre y regresa a la app.</small></p>
</body></html>"""

DONE = """<!doctype html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Cuida Tu Agua</title>
<style>body{{font-family:system-ui,sans-serif;max-width:420px;margin:24px auto;padding:0 16px;color:#0f2d3d}}
.ok{{background:#e6f6ec;color:#1e6b3a;padding:16px;border-radius:8px}}</style></head><body>
<h1>¡Listo!</h1><p class="ok">Guardado. El medidor se reinicia y se conecta a <b>{ssid}</b>.</p>
<p>1. Conecta tu teléfono a tu WiFi de siempre.<br>2. Vuelve a la app Cuida Tu Agua.<br>
3. En 1 minuto el medidor debe aparecer <b>Conectado</b>.</p>
<p>Si no se conecta (contraseña mal escrita), el equipo vuelve solo a este modo y verás otra vez la red {ap}.</p>
</body></html>"""


class Portal:
    def __init__(self, serial, password, firmware_version, port=80, last_error=None):
        self.serial = serial
        self.password = password
        self.fw = firmware_version
        self.port = port
        self.last_error = last_error
        self.networks = []
        self.saved = None   # (ssid, password) once the user submits the form

    # ---- HTTP -------------------------------------------------------------------------------
    def handle(self, conn):
        conn.settimeout(3)
        deadline = time.ticks_add(time.ticks_ms(), 8000)   # a slow client cannot hold the loop (watchdog)
        request = b""
        while b"\r\n\r\n" not in request and len(request) < MAX_REQUEST:
            if time.ticks_diff(time.ticks_ms(), deadline) > 0:
                raise OSError("request too slow")
            chunk = conn.recv(512)
            if not chunk:
                break
            request += chunk
        head, _, body = request.partition(b"\r\n\r\n")
        lines = head.decode().split("\r\n")
        method, path = (lines[0].split(" ") + ["", ""])[:2]
        length = 0
        for line in lines[1:]:
            if line.lower().startswith("content-length:"):
                length = min(int(line.split(":", 1)[1].strip() or 0), MAX_REQUEST)
        while len(body) < length:
            if time.ticks_diff(time.ticks_ms(), deadline) > 0:
                raise OSError("request too slow")
            chunk = conn.recv(512)
            if not chunk:
                break
            body += chunk
        status, content_type, text = self.route(method, path.split("?")[0], body[:length].decode())
        data = text.encode()
        conn.send("HTTP/1.1 {}\r\nContent-Type: {}\r\nContent-Length: {}\r\nCache-Control: no-store\r\n"
                  "Connection: close\r\n\r\n".format(status, content_type, len(data)).encode())
        conn.send(data)

    def route(self, method, path, body):
        html = "text/html; charset=utf-8"
        if method == "GET" and path == "/api/info":
            return "200 OK", "application/json", json.dumps(
                {"serial": self.serial, "fw": self.fw, "networks": self.networks})
        if method == "POST" and path in ("/save", "/api/wifi"):
            if path == "/api/wifi":
                try:
                    fields = json.loads(body)
                except ValueError:
                    fields = {}
                if not isinstance(fields, dict):
                    fields = {}
            else:
                fields = parse_form(body)
            ssid = str(fields.get("ssid") or fields.get("ssid_pick") or "").strip()
            password = str(fields.get("password") or "")
            error = validate(ssid, password)
            if error:
                if path == "/api/wifi":
                    return "400 Bad Request", "application/json", json.dumps({"error": error})
                return "400 Bad Request", html, self.page(error, ssid)
            self.saved = (ssid, password)
            if path == "/api/wifi":
                return "200 OK", "application/json", json.dumps({"saved": True, "ssid": ssid})
            return "200 OK", html, DONE.format(ssid=_escape(ssid), ap=_escape(ap_name(self.serial)))
        if method == "GET":
            # Any other address (phones probing for internet) gets the form: works as a captive page
            return "200 OK", html, self.page(self.last_error)
        return "405 Method Not Allowed", "text/plain", "method not allowed"

    def page(self, message=None, ssid=""):
        options = "".join('<option value="{0}">{0}</option>'.format(_escape(n)) for n in self.networks)
        box = '<p class="err">{}</p>'.format(_escape(message)) if message else ""
        return PAGE.format(serial=_escape(self.serial), fw=_escape(self.fw), message=box, options=options,
                           ssid=_escape(ssid))

    # ---- Loop (only on the ESP32) -------------------------------------------------------------
    def run(self, feed, led):
        self.networks = wifi.scan()     # before the AP starts: scanning while serving disconnects phones
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid=ap_name(self.serial), password=self.password, authmode=network.AUTH_WPA_WPA2_PSK)
        print("Setup: join WiFi", ap_name(self.serial), "and open http://" + AP_IP)

        server = socket.socket()
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", self.port))
        server.listen(2)
        server.settimeout(0.5)
        try:
            while self.saved is None:
                feed()
                led.value(1 - led.value())   # fast blink = setup mode
                try:
                    conn, _ = server.accept()
                except OSError:
                    continue
                try:
                    self.handle(conn)
                except (OSError, ValueError, IndexError, AttributeError, TypeError, UnicodeError) as error:
                    print("Setup: bad request", repr(error))
                finally:
                    conn.close()
        finally:
            server.close()

        wifi.save(*self.saved)
        print("Setup: WiFi saved:", self.saved[0], "- restarting")
        time.sleep(2)                    # let the "¡Listo!" page reach the phone
        ap.active(False)
        machine.reset()
