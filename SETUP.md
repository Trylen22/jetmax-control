# JetMax Robotic Arm — Setup Guide

A step-by-step guide to getting your JetMax connected and ready for development.

---

## What You Need

- JetMax robotic arm (Hiwonder, powered by Jetson Nano)
- PC running Linux
- Ethernet cable
- Power adapter (12V 5A)

---

## Step 1 — Power On the JetMax

1. Insert the two WiFi antennas and tighten them
2. Install the rubber suction cups on the four base corners
3. Connect the 12V power adapter to the expansion board
4. Flip the switch on the expansion board to **ON**
5. Wait for **3 beeps** — that means it booted successfully

On boot, JetMax launches a WiFi hotspot with a name starting with **`HW`**.

---

## Step 2 — First-Time Ethernet Setup (One-Time Only)

The JetMax's ethernet port ships with no IP assigned. You need to set it once over WiFi, then ethernet works permanently after that.

### 2a — Connect your PC to the JetMax hotspot

On your PC, connect to the `HW...` WiFi network.

Default credentials:
- **Username:** `hiwonder`
- **Password:** `hiwonder`

### 2b — SSH in over WiFi

```bash
ssh hiwonder@192.168.149.1
```

### 2c — Assign a static IP to the JetMax ethernet port

Set it immediately (active until reboot):
```bash
sudo ifconfig eth0 192.168.55.1 netmask 255.255.255.0 up
```

Make it persist across reboots:
```bash
echo -e "\nauto eth0\niface eth0 inet static\n    address 192.168.55.1\n    netmask 255.255.255.0" | sudo tee -a /etc/network/interfaces
```

Verify it was written correctly:
```bash
cat /etc/network/interfaces
```

---

## Step 3 — Configure Your PC's Ethernet Port

On your PC, assign a static IP on the ethernet interface so it can talk to the JetMax.

Find your ethernet interface name:
```bash
ip link show
```
Look for something like `enp12s0` (not `lo`, `wlp...`, `docker0`, or `tailscale0`).

Set a static IP:
```bash
sudo ip addr add 192.168.55.100/24 dev enp12s0
sudo ip link set enp12s0 up
```

> Replace `enp12s0` with your actual interface name.

To make this permanent, set it via your network manager GUI:
- **Method:** Manual
- **Address:** `192.168.55.100`
- **Netmask:** `255.255.255.0`
- **Gateway:** `192.168.55.1`

---

## Step 4 — Connect via Ethernet Going Forward

Disconnect from the JetMax hotspot and reconnect your PC to your home WiFi.
Plug in the ethernet cable between your PC and the JetMax.

Verify the connection:
```bash
ping -c 3 192.168.55.1
```

You should see 0% packet loss. Then SSH in:
```bash
ssh hiwonder@192.168.55.1
```

- **Username:** `hiwonder`
- **Password:** `hiwonder`

You now have internet on your PC via WiFi and a direct connection to the JetMax over ethernet simultaneously.

---

## Key IPs at a Glance

| Connection | IP |
|---|---|
| JetMax WiFi hotspot (AP mode) | `192.168.149.1` |
| JetMax ethernet (after setup) | `192.168.55.1` |
| Your PC ethernet | `192.168.55.100` |
| JetMax Tailscale (anywhere) | `100.65.198.107` |

---

## Remote Access via Tailscale

The JetMax is on Tailscale — you can SSH into it from anywhere in the world, no ethernet or hotspot needed.

```bash
ssh -i ~/.ssh/jetmax_key hiwonder@100.65.198.107
```

**If the JetMax loses WiFi or reboots**, Tailscale and the WiFi connection need to be re-established. See the WiFi section below.

### Connecting JetMax to LaTechWPA2 (if it loses WiFi)

The JetMax's built-in hotspot (`create_ap`) locks the WiFi radio. Kill it first, then connect manually:

```bash
# Kill the hotspot stack
sudo pkill -f create_ap && sudo pkill -f hostapd && sudo pkill -f dnsmasq

# Connect via wpa_supplicant (bypasses NetworkManager)
sudo bash -c 'cat > /tmp/wpa.conf << EOF
network={
    ssid="LaTechWPA2"
    key_mgmt=WPA-EAP
    eap=PEAP
    identity="YOUR_USERNAME"
    password="YOUR_PASSWORD"
    phase2="auth=MSCHAPV2"
}
EOF'

sudo wpa_supplicant -B -i wlan0 -c /tmp/wpa.conf
sleep 5
sudo dhclient wlan0
```

Test internet:
```bash
curl -I https://tailscale.com
```

Then bring Tailscale back up:
```bash
sudo tailscale up
```

### SSH Config for Remote Access

Add this to `~/.ssh/config` on any machine:
```
Host jetmax
    HostName 100.65.198.107
    User hiwonder
    IdentityFile ~/.ssh/jetmax_key
```

Then just:
```bash
ssh jetmax
```

---

## Useful Tools

Install these on your PC if needed:
```bash
sudo apt install nmap arp-scan -y
```

Scan for devices on the ethernet subnet:
```bash
sudo nmap -sn 192.168.55.0/24
```

Force-close a frozen SSH session:
```
Enter, then type: ~.
```

---

## Project Repositories

Cloned into `/home/wavyjones/Desktop/JETMAX/`:

| Repo | Purpose |
|---|---|
| `jetmax_buildin_funcs` | Core library — servos, control, sensors |
| `jetmax_demos` | Demo scripts — color sorting, tracking, etc. |

Official docs: [docs.hiwonder.com/projects/JetMax](https://docs.hiwonder.com/projects/JetMax/en/latest/)

---

## Next Steps

- Explore what's on the JetMax: `ls ~/ros/src/`
- Write a basic movement script
- Upload files via `scp`: `scp myfile.py hiwonder@192.168.55.1:~/`

---

## PLC Pick-and-Place System

### Final Architecture (with Do-More PLC)

```
PLC ladder logic
  └─ writes command value (1/2/3...) into MHR register
       └─ watch.py / modb.py polls register every 1s
            └─ value changes → dispatch(value)
                 └─ arm executes pick-and-place sequence
```

### Files

| File | Purpose |
|---|---|
| `modb.py` | Modbus TCP toolkit — poll, watch, dump, probe, selftest against PLC |
| `watch.py` | Simple register watcher — prints every MHR that changes |
| `plc_sim.py` | **Development stand-in** — keyboard input replaces PLC register |

### PLC Connection Details

- **PLC:** Do-More (BRX or similar)
- **Protocol:** Modbus TCP, port 502
- **PLC IP:** `192.168.1.10` (static)
- **Register:** MHR9 (FC03 address 9) — PLC ladder copies command value here
- **Unit ID:** 1

> PLC internal memory (R, D, V, I/O) is NOT visible over Modbus.
> Ladder logic must explicitly copy values into MHR registers.

### Running the PLC Simulator (no PLC needed)

```bash
source ~/ros/devel/setup.bash && python3 ~/plc_sim.py
```

Type a number and press Enter — the arm executes the sequence:

| Command | Action |
|---|---|
| `1` | Pick from position A (front-left) |
| `2` | Pick from position B (front-center) |
| `3` | Pick from position C (front-right) |
| `4` | Place at drop zone |
| `5` | Home |
| `0` | E-Stop / Home |
| `q` | Quit |

### Swapping in the Real PLC

When the PLC is available, replace the input loop in `plc_sim.py` with Modbus polling. Only one section changes — everything else (sequences, dispatcher, arm control) stays identical:

```python
# Replace this block in plc_sim.py:
while not rospy.is_shutdown():
    raw = input("Enter command: ").strip()
    dispatch(int(raw))

# With this (using modb.py's connection helpers):
from modb import _connect, _read_holding, Config
cfg = Config(ip="192.168.1.10")
client = _connect(cfg)
prev = 0
while not rospy.is_shutdown():
    time.sleep(0.5)
    val = _read_holding(client, cfg, start=9, count=1)[0]
    if val != prev and val != 0:
        dispatch(val)
        prev = val
```

### Tuning Pick Positions

Edit the position constants at the top of `plc_sim.py`:

```python
HOME      = (  0, -160,  200)
PICK_A    = (-80, -180,  120)
PICK_B    = (  0, -200,  120)
PICK_C    = ( 80, -180,  120)
DROP_ZONE = (  0, -130,  130)
```

Use `wasd_control.py` to manually jog the arm to each position and read the x/y/z values, then paste them in.

---

## Moving the Arm — How It Works

### Architecture

The JetMax runs **ROS (Robot Operating System)**. All movement goes through a central control node called `/jetmax_control`. You send it position commands by publishing to a ROS topic — you never call the hardware directly.

```
Your script → /jetmax/command topic → /jetmax_control node → servos → arm moves
```

### Why not use the hiwonder Python library directly?

The installed `hiwonder` library (`hiwonder-1.0-py3.6.egg`) has a bug in `jetmax.py`:

```python
for p in pulses:
    if p < 0:
        raise ValueError("{} Out of limit range".format(pulses[i]))  # 'i' is undefined here!
```

This causes an `UnboundLocalError` whenever inverse kinematics returns a negative pulse value. **Use ROS topics instead** — it's cleaner and the correct approach anyway.

### The Coordinate System

The arm uses x/y/z in **millimeters**:

| Axis | Direction |
|---|---|
| x | Left (negative) / Right (positive) |
| y | **Negative** = forward (toward the map). The arm faces the negative y direction. |
| z | Up (positive) / Down (negative) |

> Important: y is **negative** when pointing forward. The arm's default resting position is around `(0, -163, 213)`. Sending positive y values will fail silently or move the wrong way.

Check the arm's current position at any time:
```bash
source ~/ros/devel/setup.bash
rostopic echo /jetmax/status -n 1
```

### Safe Working Ranges (approximate)

| Axis | Safe Range |
|---|---|
| x | -150 to 150 |
| y | -250 to -100 |
| z | 50 to 220 |

### Running ROS Scripts

Always source the ROS environment first:
```bash
source ~/ros/devel/setup.bash && python3 ~/yourscript.py
```

Or add it to `.bashrc` so it's automatic:
```bash
echo "source ~/ros/devel/setup.bash" >> ~/.bashrc
```

### Minimal Movement Script Template

```python
#!/usr/bin/env python3
import rospy
import time
from jetmax_control.msg import SetJetMax

rospy.init_node('my_script', anonymous=True)
pub = rospy.Publisher('/jetmax/command', SetJetMax, queue_size=1)

# Always wait for the control node to connect first
while pub.get_num_connections() == 0:
    time.sleep(0.1)

def move(x, y, z, duration=1.5):
    msg = SetJetMax()
    msg.x = float(x)
    msg.y = float(y)
    msg.z = float(z)
    msg.duration = float(duration)
    pub.publish(msg)
    time.sleep(duration + 0.5)  # wait for move to complete

# Example: move to home
move(0, -160, 200)
```

### Quick One-Off Movement (no script needed)

```bash
source ~/ros/devel/setup.bash
rostopic pub -1 /jetmax/command jetmax_control/SetJetMax '{x: 0.0, y: -160.0, z: 150.0, duration: 2.0}'
```

### Available ROS Topics

| Topic | Purpose |
|---|---|
| `/jetmax/command` | Send position commands (x, y, z, duration) |
| `/jetmax/status` | Read current arm position |
| `/jetmax/joint1/command` | Control individual joint 1 |
| `/jetmax/joint2/command` | Control individual joint 2 |
| `/jetmax/joint3/command` | Control individual joint 3 |

List all topics:
```bash
rostopic list
```
