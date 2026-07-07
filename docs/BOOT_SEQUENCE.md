# JetMax Boot Sequence — What's Actually Happening

## The Problem in Plain English

The JetMax was designed to be a WiFi hotspot out of the box.
Every time it boots, it races to grab the WiFi radio for its own hotspot
before anything else can use it. Our WiFi connection script has to fight
that process every single time.

---

## The Boot Race (What Was Going Wrong)

```
POWER ON
   │
   ▼
┌─────────────────────────────────────────────────────────┐
│  systemd starts ALL services roughly at the same time   │
└─────────────────────────────────────────────────────────┘
   │
   ├──────────────────────────┬────────────────────────────
   │                          │
   ▼                          ▼
hw_wifi.service          latech-wifi.service
(Hiwonder's hotspot)     (our WiFi script)
   │                          │
   │  runs hw_wifi.py         │  kills wpa_supplicant
   │  which calls create_ap   │  kills create_ap
   │  which runs hostapd      │  kills hostapd
   │  which grabs wlan0       │  brings wlan0 down/up
   │  and puts it in AP mode  │  starts wpa_supplicant
   │                          │
   ▼                          ▼
 wlan0 = HOTSPOT ❌        wlan0 = CONNECTING... ✓
                                │
                    hw_wifi restarts (Restart=always)
                    every 5 seconds ❌
                                │
                    grabs wlan0 back
                                │
                    wpa_supplicant gets kicked off
                                │
                    stuck in SCANNING forever ❌
```

---

## Why It Worked Manually But Not On Boot

When you ran the connection script by hand, `hw_wifi.service` had
already been killed and was sitting idle. The radio was free.

On boot, `hw_wifi.service` was still alive with `Restart=always`,
meaning it would respawn every 5 seconds no matter how many times
we killed it. Our script would get 5 seconds of peace, start
authenticating, then get interrupted mid-handshake.

---

## The EAP Authentication Timeline

LaTechWPA2 uses WPA2-Enterprise (PEAP/MSCHAPv2).
This is more complex than a home WiFi password — it's a full
certificate handshake with the university's RADIUS server.

```
wpa_supplicant starts
   │
   ├─ ~1s   Scans for LaTechWPA2 network
   ├─ ~2s   Associates with access point (MAC layer)
   ├─ ~3s   PEAP outer tunnel established
   ├─ ~4s   MSCHAPv2 inner auth (username/password sent encrypted)
   ├─ ~5s   RADIUS server validates credentials
   ├─ ~6s   COMPLETED ✓  ←  wpa_state = COMPLETED
   │
   └─ dhclient runs AFTER this ← critical timing
         │
         ├─ DHCPDISCOVER sent to university DHCP server
         ├─ ~1-3s  DHCPOFFER received
         ├─ DHCPREQUEST sent
         ├─ DHCPACK received → IP assigned (138.47.156.46)
         └─ bound ✓

Total time from boot to usable WiFi: ~30-45 seconds
```

---

## Why dhclient Kept Failing

Even when wpa_supplicant finished authenticating, `dhclient` was
running too early (before COMPLETED state) or the university DHCP
server was slow to respond. This caused the endless DHCPDISCOVER loop.

Our fix: poll `wpa_state` every second and only run `dhclient`
AFTER seeing `COMPLETED`. This makes the timing adaptive instead
of relying on a fixed sleep.

---

## The Fix — What We Did

```
POWER ON
   │
   ▼
systemd starts services
   │
   ├── hw_wifi.service ──► MASKED (symlinked to /dev/null)
   │                       Cannot start. Ever. ✓
   │
   └── latech-wifi.service
          │
          ▼
       /usr/local/bin/latech-connect.sh runs
          │
          ├─ kill any lingering wpa_supplicant/hostapd/create_ap
          ├─ delete stale socket file /run/wpa_supplicant/wlan0
          ├─ bring wlan0 down then up (clean state)
          ├─ start wpa_supplicant in background
          │
          └─ POLL wpa_state every 1 second (max 60s)
                │
                ├─ SCANNING → keep waiting
                ├─ DISCONNECTED → keep waiting
                ├─ COMPLETED → run dhclient ✓
                │
                └─ dhclient gets IP from university DHCP
                      │
                      └─ resolv.conf set to 8.8.8.8
                            │
                            └─ tailscaled starts with internet ✓
                                  │
                                  └─ Tailscale connects to relay
                                        │
                                        └─ Remote SSH available ✓
```

---

## Boot Timing Summary

| Time after power on | Event |
|---|---|
| 0s | systemd starts |
| ~5s | latech-wifi.service starts |
| ~7s | wpa_supplicant scanning |
| ~12s | EAP authentication completes |
| ~13s | dhclient gets IP |
| ~15s | resolv.conf set |
| ~20s | tailscaled connects |
| ~30s | Remote SSH available via Tailscale |

---

## What "Masking" hw_wifi.service Does

```
DISABLED service:
  systemd won't start it automatically
  BUT another service or script CAN still start it manually
  AND Restart=always means it respawns if something triggers it

MASKED service:
  /lib/systemd/system/hw_wifi.service
        │
        └──► symlinked to /dev/null
  
  Any attempt to start it returns:
  "Failed to start hw_wifi.service: Unit is masked."
  Nothing can start it. Period.
```

To undo masking: `sudo systemctl unmask hw_wifi.service`

---

## Files Involved

| File | Purpose |
|---|---|
| `/usr/local/bin/latech-connect.sh` | The WiFi connection script |
| `/etc/systemd/system/latech-wifi.service` | systemd service that runs the script on boot |
| `/etc/wpa_supplicant/latech.conf` | WiFi credentials and EAP config |
| `/lib/systemd/system/hw_wifi.service` | Hiwonder's hotspot service (now masked) |
| `/home/hiwonder/hiwonder-toolbox/hw_wifi.py` | Hiwonder's hotspot script (untouched, just masked) |
