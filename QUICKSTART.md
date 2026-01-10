# Network Policy - Quick Start Guide

Get your network policy system running in 5 minutes!

## Prerequisites

- Debian-based Linux system (Debian 11+, Ubuntu 20.04+)
- Root/sudo access
- Python 3.7 or higher

## Installation

### Option 1: From Debian Package

```bash
# Build the package
./build-deb.sh

# Install
sudo dpkg -i ../network-policy_*.deb
sudo apt-get install -f  # Fix any missing dependencies
```

### Option 2: Manual Installation

```bash
# Install dependencies
sudo apt install python3 python3-toml network-manager modemmanager \
                 iproute2 nftables systemd iputils-ping

# Copy files
sudo cp -r usr/local/lib/network-policy /usr/local/lib/
sudo cp usr/local/bin/network-policy-* /usr/local/bin/
sudo chmod +x /usr/local/bin/network-policy-*
sudo cp etc/systemd/system/*.service /etc/systemd/system/
sudo mkdir -p /usr/share/doc/network-policy
sudo cp usr/share/doc/network-policy/* /usr/share/doc/network-policy/

# Reload systemd
sudo systemctl daemon-reload
```

## Configuration

1. **Create configuration directory:**
   ```bash
   sudo mkdir -p /data
   ```

2. **Copy and edit the example configuration:**
   ```bash
   sudo cp /usr/share/doc/network-policy/example-config.toml /data/network-policy.toml
   sudo nano /data/network-policy.toml
   ```

3. **Minimal configuration example:**
   ```toml
   [system]
   hostname = "my-gateway"
   
   [ethernet.eth0]
   enabled = true
   priority = 10
   method = "dhcp"
   
   [firewall]
   enabled = true
   default_input_policy = "drop"
   allow_established = true
   allow_loopback = true
   
   [[firewall.input_rules]]
   comment = "Allow SSH"
   service = "ssh"
   action = "accept"
   
   [firewall.services.ssh]
   protocol = "tcp"
   ports = [22]
   ```

4. **Validate your configuration:**
   ```bash
   network-policy-validate /data/network-policy.toml
   ```

## Start Services

```bash
# Enable and start initialization service
sudo systemctl enable network-policy-init.service
sudo systemctl start network-policy-init.service

# Check status
sudo systemctl status network-policy-init.service

# Enable and start health monitoring
sudo systemctl enable network-policy-healthcheck.service
sudo systemctl start network-policy-healthcheck.service

# Check status
sudo systemctl status network-policy-healthcheck.service
```

## Verify Everything Works

```bash
# Check system status
network-policy-ctl status

# View firewall rules
network-policy-ctl firewall

# View logs
sudo journalctl -u network-policy-init.service -f
sudo journalctl -u network-policy-healthcheck.service -f
```

## Common Tasks

### Add a WiFi Interface

Edit `/data/network-policy.toml`:

```toml
[wifi.wlan0]
enabled = true
priority = 20
ssid = "MyNetwork"
psk = "MyPassword123"
method = "dhcp"
```

Reload:
```bash
network-policy-ctl reload
```

### Configure Firewall Rules

Edit `/data/network-policy.toml`:

```toml
[firewall.address_groups.trusted]
addresses = ["192.168.1.0/24", "10.0.0.0/8"]

[firewall.services.web]
protocol = "tcp"
ports = [80, 443]

[[firewall.input_rules]]
comment = "Allow web from trusted networks"
source_groups = ["trusted"]
service = "web"
action = "accept"
```

Reload:
```bash
network-policy-ctl reload
```

### Set Up LTE Failover

Edit `/data/network-policy.toml`:

```toml
[ethernet.eth0]
enabled = true
priority = 10  # Primary
method = "dhcp"

[lte.wwan0]
enabled = true
priority = 30  # Backup
device = "eg25-g"
apn = "internet"

[healthcheck]
interval_sec = 30
timeout_sec = 5
probe_targets = ["8.8.8.8", "1.1.1.1"]
failures_before_down = 3
successes_before_up = 2
```

Reload and check:
```bash
network-policy-ctl reload
network-policy-ctl status
```

The health monitor will automatically switch to LTE when Ethernet fails!

## Troubleshooting

### Configuration Not Loading

```bash
# Validate configuration
network-policy-validate /data/network-policy.toml

# Check for syntax errors
python3 -c "import toml; print(toml.load(open('/data/network-policy.toml')))"
```

### Services Not Starting

```bash
# Check service logs
sudo journalctl -u network-policy-init.service -n 50
sudo journalctl -u network-policy-healthcheck.service -n 50

# Check systemd status
sudo systemctl status network-policy-init.service
sudo systemctl status network-policy-healthcheck.service
```

### Network Not Working

```bash
# Check interface status
ip addr show
ip route show

# Check NetworkManager connections
nmcli connection show
nmcli device status

# Check firewall rules
sudo nft list table inet network-policy

# Check routing tables
ip rule list
ip route show table 100  # First interface table
```

### Health Monitor Not Working

```bash
# Check if daemon is running
ps aux | grep network-policy-healthcheck

# Check socket
ls -la /run/network-policy.sock

# Manual status check
network-policy-ctl status

# Check logs
sudo journalctl -u network-policy-healthcheck.service -f
```

## Next Steps

- Read the full documentation in `/usr/share/doc/network-policy/`
- Customize your firewall rules
- Set up multiple interfaces with priorities
- Configure WireGuard VPN
- Set up user accounts and SSH keys

## Getting Help

- Check logs: `sudo journalctl -u network-policy-* -f`
- Validate config: `network-policy-validate /data/network-policy.toml`
- Check status: `network-policy-ctl status`
- View firewall: `network-policy-ctl firewall`

For more detailed information, see:
- `/usr/share/doc/network-policy/README.md` - Complete user manual
- `/usr/share/doc/network-policy/example-config.toml` - Fully commented example
