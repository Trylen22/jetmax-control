# JetMax SSH Login Card

---

## Remote Access (Anywhere via Tailscale)

```
ssh -i ~/.ssh/jetmax_key hiwonder@100.65.198.107
```

---

## Local Access (Ethernet / On-Site)

```
ssh hiwonder@192.168.1.50
```

Password: `hiwonder`

---

## Camera Feed (Browser)

```
http://100.65.198.107:8080/stream?topic=/usb_cam/image_rect_color
```

## Repo (on robot)

```
~/jetmax-control
git clone https://github.com/Trylen22/jetmax-control.git ~/jetmax-control
cd ~/jetmax-control && ./run.sh wasd
```

---

## Contact

Trevor Sparks — tbs024@latech.edu — 318-312-1782

GitHub: github.com/Trylen22/jetmax-control
