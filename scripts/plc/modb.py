"""
Do-More PLC — Modbus TCP holding register toolkit.

WHAT THIS FILE DOES
───────────────────
The Do-More PLC runs a Modbus TCP *server* on port 502.
This script is the *client* — it connects over Ethernet and asks the PLC
for the value of a specific 16-bit register using the Modbus protocol.

The PLC only exposes four Modbus memory blocks to external clients:
  MC  — Modbus Coils        (1-bit, read/write)
  MI  — Modbus Inputs       (1-bit, read only)
  MHR — Modbus Holding Regs (16-bit, read/write)  ← we use this one
  MIR — Modbus Input Regs   (16-bit, read only)

Normal internal PLC memory (R, D, V, I/O) is NOT visible over Modbus.
Ladder logic must copy values into MHR before Python can see them.

ADDRESS RULE
────────────
  MHR number == Modbus PDU address (both start at 0, no offset):
    MHR0  →  address=0
    MHR9  →  address=9   ← our counter lives here (shows as addr 8 in watch)

USAGE
─────
  python modb.py                          # poll MHR9 every 1 s
  python modb.py --ip 192.168.1.10        # same, explicit IP
  python modb.py watch  --ip 192.168.1.10 # print every register that changes
  python modb.py probe  --ip 192.168.1.10 # dump first 16 MHR + MIR words
  python modb.py dump   --ip 192.168.1.10 # dump all 256 holding registers
  python modb.py selftest                 # write + read back to prove the link

Details: MODBUS-DO-MORE-NOTES.md
"""

# ── Standard library ──────────────────────────────────────────────────────────
from __future__ import annotations   # allows "type | None" on older Python 3.9

import argparse   # parses command-line flags like --ip and --holding
import os         # used to read the MODB_DEVICE_ID environment variable
import time       # used for sleep() between polls
from dataclasses import dataclass    # clean way to group settings into one object
from typing import Callable          # used in the _with_client helper type hint

# ── Third-party ───────────────────────────────────────────────────────────────
# pymodbus is a pure-Python Modbus library.
# ModbusTcpClient opens a TCP socket to the PLC and sends/receives Modbus frames.
from pymodbus.client import ModbusTcpClient

# ── Constant ──────────────────────────────────────────────────────────────────
# The Modbus specification limits FC03 (read holding registers) to 125 registers
# per request. Asking for more returns an error. read_range() chunks around this.
MAX_READ = 125


# ── Configuration ─────────────────────────────────────────────────────────────
@dataclass
class Config:
    """
    All connection and behaviour settings in one place.
    A dataclass auto-generates __init__, so you can do Config(ip="10.0.0.1").
    Defaults match the lab setup; override via command-line flags.
    """

    ip: str = "192.168.1.10"   # PLC's static IP address
    port: int = 502             # Modbus TCP always uses port 502 (like HTTP uses 80)

    # The Modbus "unit id" (also called slave address or device id).
    # For a single PLC on a direct TCP connection, this is usually 1.
    # Some setups use 255. It rarely matters for Modbus TCP (unlike Modbus RTU serial).
    device_id: int = 1

    # Which MHR register to read in poll mode.
    # FC03 address == MHR number:  holding=9 reads MHR9.
    holding: int = 9

    # Seconds to wait between reads in poll mode.
    interval: float = 1.0

    # How many consecutive holding registers to scan in dump/watch mode.
    # 256 covers MHR0..MHR255. The PLC default block is 2048 words, but 256 is enough to find a counter.
    scan_words: int = 256

    # selftest writes a known value to this register, reads it back, then restores it.
    # Pick a register your ladder does NOT use (100 is usually safe).
    selftest_addr: int = 100
    selftest_value: int = 11111   # distinctive number easy to spot in Data View


# ── Helpers ───────────────────────────────────────────────────────────────────

def _env_device_id() -> int:
    """
    Read the unit id from the environment variable MODB_DEVICE_ID.
    If not set, default to 1.
    This lets you override the id without editing the file:
        $env:MODB_DEVICE_ID = "255"; python modb.py
    """
    return int(os.environ.get("MODB_DEVICE_ID", "1"))


def _connect(cfg: Config) -> ModbusTcpClient | None:
    """
    Open a TCP connection to the PLC's Modbus server.
    Returns the client object if successful, or None if the connection fails.

    Under the hood, ModbusTcpClient.connect() does a standard TCP handshake
    to cfg.ip:cfg.port (192.168.1.10:502).  If the PLC is off or the IP is
    wrong, connect() returns False and we return None so callers can print a
    helpful message instead of crashing.
    """
    c = ModbusTcpClient(cfg.ip, port=cfg.port)
    return c if c.connect() else None


def _read_holding(client: ModbusTcpClient, cfg: Config, start: int, count: int) -> list[int]:
    """
    Send one FC03 "read holding registers" request to the PLC.

    Parameters
    ──────────
    start  — first register address (0-based, == MHR number)
    count  — how many consecutive 16-bit registers to read (max 125)

    The PLC replies with 'count' 16-bit integers.
    rr.registers is a plain Python list of ints, e.g. [45, 0, 1100, ...].

    If the PLC returns a Modbus exception (e.g. illegal address), rr.isError()
    is True and we raise so the caller knows something went wrong.
    """
    rr = client.read_holding_registers(address=start, count=count, device_id=cfg.device_id)
    if rr.isError():
        raise RuntimeError(rr)
    return list(rr.registers)


def read_range(client: ModbusTcpClient, cfg: Config, start: int, total: int) -> list[int]:
    """
    Read 'total' holding registers starting at 'start', chunking into
    blocks of MAX_READ (125) to stay within the Modbus protocol limit.

    Example: read_range(client, cfg, 0, 256) makes three requests:
        FC03 addr=0   count=125  → registers 0..124
        FC03 addr=125 count=125  → registers 125..249
        FC03 addr=250 count=6    → registers 250..255
    All results are concatenated into one flat list.
    """
    out: list[int] = []
    while total > 0:
        n = min(total, MAX_READ)          # never ask for more than 125 at once
        out.extend(_read_holding(client, cfg, start, n))
        start += n                        # advance the start address
        total -= n                        # subtract the chunk we just read
    return out


def _with_client(cfg: Config, fn: Callable[[ModbusTcpClient], None]) -> None:
    """
    Open a connection, call fn(client), then always close — even if fn raises.
    This is a context-manager pattern without using 'with', useful when the
    inner function (fn) is defined elsewhere (e.g. a nested def in each command).
    """
    c = _connect(cfg)
    if not c:
        print(f"No connection to {cfg.ip}:{cfg.port}")
        return
    try:
        fn(c)      # run the actual command logic
    finally:
        c.close()  # always close the TCP socket


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_poll(cfg: Config) -> None:
    """
    POLL — read one register repeatedly and print the value each second.

    This is the simplest use case: watch a single MHR register live.
    Press Ctrl+C to stop.

    Output looks like:
        Polling MHR9 (FC03 addr 9) — Ctrl+C to stop
          46
          47
          48
    """
    # Open the TCP connection once and reuse it for every read.
    c = _connect(cfg)
    if not c:
        print(f"No connection to {cfg.ip}:{cfg.port}")
        return

    print(f"Polling MHR{cfg.holding} (FC03 addr {cfg.holding}) — Ctrl+C to stop\n")
    try:
        while True:
            # FC03 request: "give me 1 register at address cfg.holding"
            # The PLC reads its MHR block and replies with the 16-bit value.
            rr = c.read_holding_registers(address=cfg.holding, count=1, device_id=cfg.device_id)
            if rr.isError():
                print("Error:", rr)
            else:
                print(f"  {rr.registers[0]}")   # registers[0] because count=1

            time.sleep(cfg.interval)   # wait 1 second before the next request

    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        c.close()   # always close the socket on exit


def cmd_dump(cfg: Config) -> None:
    """
    DUMP — print every holding register address and its current value.

    Useful when you don't know which MHR your counter is in.
    Look for the row whose value matches what Data View shows.

    Output:
        FC03 holding 0..255 @ 192.168.1.10
          0  1100
          1  110
          ...
          8  47        ← this is likely your counter
    """
    def go(client: ModbusTcpClient) -> None:
        # Read all scan_words registers in one call (chunked internally).
        regs = read_range(client, cfg, 0, cfg.scan_words)
        for i, v in enumerate(regs):
            # i is the FC03 address, which equals the MHR number.
            print(f"  {i:3d}  {v}")

    print(f"FC03 holding 0..{cfg.scan_words - 1} @ {cfg.ip}\n")
    _with_client(cfg, go)


def cmd_probe(cfg: Config) -> None:
    """
    PROBE — quick sanity check showing the first 16 words of both MHR and MIR.

    MHR is read with FC03 (holding registers).
    MIR is read with FC04 (input registers) — a separate block, different values.

    The labeled line shows MHR0=value, MHR1=value, ... so you can match
    addresses to what you see in Do-More Designer Data View.

    To identify your counter's exact address:
      1. Force a unique value (e.g. 32100) into an MHR register in Data View.
      2. Run probe — find which MHRn shows 32100.
      3. That number is the FC03 address to use in Python.
    """
    def go(client: ModbusTcpClient) -> None:
        # Read first 16 holding registers (FC03)
        h = _read_holding(client, cfg, 0, 16)

        # Read first 16 input registers (FC04) — the MIR block
        ir = client.read_input_registers(address=0, count=16, device_id=cfg.device_id)

        print(f"FC03 MHR [0..15]: {h}")
        # Print labeled version so MHR number matches list index clearly
        print(f"      labeled:  {', '.join(f'MHR{n}={h[n]}' for n in range(16))}")

        if ir.isError():
            print(f"FC04 MIR:       {ir}")
        else:
            print(f"FC04 MIR [0..15]: {list(ir.registers)}")

    print(f"Probe @ {cfg.ip}:{cfg.port}  unit={cfg.device_id}\n")
    _with_client(cfg, go)


def cmd_watch(cfg: Config) -> None:
    """
    WATCH — scan all holding registers every second and print only the ones that changed.

    This is the most useful diagnostic command. If your ladder counter is working,
    you should see one address incrementing every second:
        addr   8: 45 -> 46
        addr   8: 46 -> 47

    If nothing prints, either:
      - The counter is in a native register (V, N, R) not in MHR — fix the ladder.
      - The PLC is not in RUN mode.
      - The project was not downloaded to the PLC.

    This command's output is also what modb_gui.py streams to drive the LED bar.

    HOW IT WORKS:
      1. Take a snapshot of all scan_words registers → prev
      2. Wait 1 second
      3. Take another snapshot → cur
      4. For each address where cur[i] != prev[i], print the change
      5. Replace prev with cur and repeat
    """
    def go(client: ModbusTcpClient) -> None:
        # First snapshot — baseline to compare against
        prev = read_range(client, cfg, 0, cfg.scan_words)

        while True:
            time.sleep(1.0)   # wait one PLC scan cycle worth of time

            # Second snapshot — compare to baseline
            cur = read_range(client, cfg, 0, cfg.scan_words)

            for i in range(min(len(prev), len(cur))):
                if prev[i] != cur[i]:
                    # This address changed — print old and new value.
                    # Format: "  addr   8: 45 -> 46"
                    # The GUI's regex parses this exact format.
                    print(f"  addr {i:3d}: {prev[i]} -> {cur[i]}")

            # Current snapshot becomes the new baseline for next iteration
            prev = cur

    print(f"Watching FC03 0..{cfg.scan_words - 1} (1s) — Ctrl+C to stop\n")
    c = _connect(cfg)
    if not c:
        print(f"No connection to {cfg.ip}:{cfg.port}")
        return
    try:
        go(c)
    except KeyboardInterrupt:
        print("Stopped.")
    finally:
        c.close()


def cmd_selftest(cfg: Config) -> None:
    """
    SELFTEST — prove the full read + write path is working.

    Steps:
      1. Read MHR0 (just to confirm reads work at all).
      2. Save the current value at selftest_addr (MHR100 by default).
      3. Write a known value (11111) to MHR100.
      4. Read it back — if it matches, write path works.
      5. Restore the original value so the PLC state is unchanged.

    If the write fails, it usually means the PLC's Modbus server is set
    to read-only, or the address is outside the allowed range.

    Use a selftest_addr that your ladder does NOT write to, otherwise the
    PLC might overwrite the test value before Python reads it back.
    """
    def go(client: ModbusTcpClient) -> None:
        a = cfg.selftest_addr    # shorthand — the register address we'll test
        v = cfg.selftest_value   # the value we'll write to prove it works

        # Step 1: basic read of MHR0 to confirm the read path is alive
        r0 = client.read_holding_registers(address=0, count=1, device_id=cfg.device_id)
        print(f"read MHR0: {r0.registers[0] if not r0.isError() else r0}")

        # Step 2: save whatever is currently at selftest_addr so we can restore it
        oldb = client.read_holding_registers(address=a, count=1, device_id=cfg.device_id)
        old = oldb.registers[0] if not oldb.isError() else None

        # Step 3: write the test value
        # FC16 "write multiple registers" — pymodbus uses this for write_registers()
        wr = client.write_registers(address=a, values=[v], device_id=cfg.device_id)
        if wr.isError():
            print(f"write MHR{a} failed: {wr}")
            return

        # Step 4: read it back and compare
        rb = client.read_holding_registers(address=a, count=1, device_id=cfg.device_id)
        got = rb.registers[0] if not rb.isError() else None
        ok = got == v
        print(f"write/read MHR{a}: {'OK' if ok else 'FAIL'} (wrote {v}, read {got})")

        # Step 5: restore the original value so the PLC is undisturbed
        if old is not None and ok:
            client.write_registers(address=a, values=[old], device_id=cfg.device_id)
            print(f"restored MHR{a} -> {old}")

    print(f"Self-test @ {cfg.ip}  MHR{cfg.selftest_addr} = {cfg.selftest_value}\n")
    _with_client(cfg, go)


# ── Argument parsing ──────────────────────────────────────────────────────────

def parse_args() -> tuple[Config, str]:
    """
    Parse command-line arguments and build a Config object.

    The 'command' positional argument selects which function to run.
    All flags (--ip, --port, etc.) override the defaults in Config.

    Returns (cfg, command_name) so main() can look up the right function.
    """
    p = argparse.ArgumentParser(description="Do-more Modbus TCP — MHR tools")

    # Positional optional argument — which mode to run (default: poll)
    p.add_argument(
        "command",
        nargs="?",          # "?" means 0 or 1 occurrences → optional
        default="poll",
        choices=("poll", "dump", "watch", "selftest", "probe"),
    )

    # Network settings — override the defaults baked into Config
    p.add_argument("--ip",   default="192.168.1.10",  help="PLC IP address")
    p.add_argument("--port", type=int, default=502,   help="Modbus TCP port (almost always 502)")

    # Modbus unit id — for a single PLC on TCP this is usually 1; try 255 if needed
    p.add_argument("--device-id", type=int, default=None, help="default: MODB_DEVICE_ID env var or 1")

    # Which MHR register to poll (FC03 address = MHR number)
    p.add_argument("--holding",   type=int, default=None, help="FC03 addr = MHR number (default 9)")

    args = p.parse_args()

    # Build the Config, applying CLI overrides where provided
    cfg = Config(
        ip=args.ip,
        port=args.port,
        # device_id: use CLI value if given, otherwise check env var, otherwise 1
        device_id=args.device_id if args.device_id is not None else _env_device_id(),
        # holding: use CLI value if given, otherwise default to 9 (MHR9)
        holding=args.holding if args.holding is not None else 9,
    )
    return cfg, args.command


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    """
    Parse arguments, look up the matching command function, and run it.

    The cmds dict maps the string name to the actual function so we avoid
    a long if/elif chain. cmds[cmd](cfg) calls the function with config.
    """
    cfg, cmd = parse_args()

    # Dispatch table: command name → function to call
    cmds = {
        "poll":     cmd_poll,      # read one register forever
        "dump":     cmd_dump,      # print all registers once
        "watch":    cmd_watch,     # print changes every second
        "selftest": cmd_selftest,  # write + read back to verify the link
        "probe":    cmd_probe,     # dump first 16 MHR + MIR words with labels
    }
    cmds[cmd](cfg)


# Only run main() when this file is executed directly (not when imported).
# e.g.  python modb.py watch  →  runs
#       from modb import read_range  →  does NOT run main()
if __name__ == "__main__":
    main()
