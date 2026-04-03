# JetMax Quick Reference

## SSH

```bash
# Over Tailscale (anywhere, preferred)
ssh -i ~/.ssh/jetmax_key hiwonder@100.65.198.107

# Over PLC ethernet (when physically connected to 192.168.1.x network)
ssh hiwonder@192.168.1.50

# Old ethernet address (before PLC network change)
ssh hiwonder@192.168.55.1
```

Password: `hiwonder`

---

## File Transfer

```bash
# Upload file to JetMax (Tailscale)
scp -i ~/.ssh/jetmax_key myfile.py hiwonder@100.65.198.107:~/

# Upload file to JetMax (ethernet)
scp myfile.py hiwonder@192.168.1.50:~/

# Download file from JetMax
scp -i ~/.ssh/jetmax_key hiwonder@100.65.198.107:~/somefile.py ./
```

---

## Scripts (run from inside SSH)

Always source ROS first:
```bash
source ~/ros/devel/setup.bash
```

| Script | Command | What it does |
|---|---|---|
| `hello_jetmax.py` | `python3 ~/hello_jetmax.py` | Moves arm through 4 positions |
| `wasd_control.py` | `python3 ~/wasd_control.py` | WASD keyboard controller, P=save position |
| `plc_sim.py` | `python3 ~/plc_sim.py` | PLC simulator — type 5/6/7 to trigger sequences |
| `plc_live.py` | `python3 ~/plc_live.py` | Live Allen Bradley Micro820 polling via EtherNet/IP |
| `plc_live.py --sim` | `python3 ~/plc_live.py --sim` | Same but keyboard-driven (no PLC needed) |
| `belt_vision.py` | `python3 ~/belt_vision.py` | Vision-guided green block pick from conveyor belt |
| `plc_read.py` | `python3 ~/plc_read.py` | Diagnostic — reads RobotCmd tag from PLC every second |

Combined (ROS required for all arm scripts):
```bash
source ~/ros/devel/setup.bash && python3 ~/wasd_control.py
source ~/ros/devel/setup.bash && python3 ~/plc_sim.py
source ~/ros/devel/setup.bash && python3 ~/plc_live.py
source ~/ros/devel/setup.bash && python3 ~/belt_vision.py

# plc_read.py does NOT need ROS
python3 ~/plc_read.py
```

---

## One-Off Arm Movement

```bash
source ~/ros/devel/setup.bash
rostopic pub -1 /jetmax/command jetmax_control/SetJetMax '{x: 0.0, y: -160.0, z: 200.0, duration: 1.5}'
```

## Check Arm Position

```bash
source ~/ros/devel/setup.bash
rostopic echo /jetmax/status -n 1
```

---

## WiFi (if it drops)

```bash
sudo /usr/local/bin/latech-connect.sh
```

---

## Networking / Routing (if Tailscale can't connect)

If the JetMax is also connected to the PLC ethernet network, the default route
may point through eth0 (no internet) instead of wlan0. Fix it:

```bash
# Check current routes
ip route show

# Fix default route to go through WiFi
sudo ip route del default
sudo ip route add default via 138.47.152.1 dev wlan0

# Fix DNS
echo "nameserver 8.8.8.8" | sudo tee /etc/resolv.conf

# Then restart Tailscale
sudo tailscale up
```

Network layout:
- `eth0`  → `192.168.1.50`   (PLC network, no internet)
- `wlan0` → `138.47.156.46`  (LaTechWPA2, internet)
- PLC     → `192.168.1.10`
- Router  → `192.168.1.1`

---

## PLC Commands (Allen Bradley Micro820)

The PLC programmer writes an INT to the `RobotCmd` tag:

| Value | Action |
|---|---|
| `0` | Idle / do nothing |
| `5` | Go home |
| `6` | Pick block_pos_1 → drop zone |
| `7` | Drop zone → return to block_pos_1 |

```bash
# Test PLC connection (no ROS needed)
python3 ~/plc_read.py
```

---

## Services

```bash
# Check WiFi service
sudo systemctl status latech-wifi.service

# Check WiFi logs
sudo journalctl -u latech-wifi.service --no-pager | tail -20

# Restart WiFi
sudo systemctl restart latech-wifi.service

# Check Tailscale
sudo tailscale status
sudo tailscale up
```

---

## Files on This PC

| File | Purpose |
|---|---|
| `SETUP.md` | Full setup guide from scratch |
| `BOOT_SEQUENCE.md` | How the boot/WiFi system works |
| `COMMANDS.md` | This file |
| `SSH_KEY_INFO.md` | SSH key details |
| `hello_jetmax.py` | Basic movement script |
| `wasd_control.py` | Keyboard controller |
| `plc_sim.py` | PLC simulator / pick-and-place |
| `plc_live.py` | Live Allen Bradley EtherNet/IP integration |
| `plc_read.py` | PLC tag diagnostic reader |
| `belt_vision.py` | Vision-guided conveyor pick |
| `modb.py` | Modbus TCP toolkit for Do-More PLC |
| `watch.py` | PLC register watcher |

## Files on JetMax (~/)

| File | Purpose |
|---|---|
| `~/hello_jetmax.py` | Basic movement script |
| `~/wasd_control.py` | Keyboard controller |
| `~/plc_sim.py` | PLC simulator |
| `~/plc_live.py` | Live Allen Bradley Micro820 integration |
| `~/plc_read.py` | PLC tag diagnostic reader |
| `~/belt_vision.py` | Vision-guided conveyor belt pick |
| `~/saved_positions.json` | Saved arm positions (wasd_control P key) |
| `/usr/local/bin/latech-connect.sh` | WiFi connect script |
| `/etc/wpa_supplicant/latech.conf` | WiFi credentials |
| `/etc/network/interfaces` | Static eth0 IP config (192.168.1.50) |
| `~/ros/src/` | All ROS packages |

## belt_vision.py Tuning

| Variable | Value | Purpose |
|---|---|---|
| `WATCH_POS` | `(-160, 0, 210)` | Arm hover position over belt |
| `PICK_Z` | `125` | Z height to grab block |
| `TOOL_OFFSET_X` | `-37` | Camera-to-sucker X correction |
| `TOOL_OFFSET_Y` | `5` | Camera-to-sucker Y correction |
| `MM_PER_PIXEL` | `0.25` | Pixel to mm scale at z=210 |
| `IDLE_TIMEOUT` | `30` | Seconds before going home |
