# JetMax Quick Reference

Repo on the robot: `~/jetmax-control`

## SSH

```bash
# Over Tailscale (anywhere, preferred)
ssh -i ~/.ssh/jetmax_key hiwonder@100.65.198.107

# Over PLC ethernet (when physically connected to 192.168.1.x network)
ssh hiwonder@192.168.1.50
```

Password: `hiwonder`

---

## Repo Setup / Update

```bash
# First time on the robot
git clone https://github.com/Trylen22/jetmax-control.git ~/jetmax-control
~/jetmax-control/scripts/robot_setup.sh

# After changes are pushed
cd ~/jetmax-control && git pull
```

---

## Run Scripts

Preferred (handles ROS sourcing):

```bash
cd ~/jetmax-control
./run.sh wasd
./run.sh belt
./run.sh plc-live
./run.sh plc-live-sim
./run.sh plc-read
./run.sh stream
```

| Script | `./run.sh` command | What it does |
|---|---|---|
| `wasd_control.py` | `wasd` | WASD keyboard controller, P=save position |
| `hello_jetmax.py` | `hello` | Moves arm through 4 positions |
| `plc_sim.py` | `plc-sim` | PLC simulator — type 5/6/7 to trigger sequences |
| `plc_live.py` | `plc-live` | Live Allen Bradley Micro820 polling via EtherNet/IP |
| `plc_live.py --sim` | `plc-live-sim` | Same but keyboard-driven (no PLC needed) |
| `belt_vision.py` | `belt` | Vision-guided green block pick from conveyor belt |
| `belt_vision_socket_tcp.py` | `belt-tcp` | Belt vision controlled by PLC over TCP socket |
| `plc_read.py` | `plc-read` | Diagnostic — reads RobotCmd tag from PLC every second |
| `stream.py` | `stream` | MJPEG camera stream on port 8080 |
| `modb.py` | `modb ...` | Modbus TCP toolkit |
| `watch.py` | `watch` | Modbus register watcher |

Direct paths (if needed):

```bash
source ~/ros/devel/setup.bash
python3 ~/jetmax-control/scripts/arm/wasd_control.py
python3 ~/jetmax-control/scripts/plc/plc_sim.py
python3 ~/jetmax-control/scripts/plc/plc_live.py
python3 ~/jetmax-control/scripts/vision/belt_vision.py

# plc_read.py does NOT need ROS
python3 ~/jetmax-control/scripts/plc/plc_read.py
```

---

## Camera

```text
http://100.65.198.107:8080/stream?topic=/usb_cam/image_rect_color
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

## Network

| Device | IP |
|---|---|
| JetMax eth0 | `192.168.1.50` |
| PLC | `192.168.1.10` |
| Router | `192.168.1.1` |
| Tailscale | `100.65.198.107` |

---

## Data Files (on robot, gitignored)

| Path | Purpose |
|---|---|
| `~/jetmax-control/data/saved_positions.json` | Saved arm positions (wasd_control P key) |
| `~/jetmax-control/data/jetmax_coord_log.csv` | Pick/place coordinate log |

---

## belt_vision.py Tuning

| Variable | Value | Purpose |
|---|---|---|
| `WATCH_POS` | `(-160, 0, 210)` | Hover position over belt |
| `PICK_Z` | `125` | Grab height |
| `TOOL_OFFSET_X` | `-37` | Camera-to-sucker X correction |
| `TOOL_OFFSET_Y` | `5` | Camera-to-sucker Y correction |
| `MM_PER_PIXEL` | `0.25` | Scale factor at z=210 height |
| `IDLE_TIMEOUT` | `360` | Seconds idle before going home |

---

## PLC Commands (plc_live / plc_sim)

| Value | Action |
|---|---|
| `0` | Idle |
| `5` | Home |
| `6` | Pick block_pos_1 → drop zone |
| `7` | Drop zone → return block_pos_1 |

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

## Repo Structure

| Path | Purpose |
|---|---|
| `scripts/arm/` | Arm control and pick/place helpers |
| `scripts/plc/` | PLC integration and Modbus tools |
| `scripts/vision/` | Camera, belt vision, streaming |
| `lib/` | Shared banner and path helpers |
| `docs/` | Setup guides and reference cards |
| `assets/` | Printable HTML/txt reference |
