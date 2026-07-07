# JetMax Robotic Arm — Custom Control Scripts

Custom Python scripts and documentation for operating the **Hiwonder JetMax** robotic arm running on a **Jetson Nano**, developed for an industrial automation project integrating a conveyor belt and an **Allen Bradley Micro820 PLC**.

> **Base hardware/ROS packages:** [JetMaxRoboticArm on GitHub](https://github.com/JetMaxRoboticArm)

---

## Repo Layout

```text
jetmax-control/
├── scripts/
│   ├── arm/          wasd_control, hello_jetmax, pick/place helpers
│   ├── plc/          plc_live, plc_sim, plc_read, modb, watch
│   └── vision/       belt_vision, belt_vision_socket_tcp, stream
├── lib/              banner.py, paths.py
├── data/             saved_positions.json (gitignored, lives on robot)
├── docs/             setup guides and quick reference
├── assets/           printable cards and reference HTML
└── run.sh            shortcut launcher
```

---

## Quick Start (JetMax)

**1. One-time setup on the robot**

```bash
ssh -i ~/.ssh/jetmax_key hiwonder@100.65.198.107
bash -c "$(curl -fsSL https://raw.githubusercontent.com/Trylen22/jetmax-control/main/scripts/robot_setup.sh)" 2>/dev/null || ~/jetmax-control/scripts/robot_setup.sh
```

Or after cloning locally on the robot:

```bash
git clone https://github.com/Trylen22/jetmax-control.git ~/jetmax-control
~/jetmax-control/scripts/robot_setup.sh
```

**2. Run scripts**

```bash
cd ~/jetmax-control
./run.sh wasd
./run.sh belt
./run.sh plc-live
./run.sh plc-live-sim
```

Or directly:

```bash
source ~/ros/devel/setup.bash
python3 ~/jetmax-control/scripts/arm/wasd_control.py
```

**3. Update after changes**

```bash
cd ~/jetmax-control && git pull
```

---

## SSH

```bash
# Over Tailscale (anywhere)
ssh -i ~/.ssh/jetmax_key hiwonder@100.65.198.107

# Over PLC ethernet (on-site)
ssh hiwonder@192.168.1.50
```

Password: `hiwonder`

---

## Camera Feed

```text
http://100.65.198.107:8080/stream?topic=/usb_cam/image_rect_color
```

## Control Deck (web dashboard)

Modular menu with camera embed, script launch commands, and quick links:

```bash
./run.sh dashboard
# open http://100.65.198.107:8888/
```

Or start the custom stream:

```bash
./run.sh stream
# then open http://100.65.198.107:8080
```

---

## Hardware

- **Robot:** Hiwonder JetMax Standard
- **Controller:** NVIDIA Jetson Nano (Ubuntu 18.04 + ROS Melodic)
- **PLC:** Allen Bradley Micro820 @ `192.168.1.10`
- **JetMax eth0:** `192.168.1.50`
- **Tailscale:** `100.65.198.107`

---

## Documentation

| Doc | Purpose |
|---|---|
| [docs/COMMANDS.md](docs/COMMANDS.md) | Quick reference — SSH, scripts, ROS commands |
| [docs/SETUP.md](docs/SETUP.md) | Full setup — WiFi, Tailscale, ROS, arm movement |
| [docs/BOOT_SEQUENCE.md](docs/BOOT_SEQUENCE.md) | Boot sequence and WiFi auto-connect |
| [docs/SSH_LOGIN_CARD.md](docs/SSH_LOGIN_CARD.md) | Printable SSH/camera card |

---

## Dependencies

On the JetMax:

```bash
pip3 install pylogix pymodbus
```

ROS packages (pre-installed by Hiwonder): `jetmax_control`, `usb_cam`

---

## See Also

- [Hiwonder JetMax ROS repo](https://github.com/JetMaxRoboticArm)
- GitHub: [github.com/Trylen22/jetmax-control](https://github.com/Trylen22/jetmax-control)
