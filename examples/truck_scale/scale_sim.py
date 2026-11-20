"""A pretend truck-scale indicator, so examples/truck_scale.json runs with no hardware.

    python examples/truck_scale/scale_sim.py          (then start the panel)

It streams the usual continuous output, five lines a second:
    ST,GS,+0012340lb      ST = stable, US = unstable (in motion), OL = overload
over TCP on 127.0.0.1:4001; the panel's Serial control opens socket://127.0.0.1:4001.
A real indicator on a serial port sends the same kind of line: set the panel's
Port to its COM port and Settings to its baud rate (often 9600,n,8,1).

Trucks arrive by themselves: a loaded one drives on, settles, waits, drives off;
later it comes back empty. Type a weight and Enter to put a truck on yourself,
or 0 to clear the platform.
"""
import random
import socket
import threading
import time

CAPACITY = 120000      # lb; above this the indicator says OL


class Scale:
    def __init__(self):
        self.target = 0.0
        self.weight = 0.0
        self.lock = threading.Lock()

    def put(self, lb):
        with self.lock:
            self.target = float(lb)

    def step(self, dt):
        with self.lock:
            gap = self.target - self.weight
            if abs(gap) < 30:
                self.weight = self.target
            else:                                     # driving on/off: ramps, with bounce
                self.weight += gap * min(1.0, dt * 1.6) + random.uniform(-120, 120)
            moving = self.weight != self.target
            w = max(0, round(self.weight / 20) * 20)  # 20 lb divisions
        status = "OL" if w > CAPACITY else ("US" if moving else "ST")
        return f"{status},GS,{w:+08d}lb\r\n"


def traffic(scale, stop):
    """A truck now and then: loaded in, settle, off; later back empty."""
    yard = []
    while not stop.is_set():
        if yard and random.random() < 0.5:
            tare = yard.pop(0)                         # an unloaded truck leaves
            scale.put(tare)
        else:
            tare = random.randrange(24000, 34000, 20)
            yard.append(tare)
            scale.put(tare + random.randrange(8000, 46000, 20))
        stop.wait(random.uniform(14, 22))
        scale.put(0)
        stop.wait(random.uniform(6, 12))


def serve(scale, port=4001, stop=None, auto=True):
    stop = stop or threading.Event()
    if auto:
        threading.Thread(target=traffic, args=(scale, stop), daemon=True).start()
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", port))
    srv.listen(4)
    srv.settimeout(0.5)
    clients = []
    def pump():
        last = time.time()
        while not stop.is_set():
            time.sleep(0.2)
            now = time.time()
            line = scale.step(now - last).encode()
            last = now
            for c in list(clients):
                try:
                    c.sendall(line)
                except OSError:
                    clients.remove(c)
    threading.Thread(target=pump, daemon=True).start()
    while not stop.is_set():
        try:
            c, _ = srv.accept()
            clients.append(c)
        except socket.timeout:
            continue
    srv.close()


if __name__ == "__main__":
    s = Scale()
    print(__doc__.split("\n\n")[0])
    print("Serving on 127.0.0.1:4001. Ctrl+C to stop.")
    threading.Thread(target=serve, args=(s,), daemon=True).start()
    try:
        while True:
            txt = input().strip()
            if txt:
                try:
                    s.put(float(txt)); print(f"truck of {float(txt):.0f} lb on the scale")
                except ValueError:
                    print("type a weight in lb, or 0")
    except (KeyboardInterrupt, EOFError):
        pass
