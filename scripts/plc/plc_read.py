#!/usr/bin/env python3
"""
plc_read.py — Quick diagnostic: just read and print whatever is in RobotCmd.
Run this to verify the PLC connection is working before running plc_live.py.

Usage:
  python3 ~/jetmax-control/scripts/plc/plc_read.py
"""

from pylogix import PLC
import time

PLC_IP   = "192.168.1.10"
TAG_NAME = "RobotCmd"

print(f"Reading '{TAG_NAME}' from {PLC_IP} every second. Ctrl+C to stop.\n")

with PLC() as comm:
    comm.IPAddress = PLC_IP
    comm.Micro800 = True
    while True:
        result = comm.Read(TAG_NAME)
        print(f"  {TAG_NAME} = {result.Value}  (status: {result.Status})")
        time.sleep(1)
