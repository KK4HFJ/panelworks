"""
A pretend Victron GX device (Cerbo GX / Venus GX) on Modbus TCP, so the solar_battery
example runs without hardware. It answers the com.victronenergy.system registers on
Unit-ID 100, with an off-grid system behind it: 3.2 kW of PV, a 48 V / 10 kWh battery,
house loads with a well pump that cycles, and a generator on relay 1.

    python -m panelworks --simulator solar_battery             # listens on 127.0.0.1:5021

A simulated day passes in 10 minutes (it starts at 07:30), so you see the sun come up,
the battery fill, and the evening loads pull it down. Tick "Generator" on the panel to
start the generator (it writes register 806, relay 1, as on a real GX).

Registers (holding, Unit-ID 100), as on a real GX:
    806  Relay 1 state            uint16   read/write (0 off, 1 on)
    817  AC consumption L1        uint16   W
    820  Grid L1                  int16    W   (0: off-grid)
    823  Genset L1                int16    W
    840  Battery voltage          uint16   V x10
    841  Battery current          int16    A x10   (+ charging)
    842  Battery power            int16    W       (+ charging)
    843  Battery state of charge  uint16   %
    844  Battery state            uint16   0 idle, 1 charging, 2 discharging
    846  Battery time to go       uint16   s / 100  (0 while charging)
    850  PV - DC-coupled power     uint16   W
    851  PV - DC-coupled current  int16    A x10
    860  DC system power          int16    W
Registers 800-866 all answer (unlisted ones read 0); anything else is refused.
"""
import asyncio
import math
import random
import sys
import threading
import time

from pymodbus.server import StartTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

PORT = 5021
UNIT = 100
DAY_SECONDS = 600            # one simulated day, in real seconds
CAPACITY_WH = 10240          # 51.2 V x 200 Ah
FC_BLOCK = {3: "hr", 6: "hr", 16: "hr"}


def s16(v):
    """A signed value as the uint16 a register carries."""
    return int(round(v)) & 0xFFFF


class GX:
    def __init__(self, soc=55.0, start_hour=7.5):
        self.lock = threading.Lock()
        self.hr = {a: 0 for a in range(800, 867)}
        self.soc = soc
        self.clock = start_hour * 3600           # simulated seconds since midnight
        self.cloud = 1.0
        self.pump_t = 0.0

    # ---- the Modbus side -------------------------------------------------------------
    def put(self, addr, value):
        with self.lock:
            self.hr[addr] = int(value) & 0xFFFF

    def get(self, addr):
        with self.lock:
            return self.hr[addr]

    async def action(self, function_code, start_address, address, count, current_registers, set_values):
        if FC_BLOCK.get(function_code) != "hr":
            return None
        if set_values is not None:
            with self.lock:
                for i, v in enumerate(set_values):
                    self.hr[address + i] = int(v) & 0xFFFF
            return None
        with self.lock:
            for i in range(count):
                if address + i in self.hr:
                    current_registers[address - start_address + i] = self.hr[address + i]
        return None

    def device(self):
        # pymodbus wants something in every table; a GX only has holding registers, so the
        # coil, input and input-register tables get one placeholder each (never read here).
        one_bit = [SimData(0, values=[False], datatype=DataType.BITS)]
        return SimDevice(id=UNIT, simdata=(one_bit, list(one_bit),
                                           [SimData(800, values=[0] * 67, datatype=DataType.REGISTERS)],
                                           [SimData(0, values=[0], datatype=DataType.REGISTERS)]),
                         action=self.action)

    # ---- the physics ---------------------------------------------------------------
    def hour(self):
        return (self.clock / 3600) % 24

    def step(self, dt):
        speed = 86400 / DAY_SECONDS
        self.clock += dt * speed
        h = self.hour()
        self.cloud = min(1.0, max(0.35, self.cloud + random.uniform(-0.04, 0.04)))
        sun = math.sin(math.pi * (h - 6) / 14) if 6 < h < 20 else 0.0
        pv = 3200 * max(0.0, sun) ** 1.4 * self.cloud
        # house: base load, fridge cycling, evening lights, and a well pump every 75 s
        self.pump_t = (self.pump_t + dt) % 75
        ac = 170 + (120 if (self.clock // 900) % 5 < 2 else 0) + (320 if 18 <= h < 23 else 0) \
            + (900 if self.pump_t < 20 else 0) + random.uniform(-15, 15)
        dc = 35 + random.uniform(-3, 3)
        gen = 3000.0 if self.get(806) == 1 else 0.0
        batt = pv * 0.97 + gen - ac / 0.92 - dc
        if self.soc >= 100 and batt > 0:                 # full: the charger backs the PV off
            pv = max(0.0, pv - batt / 0.97)
            batt = 0.0
        if self.soc <= 3 and batt < 0:                   # empty: the inverter shuts the loads off
            ac, batt = 0.0, 0.0
        wh = batt * dt * speed / 3600                    # energy in or out over this step, simulated time
        self.soc = min(100.0, max(0.0, self.soc + wh / CAPACITY_WH * 100))
        volts = 47.6 + 6.4 * self.soc / 100 + (batt / 50) * 0.012
        amps = batt / volts
        state = 1 if batt > 20 else 2 if batt < -20 else 0
        ttg = (CAPACITY_WH * self.soc / 100) / -batt * 3600 / 100 if state == 2 else 0
        with self.lock:
            self.hr[817] = int(ac)
            self.hr[820] = 0
            self.hr[823] = s16(gen)
            self.hr[840] = int(volts * 10)
            self.hr[841] = s16(amps * 10)
            self.hr[842] = s16(batt)
            self.hr[843] = int(round(self.soc))
            self.hr[844] = state
            self.hr[846] = min(65535, int(ttg))
            self.hr[850] = int(pv)
            self.hr[851] = s16(pv / max(volts, 1) * 10)
            self.hr[860] = s16(dc)

    def simulate(self, stop=None, period=0.5, log=False):
        last = time.time()
        shown = -1
        while stop is None or not stop.is_set():
            time.sleep(period)
            now = time.time()
            self.step(now - last)
            last = now
            if log and int(self.hour() * 2) != shown:
                shown = int(self.hour() * 2)
                print(f"  {int(self.hour()):02d}:{int(self.hour() % 1 * 60):02d}  PV {self.get(850):4d} W  "
                      f"load {self.get(817):4d} W  SOC {self.get(843):3d} %  "
                      f"generator {'on' if self.get(806) == 1 else 'off'}")


def serve(gx, port=PORT):
    """Run the Modbus TCP server (blocks). Safe to call from a thread."""
    asyncio.set_event_loop(asyncio.new_event_loop())
    StartTcpServer(context=gx.device(), address=("127.0.0.1", port))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    gx = GX()
    gx.step(0.01)
    threading.Thread(target=gx.simulate, kwargs={"log": True}, daemon=True).start()
    print(f"Pretend Victron GX on 127.0.0.1:{port} (Modbus TCP, Unit-ID {UNIT}). "
          f"A day takes {DAY_SECONDS // 60} minutes. Ctrl+C to stop.")
    serve(gx, port)
