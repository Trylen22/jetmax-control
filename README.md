# JetMax Robotic Arm — Custom Control Scripts

Custom Python scripts and documentation for operating the **Hiwonder JetMax** robotic arm running on a **Jetson Nano**, developed for an industrial automation project integrating a conveyor belt and an **Allen Bradley Micro820 PLC**.

> **Base hardware/ROS packages:** [JetMaxRoboticArm on GitHub](https://github.com/JetMaxRoboticArm)

---

## What's in This Repo

| File | Purpose |
|---|---|
| `hello_jetmax.py` | Basic arm movement — good first test |
| `wasd_control.py` | WASD keyboard jogging with position save/recall |
| `plc_sim.py` | Keyboard-triggered pick-and-place simulator |
| `plc_live.py` | Live Allen Bradley Micro820 integration via EtherNet/IP |
| `plc_read.py` | Diagnostic — reads a PLC tag and prints it every second |
| `belt_vision.py` | Vision-guided pick from a conveyor belt using color detection |
| `modb.py` | Modbus TCP toolkit (Do-More PLC reference) |
| `watch.py` | Modbus register watcher |
| `SETUP.md` | Full setup guide — SSH, WiFi, Tailscale, ROS, arm movement |
| `COMMANDS.md` | Quick reference for all commands and scripts |
| `BOOT_SEQUENCE.md` | How the JetMax boots and how WiFi auto-connect works |

---

## Hardware Setup

- **Robot:** Hiwonder JetMax Standard
- **Controller:** NVIDIA Jetson Nano (running Ubuntu 18.04 + ROS Melodic)
- **PLC:** Allen Bradley Micro820
- **Network:**
  - `eth0` → `192.168.1.50` (PLC ethernet network)
  - `wlan0` → LaTechWPA2 (university WiFi, internet + Tailscale)
- **Remote Access:** Tailscale VPN (`100.65.198.107`)

---

## Quick Start

**1. SSH into the JetMax**
```bash
# Over Tailscale (anywhere)
ssh -i ~/.ssh/jetmax_key hiwonder@100.65.198.107

# Over ethernet (on PLC network)
ssh hiwonder@192.168.1.50
```

**2. Source ROS**
```bash
source ~/ros/devel/setup.bash
```

**3. Run a script**
```bash
python3 ~/wasd_control.py        # keyboard jog
python3 ~/belt_vision.py         # vision pick loop
python3 ~/plc_live.py            # live PLC integration
python3 ~/plc_live.py --sim      # PLC sim (no PLC needed)
```

---

## belt_vision.py

Parks the arm at a watch position over the conveyor belt, detects a **green sticker** on a block using HSV color detection, calculates the real-world position from the pixel offset, and picks the block.

- Returns to watch position after each pick
- Goes home after 30 seconds of no block detected
- Ctrl+C → suction off, arm homes cleanly

**Tuning constants (top of file):**

| Variable | Value | Purpose |
|---|---|---|
| `WATCH_POS` | `(-160, 0, 210)` | Hover position over belt |
| `PICK_Z` | `125` | Grab height |
| `TOOL_OFFSET_X` | `-37` | Camera-to-sucker X correction |
| `TOOL_OFFSET_Y` | `5` | Camera-to-sucker Y correction |
| `MM_PER_PIXEL` | `0.25` | Scale factor at z=210 height |
| `IDLE_TIMEOUT` | `30` | Seconds idle before going home |

---

## PLC Integration (Allen Bradley Micro820)

`plc_live.py` polls a tag named `RobotCmd` (INT) from the PLC via EtherNet/IP every 500ms. When the value changes, the corresponding arm sequence runs.

| Value | Action |
|---|---|
| `0` | Idle |
| `5` | Go home |
| `6` | Pick block_pos_1 → drop zone |
| `7` | Drop zone → return to block_pos_1 |

**Tell the PLC programmer:** Create an INT tag named `RobotCmd` in their ladder. Use a `MOV` instruction to write a command value when a condition triggers. Use a One Shot (OSR) to fire it once per event.

---

## wasd_control.py Keys

| Key | Action |
|---|---|
| W / S | Move forward / back (Y axis) |
| A / D | Move left / right (X axis) |
| R / F | Move up / down (Z axis) |
| Space | Go home |
| P | Save current position |
| G | Go to a saved position |
| L | List saved positions |
| Q | Quit |

---

## Dependencies

On the JetMax (Jetson Nano):
```bash
pip3 install pylogix   # Allen Bradley EtherNet/IP
```

ROS packages (pre-installed by Hiwonder):
- `jetmax_control`
- `usb_cam`
- `apriltag`

---

## See Also

- [Hiwonder JetMax ROS repo](https://github.com/JetMaxRoboticArm)
- Full setup walkthrough: `SETUP.md`
- Troubleshooting + boot sequence: `BOOT_SEQUENCE.md`
