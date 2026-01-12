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
cfg status

# View firewall rules
cfg firewall

# View configuration
cfg get system.hostname
cfg get ethernet.eth0.method

# View logs
sudo journalctl -u network-policy-init.service -f
sudo journalctl -u network-policy-healthcheck.service -f
```

## Configuration Workflow

**Important:** The `cfg set` and `cfg del` commands save changes to the configuration file but do NOT automatically apply them. This allows you to:

1. Make multiple related changes safely (e.g., changing interface method from DHCP to static requires setting address, gateway, etc.)
2. Verify configuration is valid before applying
3. Avoid partial configurations that could break networking

**Workflow:**
```bash
# 1. Make your changes (multiple values in one command for atomicity)
cfg set ethernet.eth0.method=static ethernet.eth0.address="192.168.1.100/24" ethernet.eth0.gateway="192.168.1.1"

# OR make changes individually
cfg set ethernet.eth0.method=static
cfg set ethernet.eth0.address="192.168.1.100/24"
cfg set ethernet.eth0.gateway="192.168.1.1"

# 2. Validate configuration
network-policy-validate /data/network-policy.toml

# 3. Apply changes
cfg reload

# OR: Set and apply immediately (use with caution)
cfg set ethernet.eth0.enabled=true --apply
```

**Pro Tips:**
- Use multiple assignments in one command to ensure related changes are applied together
- Delete multiple items at once: `cfg del ethernet.eth1 wifi.wlan0`
- Delete list items by value: `cfg del system.ntp_servers.[]="1.2.3.4"`

## Common Tasks

### Add a WiFi Interface

Using the cfg command (all values in one atomic operation):

```bash
cfg set wifi.wlan0.enabled=true wifi.wlan0.priority=20 wifi.wlan0.ssid="MyNetwork" wifi.wlan0.psk="MyPassword123" wifi.wlan0.method=dhcp

# Apply the changes
cfg reload
```

Or make changes individually:

```bash
cfg set wifi.wlan0.enabled=true
cfg set wifi.wlan0.priority=20
cfg set wifi.wlan0.ssid="MyNetwork"
cfg set wifi.wlan0.psk="MyPassword123"
cfg set wifi.wlan0.method=dhcp

# Apply the changes
cfg reload
```

Or edit `/data/network-policy.toml`:

```toml
[wifi.wlan0]
enabled = true
priority = 20
ssid = "MyNetwork"
psk = "MyPassword123"
method = "dhcp"
```

After making changes, apply them:
```bash
cfg reload
```

### Configure IPv6 on Interfaces

Using the cfg command for dual-stack configuration (IPv4 + IPv6):

```bash
# Dual-stack with DHCP for both IPv4 and IPv6
cfg set ethernet.eth0.enabled=true ethernet.eth0.priority=10 ethernet.eth0.method=dhcp ethernet.eth0.ipv6_method=auto

# Static IPv4 and IPv6 (single addresses)
cfg set ethernet.eth1.enabled=true ethernet.eth1.priority=15 \
        ethernet.eth1.method=static ethernet.eth1.address="192.168.1.100/24" ethernet.eth1.gateway="192.168.1.1" \
        ethernet.eth1.ipv6_method=static ethernet.eth1.ipv6_address="2001:db8::100/64" ethernet.eth1.ipv6_gateway="2001:db8::1"

# Static with multiple IP addresses (both IPv4 and IPv6)
cfg set ethernet.eth2.method=static \
        ethernet.eth2.addresses.[]="10.0.1.100/24" ethernet.eth2.addresses.[]="10.0.1.101/24" \
        ethernet.eth2.gateway="10.0.1.1" \
        ethernet.eth2.ipv6_method=static \
        ethernet.eth2.ipv6_addresses.[]="fd00::100/64" ethernet.eth2.ipv6_addresses.[]="fd00::101/64" \
        ethernet.eth2.ipv6_gateway="fd00::1"

# Apply the changes
cfg reload
```

Or edit `/data/network-policy.toml`:

```toml
# Dual-stack: DHCP for IPv4, SLAAC for IPv6
[ethernet.eth0]
enabled = true
priority = 10
method = "dhcp"
ipv6_method = "auto"  # SLAAC/ND

# Static IPv4 and IPv6 with multiple addresses
[ethernet.eth1]
enabled = true
priority = 15
method = "static"
ipv4_addresses = ["192.168.1.100/24", "192.168.1.101/24"]
ipv4_gateway = "192.168.1.1"
ipv4_dns = ["192.168.1.1"]
ipv6_method = "static"
ipv6_addresses = ["2001:db8::100/64", "2001:db8::101/64"]
ipv6_gateway = "2001:db8::1"
ipv6_dns = ["2001:4860:4860::8888"]

# DHCPv6 for IPv6
[ethernet.eth2]
enabled = true
priority = 12
method = "dhcp"
ipv6_method = "dhcp"  # DHCPv6
```

**IPv6 Method Options:**
- `auto` - SLAAC (Stateless Address Autoconfiguration) with Neighbor Discovery
- `dhcp` - DHCPv6 (Stateful configuration)
- `static` - Static IPv6 addresses
- `disabled` - Disable IPv6

### Configure Firewall Rules

Using cfg command:
```bash
# Create address group
cfg set firewall.address_groups.trusted.addresses='["192.168.1.0/24", "10.0.0.0/8"]'

# Create service
cfg set firewall.services.web.protocol=tcp
cfg set firewall.services.web.ports='[80, 443]'

# Add firewall rule (note: array syntax for rules is complex, edit file directly)
```

Or edit `/data/network-policy.toml`:

```toml
[firewall.address_groups.trusted]
ipv4_addresses = ["192.168.1.0/24", "10.0.0.0/8"]

[firewall.services.web]
protocol = "tcp"
ports = [80, 443]

[[firewall.input_rules]]
comment = "Allow web from trusted networks"
source_groups = ["trusted"]
service = "web"
action = "accept"
```

### Set Up LTE Failover

Using cfg command (all at once for atomicity):
```bash
# Configure all settings in one command
cfg set ethernet.eth0.enabled=true ethernet.eth0.priority=10 ethernet.eth0.method=dhcp \
        lte.wwan0.enabled=true lte.wwan0.priority=30 lte.wwan0.device="eg25-g" lte.wwan0.apn="internet" \
        healthcheck.interval_sec=30 healthcheck.timeout_sec=5 \
        healthcheck.probe_targets='["8.8.8.8", "1.1.1.1"]' \
        healthcheck.failures_before_down=3 healthcheck.successes_before_up=2

# Apply all changes
cfg reload
```

Or make changes individually:
```bash
# Configure Ethernet as primary
cfg set ethernet.eth0.enabled=true ethernet.eth0.priority=10 ethernet.eth0.method=dhcp

# Configure LTE as backup
cfg set lte.wwan0.enabled=true lte.wwan0.priority=30 lte.wwan0.device="eg25-g" lte.wwan0.apn="internet"

# Configure health monitoring
cfg set healthcheck.interval_sec=30 healthcheck.timeout_sec=5 \
        healthcheck.probe_targets='["8.8.8.8", "1.1.1.1"]' \
        healthcheck.failures_before_down=3 healthcheck.successes_before_up=2

# Apply all changes
cfg reload
```

Or edit `/data/network-policy.toml`:

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

Check status:
```bash
cfg status
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
cfg status

# Check logs
sudo journalctl -u network-policy-healthcheck.service -f
```

### Debug Mode

Enable comprehensive debug logging for troubleshooting:

```bash
# Enable debug logging for any command
cfg --debug set ethernet.eth0.method=dhcp
cfg --debug reload
cfg --debug status

# View debug log
sudo tail -f /var/log/network-policy-cfg-debug.log
```

The debug log captures:
- All commands executed with full output
- File operations (read/write)
- Socket communications
- Error codes and stack traces
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
