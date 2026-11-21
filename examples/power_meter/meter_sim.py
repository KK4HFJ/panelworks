"""
A pretend power meter on Modbus TCP, so the power_meter example (and the tests) run
without hardware. Run it, then open examples/power_meter.json.

    python -m panelworks --simulator power_meter            # listens on 127.0.0.1:5020

Register map (addresses 0-based, unit id 1):
    hr 0      volts x10          u16         e.g. 2304 = 230.4 V
    hr 1      amps x100          u16
    hr 2-3    power W            f32 CDAB    (word-swapped, like many real meters)
    hr 4-5    energy Wh          u32
    hr 10     load setpoint %    u16         read/write: the panel's slider writes it
    hr 20-23  name               str4        "PM-1"
    ir 0      temperature x10    i16         input register
    co 0      relay              coil        read/write: the panel's checkbox writes it
Addresses not listed are refused (Modbus "illegal address"), like a real meter.
"""
import asyncio
import math
import random
import struct
import sys
import threading
import time

from pymodbus.server import StartTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

PORT = 5020
FC_BLOCK = {1: "co", 5: "co", 15: "co", 2: "di", 3: "hr", 6: "hr", 16: "hr", 4: "ir"}


class Meter:
    """The meter's registers, as plain dicts the physics thread and the server share."""

    def __init__(self):
        self.lock = threading.Lock()
        self.regs = {"hr": {0: 2304, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 10: 50,
                            20: 0x504D, 21: 0x2D31, 22: 0, 23: 0},
                     "ir": {0: 215}, "co": {0: 1}, "di": {0: 0}}
        self.energy = 0.0

    def get(self, block, addr):
        with self.lock:
            return self.regs[block][addr]

    def put(self, block, addr, values):
        with self.lock:
            for i, v in enumerate(values):
                self.regs[block][addr + i] = int(v)

    async def action(self, function_code, start_address, address, count, current_registers, set_values):
        """pymodbus calls this for every request: answer reads from the model, record writes."""
        block = FC_BLOCK.get(function_code)
        if block is None:
            return None
        if set_values is not None:                       # a write: remember it
            self.put(block, address, [int(bool(v)) if block == "co" else v for v in set_values])
            return None
        with self.lock:
            for i in range(count):
                if address + i in self.regs[block]:
                    current_registers[address - start_address + i] = int(self.regs[block][address + i])
        return None

    def device(self, unit=1):
        def sd(block):
            # one SimData per run of consecutive addresses, so the gaps are invalid addresses
            kind = DataType.BITS if block in ("co", "di") else DataType.REGISTERS
            conv = (lambda v: bool(v)) if kind == DataType.BITS else int
            out, addrs = [], sorted(self.regs[block])
            run = [addrs[0]]
            for a in addrs[1:]:
                if a == run[-1] + 1:
                    run.append(a)
                else:
                    out.append(SimData(run[0], values=[conv(self.regs[block][x]) for x in run], datatype=kind))
                    run = [a]
            out.append(SimData(run[0], values=[conv(self.regs[block][x]) for x in run], datatype=kind))
            return out
        return SimDevice(id=unit, simdata=(sd("co"), sd("di"), sd("hr"), sd("ir")), action=self.action)

    def simulate(self, stop=None, period=0.5):
        """Change the readings like a real load would. The relay (co 0) and setpoint (hr 10) drive it."""
        t = 0.0
        while stop is None or not stop.is_set():
            t += period
            relay = bool(self.get("co", 0))
            setpoint = self.get("hr", 10)
            volts = 230 + 3 * math.sin(t / 7) + random.uniform(-0.4, 0.4)
            amps = max(0.0, setpoint / 100 * 12 + random.uniform(-0.2, 0.2)) if relay else 0.0
            power = volts * amps
            self.energy += power * period / 3600
            hi, lo = struct.unpack(">HH", struct.pack(">f", power))
            e = int(self.energy)
            self.put("hr", 0, [int(volts * 10), int(amps * 100), lo, hi, (e >> 16) & 0xFFFF, e & 0xFFFF])
            self.put("ir", 0, [int((21.5 + power / 400 + random.uniform(-0.1, 0.1)) * 10) & 0xFFFF])
            time.sleep(period)


def serve(meter, port=PORT):
    """Run the Modbus TCP server (blocks). Safe to call from a thread."""
    asyncio.set_event_loop(asyncio.new_event_loop())
    StartTcpServer(context=meter.device(), address=("127.0.0.1", port))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    meter = Meter()
    threading.Thread(target=meter.simulate, daemon=True).start()
    print(f"Pretend power meter on 127.0.0.1:{port} (Modbus TCP, unit 1). Ctrl+C to stop.")
    serve(meter, port)
