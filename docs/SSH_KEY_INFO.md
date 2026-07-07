# JetMax SSH Key Info

## Key Location
- **Private key:** `~/.ssh/jetmax_key`
- **Public key:** `~/.ssh/jetmax_key.pub`

## Public Key
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFp3LbdHUg4+4VkFKdDPnCHDBWKwHV3GRUFHlifqkJDc jetmax
```

## Key Fingerprint
```
SHA256:spn3SIX/YPE0W7uCjvdLkFTwNKGNIZ2ZiYydl695B/0 jetmax
```

## SSH Config Entry
```
Host jetmax
    HostName 192.168.55.1
    User hiwonder
    IdentityFile ~/.ssh/jetmax_key
```

## Connect
```bash
ssh jetmax
```

## Copy key to a new JetMax (if needed)
```bash
ssh-copy-id -i ~/.ssh/jetmax_key.pub hiwonder@192.168.55.1
```
