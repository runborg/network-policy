# Network Policy - User Manual

Complete guide to configuring and using the Network Policy management system.

## Table of Contents

1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Interface Management](#interface-management)
5. [Firewall](#firewall)
6. [Health Monitoring](#health-monitoring)
7. [System Management](#system-management)
8. [Command Reference](#command-reference)
9. [Troubleshooting](#troubleshooting)
10. [Examples](#examples)

## Introduction

Network Policy is a comprehensive network management system designed for embedded Linux systems that need:

- Multiple network interfaces (Ethernet, WiFi, LTE, WireGuard)
- Automatic failover between interfaces
- Stateful firewall protection
- Policy-based routing
- Centralized, validated configuration

### Key Concepts

**Priority-Based Routing**: Each interface is assigned a priority (lower number = higher priority). Traffic uses the highest-priority active interface.

**Health Monitoring**: Interfaces are continuously monitored with ICMP pings. Failed interfaces are automatically taken out of rotation.

**Policy Routing**: Each interface gets its own routing table. Connection tracking ensures return traffic uses the correct interface.

**Stateful Firewall**: nftables-based firewall with connection tracking, address groups, and service definitions.

## Installation

### From Debian Package

```bash
# Install the package
sudo dpkg -i network-policy_1.0.0_all.deb

# Fix any dependency issues
sudo apt-get install -f
```

The package installs:
- Libraries to `/usr/local/lib/network-policy/`
- Executables to `/usr/local/bin/`
- Systemd services to `/etc/systemd/system/`
- Documentation to `/usr/share/doc/network-policy/`
- Example config to `/data/network-policy.toml` (if not exists)

### Manual Installation

```bash
# Install dependencies
sudo apt install python3 python3-toml network-manager modemmanager \
                 iproute2 nftables systemd iputils-ping

# Copy files from repository
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

### Configuration File

The main configuration file is `/data/network-policy.toml` in TOML format.

**TOML Basics:**
- `key = "value"` for strings
- `key = 123` for numbers
- `key = true` for booleans
- `key = ["a", "b"]` for lists
- `[section]` for sections
- `[[array_section]]` for array of tables

### Configuration Structure

```toml
[system]          # System settings
[users.NAME]      # User accounts
[ethernet.NAME]   # Ethernet interfaces
[wifi.NAME]       # WiFi interfaces
[lte.NAME]        # LTE interfaces
[wireguard.NAME]  # WireGuard interfaces
[firewall]        # Firewall settings
[healthcheck]     # Health monitoring
[dns]             # DNS management
[logging]         # Logging settings
[[routes]]        # Static routes
```

### Validation

Always validate your configuration before applying:

```bash
network-policy-validate /data/network-policy.toml
```

The validator checks for:
- TOML syntax errors
- Unknown configuration options (typos)
- Missing required fields
- Invalid values (wrong type, out of range)
- Bad references (unknown services, groups, interfaces)
- Conditional requirements (e.g., static IP requires address)

## Interface Management

### Ethernet Interfaces

```toml
[ethernet.eth0]
enabled = true
priority = 10        # 0-1000, lower = higher priority
method = "dhcp"      # "dhcp", "static", or "auto"

# Optional for static IP
address = "192.168.1.100/24"
gateway = "192.168.1.1"
dns = ["8.8.8.8", "1.1.1.1"]
mtu = 1500
```

**Methods:**
- `dhcp`: Get IP via DHCP
- `static`: Manual IP configuration (requires address)
- `auto`: Autoconfiguration (IPv6)

### WiFi Interfaces

```toml
[wifi.wlan0]
enabled = true
priority = 20
ssid = "NetworkName"     # Required, 1-32 characters
psk = "Password123"      # Required if secured, 8-63 characters
method = "dhcp"

# Optional for static IP
address = "192.168.2.100/24"
gateway = "192.168.2.1"
dns = ["192.168.2.1"]
```

**Security:** Currently supports WPA-PSK only. Open networks can omit `psk`.

### LTE/Cellular Interfaces

```toml
[lte.wwan0]
enabled = true
priority = 30
device = "eg25-g"        # "eg25-g", "mc7455", "mc7354", "generic"
apn = "internet"         # Required

# Optional authentication
user = "username"
password = "password"
pin = "1234"             # 4-8 digits
```

**Supported Modems:**
- Quectel EG25-G (`eg25-g`)
- Sierra Wireless MC7455 (`mc7455`)
- Sierra Wireless MC7354 (`mc7354`)
- Generic (`generic`)

### WireGuard VPN

```toml
[wireguard.wg0]
enabled = true
private_key = "YourPrivateKeyBase64="    # Required, 44 chars
address = "10.200.100.2/24"              # Required
peer_public_key = "PeerKeyBase64="       # Required
peer_endpoint = "vpn.example.com:51820"  # host:port
peer_allowed_ips = ["0.0.0.0/0"]         # Required

# Optional
listen_port = 51820
dns = ["10.200.100.1"]
peer_preshared_key = "PSKBase64="
peer_keepalive = 25                      # Seconds, 0=disable
```

**Key Generation:**
```bash
# Generate private key
wg genkey > privatekey

# Generate public key
wg pubkey < privatekey > publickey

# Generate pre-shared key (optional)
wg genpsk > preshared
```

**Routing All Traffic Through VPN:**
Set `peer_allowed_ips = ["0.0.0.0/0"]` and give the VPN interface higher priority (lower number) than other interfaces.

## Firewall

### Firewall Configuration

```toml
[firewall]
enabled = true
default_input_policy = "drop"    # "drop" or "accept"
allow_established = true         # Allow return traffic
allow_loopback = true           # Allow localhost
```

### Address Groups

Define reusable sets of IP addresses:

```toml
[firewall.address_groups.GROUP_NAME]
description = "Optional description"
addresses = [
    "192.168.1.0/24",
    "10.0.0.0/8",
    "172.16.0.100"
]
```

**Supported Formats:**
- Single IPs: `"192.168.1.100"`
- CIDR networks: `"10.0.0.0/8"`
- IPv4 only currently

### Service Definitions

Define reusable services:

```toml
[firewall.services.SERVICE_NAME]
protocol = "tcp"           # "tcp", "udp", or "icmp"
ports = [80, 443, 8080]   # List of port numbers (1-65535)
```

### Firewall Rules

Rules are evaluated in order, first match wins:

```toml
[[firewall.input_rules]]
comment = "Descriptive comment"
source_groups = ["group1", "group2"]  # Optional, OR logic
service = "service_name"              # Optional
action = "accept"                     # "accept", "drop", or "reject"
log = true                           # Optional, log matches
log_prefix = "FW-PREFIX: "           # Optional, max 29 chars
```

**Actions:**
- `accept`: Allow the traffic
- `drop`: Silently discard
- `reject`: Discard with ICMP error

**Multiple Source Groups:**
When multiple groups are specified, traffic from ANY of them matches (OR logic).

### Firewall Examples

**Allow SSH from specific networks:**
```toml
[firewall.address_groups.admin_nets]
addresses = ["192.168.1.0/24", "10.10.10.0/24"]

[firewall.services.ssh]
protocol = "tcp"
ports = [22]

[[firewall.input_rules]]
comment = "Allow SSH from admin networks"
source_groups = ["admin_nets"]
service = "ssh"
action = "accept"
```

**Allow web traffic from anywhere:**
```toml
[firewall.services.web]
protocol = "tcp"
ports = [80, 443]

[[firewall.input_rules]]
comment = "Allow web traffic"
service = "web"
action = "accept"
```

**Log and reject everything else:**
```toml
[[firewall.input_rules]]
comment = "Log rejected traffic"
action = "reject"
log = true
log_prefix = "FW-REJECT: "
```

## Health Monitoring

The health monitoring daemon continuously checks interface health and performs automatic failover.

### Configuration

```toml
[healthcheck]
interval_sec = 30                    # Check interval (1-3600)
timeout_sec = 5                      # Ping timeout (1-60)
probe_targets = [                    # IPs to ping
    "8.8.8.8",
    "1.1.1.1"
]
failures_before_down = 3             # Failures to mark down (1-100)
successes_before_up = 2              # Successes to mark up (1-100)
```

### How It Works

1. Every `interval_sec`, the daemon pings all `probe_targets` via each interface
2. If at least one target responds, the check succeeds
3. After `failures_before_down` consecutive failures, the interface is marked down
4. After `successes_before_up` consecutive successes, the interface is marked up
5. When an interface state changes, routing rules are updated
6. DNS configuration is updated to follow the new default route

### Monitoring Status

```bash
# Check status
network-policy-ctl status

# Watch logs
sudo journalctl -u network-policy-healthcheck.service -f
```

## System Management

### System Settings

```toml
[system]
hostname = "my-gateway"
timezone = "Europe/Copenhagen"       # IANA timezone
ntp_servers = [                      # NTP server addresses
    "0.pool.ntp.org",
    "1.pool.ntp.org"
]
locale = "en_US.UTF-8"              # System locale
```

**Common Timezones:**
- `UTC`
- `America/New_York`
- `Europe/London`
- `Europe/Copenhagen`
- `Asia/Tokyo`

### User Management

```toml
[users.USERNAME]
password_hash = "$6$..."             # Required, see below
groups = ["wheel", "sudo", "adm"]   # Optional
shell = "/bin/bash"                 # Optional, default /bin/bash
ssh_keys = [                        # Optional
    "ssh-ed25519 AAAAC3... user@host",
    "ssh-rsa AAAAB3... user@host"
]
```

**Generate Password Hash:**
```bash
# Method 1: Using mkpasswd
mkpasswd -m sha-512

# Method 2: Using Python
python3 -c 'import crypt; print(crypt.crypt("mypassword", crypt.mksalt(crypt.METHOD_SHA512)))'
```

**Common Groups:**
- `wheel`: sudo access (RHEL/CentOS)
- `sudo`: sudo access (Debian/Ubuntu)
- `adm`: read system logs
- `systemd-journal`: read journald logs

## Command Reference

### network-policy-init

Initialize the system with configuration.

```bash
network-policy-init [options]

Options:
  -c, --config PATH    Configuration file (default: /data/network-policy.toml)
  -v, --verbose        Enable verbose logging
```

Run once at boot via systemd service. Applies:
- System settings
- NetworkManager profiles
- Policy routing
- Firewall rules
- DNS configuration

### network-policy-healthcheck

Health monitoring daemon.

```bash
network-policy-healthcheck [options]

Options:
  -c, --config PATH    Configuration file (default: /data/network-policy.toml)
  -v, --verbose        Enable verbose logging
```

Long-running daemon that monitors interface health and performs automatic failover. Control via `network-policy-ctl`.

### network-policy-ctl

Control tool for managing the system.

```bash
# Reload configuration
network-policy-ctl reload [-c CONFIG]

# Show system status
network-policy-ctl status

# View firewall rules
network-policy-ctl firewall
```

**Commands:**
- `reload`: Reload configuration without restart
- `status`: Show interface status and health monitor state
- `firewall`: Display current nftables rules

### network-policy-validate

Validate configuration file.

```bash
network-policy-validate [CONFIG] [-v]

Options:
  CONFIG               Configuration file (default: /data/network-policy.toml)
  -v, --verbose        Show detailed validation information
```

Always validate before applying new configuration!

## Troubleshooting

### Configuration Issues

**Problem:** Validation fails with "Unknown field"
- **Cause:** Typo in configuration key
- **Fix:** Check spelling against example-config.toml

**Problem:** "Required field missing"
- **Cause:** Required field not provided
- **Fix:** Add the missing field (e.g., `address` for static IP)

**Problem:** "Invalid value"
- **Cause:** Value is wrong type or out of range
- **Fix:** Check value type (string vs number) and range

### Network Issues

**Problem:** Interface not coming up
- Check NetworkManager: `nmcli device status`
- Check connection: `nmcli connection show`
- Restart NetworkManager: `sudo systemctl restart NetworkManager`
- Check logs: `sudo journalctl -u NetworkManager -f`

**Problem:** No default route
- Check routing: `ip route show`
- Check interface status: `network-policy-ctl status`
- Verify interface has gateway configured

**Problem:** Cannot reach internet
- Check routing: `ip route show`
- Check firewall: `network-policy-ctl firewall`
- Test ping: `ping -I eth0 8.8.8.8`
- Check DNS: `resolvectl status`

### Firewall Issues

**Problem:** Firewall blocking expected traffic
- View rules: `network-policy-ctl firewall`
- Check rule order (first match wins)
- Add logging to debug: `log = true` in rule
- Check kernel logs: `sudo journalctl -k | grep -i nft`

**Problem:** Firewall not applying
- Check service: `sudo systemctl status network-policy-init.service`
- Manual apply: `sudo nft -f /path/to/rules.nft`
- Check nftables: `sudo nft list tables`

### Health Monitor Issues

**Problem:** Health monitor not running
- Check service: `sudo systemctl status network-policy-healthcheck.service`
- Check socket: `ls -la /run/network-policy.sock`
- Check logs: `sudo journalctl -u network-policy-healthcheck.service -f`

**Problem:** Failover not working
- Check status: `network-policy-ctl status`
- Verify probe targets are reachable: `ping 8.8.8.8`
- Check thresholds in configuration
- Watch logs during failover event

### Service Issues

**Problem:** Services fail to start
- Check configuration: `network-policy-validate /data/network-policy.toml`
- Check logs: `sudo journalctl -u network-policy-* -n 100`
- Check dependencies: `sudo apt-get install -f`

**Problem:** Changes not taking effect
- Reload: `network-policy-ctl reload`
- Restart services: `sudo systemctl restart network-policy-*`
- Check logs for errors

## Examples

### Example 1: Simple Gateway

Single Ethernet interface with firewall:

```toml
[system]
hostname = "gateway"

[ethernet.eth0]
enabled = true
priority = 10
method = "dhcp"

[firewall]
enabled = true
default_input_policy = "drop"
allow_established = true
allow_loopback = true

[firewall.services.ssh]
protocol = "tcp"
ports = [22]

[[firewall.input_rules]]
comment = "Allow SSH"
service = "ssh"
action = "accept"

[[firewall.input_rules]]
comment = "Drop everything else"
action = "drop"
```

### Example 2: Multi-WAN with Failover

Primary Ethernet, backup LTE:

```toml
[ethernet.eth0]
enabled = true
priority = 10
method = "dhcp"

[lte.wwan0]
enabled = true
priority = 30
device = "eg25-g"
apn = "internet"

[healthcheck]
interval_sec = 30
timeout_sec = 5
probe_targets = ["8.8.8.8", "1.1.1.1"]
failures_before_down = 3
successes_before_up = 2

[firewall]
enabled = true
default_input_policy = "drop"
allow_established = true
allow_loopback = true
```

### Example 3: VPN Gateway

Route all traffic through WireGuard:

```toml
[ethernet.eth0]
enabled = true
priority = 20  # Lower priority
method = "dhcp"

[wireguard.wg0]
enabled = true
priority = 10  # Higher priority
private_key = "YOUR_PRIVATE_KEY="
address = "10.200.100.2/24"
peer_public_key = "PEER_PUBLIC_KEY="
peer_endpoint = "vpn.example.com:51820"
peer_allowed_ips = ["0.0.0.0/0"]
peer_keepalive = 25

[firewall]
enabled = true
default_input_policy = "drop"
allow_established = true
allow_loopback = true

[firewall.address_groups.vpn_clients]
addresses = ["10.200.100.0/24"]

[[firewall.input_rules]]
comment = "Allow from VPN"
source_groups = ["vpn_clients"]
action = "accept"
```

### Example 4: Complete System

Full configuration with all features:

```toml
[system]
hostname = "edge-gateway"
timezone = "Europe/Copenhagen"
ntp_servers = ["0.pool.ntp.org"]
locale = "en_US.UTF-8"

[users.admin]
password_hash = "$6$rounds=656000$..."
groups = ["wheel", "sudo"]
shell = "/bin/bash"
ssh_keys = ["ssh-ed25519 AAAAC3..."]

[ethernet.eth0]
enabled = true
priority = 10
method = "static"
address = "192.168.1.100/24"
gateway = "192.168.1.1"
dns = ["192.168.1.1"]

[wifi.wlan0]
enabled = true
priority = 20
ssid = "BackupWiFi"
psk = "SecurePassword"
method = "dhcp"

[lte.wwan0]
enabled = true
priority = 30
device = "eg25-g"
apn = "internet"

[wireguard.wg0]
enabled = true
private_key = "YOUR_KEY="
address = "10.200.100.2/24"
peer_public_key = "PEER_KEY="
peer_endpoint = "vpn.example.com:51820"
peer_allowed_ips = ["10.200.100.0/24"]

[firewall]
enabled = true
default_input_policy = "drop"
allow_established = true
allow_loopback = true

[firewall.address_groups.trusted]
addresses = ["192.168.1.0/24", "10.200.100.0/24"]

[firewall.services.ssh]
protocol = "tcp"
ports = [22]

[firewall.services.web]
protocol = "tcp"
ports = [80, 443]

[[firewall.input_rules]]
comment = "Allow SSH from trusted"
source_groups = ["trusted"]
service = "ssh"
action = "accept"

[[firewall.input_rules]]
comment = "Allow web"
service = "web"
action = "accept"

[[firewall.input_rules]]
comment = "Reject rest"
action = "reject"
log = true

[healthcheck]
interval_sec = 30
timeout_sec = 5
probe_targets = ["8.8.8.8", "1.1.1.1"]
failures_before_down = 3
successes_before_up = 2

[dns]
enabled = true
fallback_servers = ["8.8.8.8", "1.1.1.1"]

[logging]
path = "/var/log/network-policy.log"
level = "INFO"

[[routes]]
interface = "wwan0"
destinations = ["203.0.113.0/24"]
```

## Additional Resources

- Example Configuration: `/usr/share/doc/network-policy/example-config.toml`
- Quick Start Guide: `QUICKSTART.md`
- Main README: `README.md`
- License: `LICENSE`

## Support

For issues and questions:
- GitHub: https://github.com/runborg/network-policy/issues
- Documentation: `/usr/share/doc/network-policy/`

---

**Network Policy v1.0.0** - Advanced Network Management for Embedded Linux
