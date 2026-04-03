"""
Watch the Do-More PLC for register changes over Modbus TCP.

Every second, this script reads all 256 holding registers from the PLC
and prints any address whose value changed since the last read.

The PLC is the SERVER  — it sits at 192.168.1.10:502 and waits for requests.
Python is the CLIENT   — it connects, asks for data, and prints what changed.

Because MHR9 (our counter) increments once per second in ladder logic,
you should see one line like this every second:

    addr   8: 45 -> 46

Run:
    python watch.py
"""

import time
from pymodbus.client import ModbusTcpClient

# ── Settings ──────────────────────────────────────────────────────────────────

PLC_IP   = "192.168.1.10"   # IP address of the Do-More PLC
PORT     = 502               # Modbus TCP always uses port 502
UNIT_ID  = 1                 # Modbus unit id — 1 for a single PLC on TCP
N_REGS   = 256               # how many holding registers to scan each second

# ── Connect ───────────────────────────────────────────────────────────────────

# Open a TCP socket to the PLC's Modbus server.
# This is the same as connecting to any server — just on port 502 instead of 80.
client = ModbusTcpClient(PLC_IP, port=PORT)
client.connect()

print(f"Connected to {PLC_IP}:{PORT}")
print("Watching for register changes — Ctrl+C to stop\n")

# ── First snapshot ────────────────────────────────────────────────────────────

# Read all N_REGS holding registers as a baseline to compare against.
# FC03 = "read holding registers" — the standard Modbus function for MHR.
# The PLC replies with a list of 16-bit integers (one per register).
result = client.read_holding_registers(address=0, count=N_REGS, device_id=UNIT_ID)
prev = list(result.registers)   # e.g. [1100, 110, 0, 0, ..., 47, 0, ...]

# ── Watch loop ────────────────────────────────────────────────────────────────

try:
    while True:
        time.sleep(1.0)   # wait one second, then check again

        # Read the registers again — this is a fresh snapshot.
        result = client.read_holding_registers(address=0, count=N_REGS, device_id=UNIT_ID)
        cur = list(result.registers)

        # Compare every address against the previous snapshot.
        # If the value changed, print the address and the old → new values.
        for i in range(N_REGS):
            if cur[i] != prev[i]:
                print(f"  addr {i:3d}: {prev[i]} -> {cur[i]}")

        # The current snapshot becomes the new baseline for next second.
        prev = cur

except KeyboardInterrupt:
    print("\nStopped.")
finally:
    client.close()   # always close the TCP socket cleanly
