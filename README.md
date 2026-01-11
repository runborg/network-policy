# Network Policy v1.0.0

**Advanced Network Policy Management for Embedded Linux**

A comprehensive network management system for embedded systems with multiple interfaces (Ethernet, WiFi, LTE, WireGuard), integrated stateful firewall, health monitoring with automatic failover, and runtime-reloadable TOML configuration.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

## Features

- ⚡ **Multiple Interface Support**: Ethernet, WiFi, LTE/Cellular, WireGuard VPN
- 🔒 **Integrated Firewall**: Stateful nftables firewall with address groups and service definitions
- 🏥 **Health Monitoring**: Automatic failover based on interface health checks
- 🛣️ **Policy Routing**: Per-interface routing tables with priority-based selection
- 🔄 **Dynamic DNS**: DNS configuration follows default route
- 📝 **TOML Configuration**: Human-readable, runtime-reloadable configuration
- 👤 **System Management**: Hostname, timezone, NTP, users, and SSH keys
- 🔧 **NetworkManager Integration**: Automatic profile generation and management

## Quick Start

See [QUICKSTART.md](QUICKSTART.md) for a 5-minute setup guide.

### Installation

```bash
# Build Debian package
./build-deb.sh

# Install
sudo dpkg -i ../network-policy_*.deb
```

### Basic Configuration

1. Edit `/data/network-policy.toml`:
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
```

2. Start services:
```bash
sudo systemctl start network-policy-init.service
sudo systemctl start network-policy-healthcheck.service
```

## Documentation

- [QUICKSTART.md](QUICKSTART.md) - Get started in 5 minutes
- [example-config.toml](usr/share/doc/network-policy/example-config.toml) - Fully commented configuration example
- [debian/](debian/) - Debian packaging files

## Architecture

### Components

1. **Core Library** (`usr/local/lib/network-policy/`)
   - Configuration validation and loading
   - System settings management
   - NetworkManager profile generation
   - Firewall rule generation
   - Policy routing setup
   - DNS management
   - Health monitoring

2. **Executables** (`usr/local/bin/`)
   - `network-policy-init` - Initialize system configuration
   - `network-policy-healthcheck` - Health monitoring daemon
   - `network-policy-ctl` - Control tool (reload, status, firewall)
   - `network-policy-validate` - Configuration validator

3. **Systemd Services** (`etc/systemd/system/`)
   - `network-policy-init.service` - Oneshot initialization
   - `network-policy-healthcheck.service` - Long-running health daemon

### Configuration Flow

```
/data/network-policy.toml
         ↓
    [Validation]
         ↓
    [System Settings] → hostname, timezone, users
         ↓
    [NetworkManager] → interface profiles
         ↓
    [Policy Routing] → per-interface tables
         ↓
    [Firewall] → nftables rules
         ↓
    [DNS] → resolv.conf
         ↓
    [Health Monitor] → automatic failover
```

## Configuration

### System Settings

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
```

### Network Interfaces

```toml
# Ethernet (DHCP)
[ethernet.eth0]
enabled = true
priority = 10
method = "dhcp"

# Ethernet (Static)
[ethernet.eth1]
enabled = true
priority = 15
method = "static"
address = "10.0.1.100/24"
gateway = "10.0.1.1"
dns = ["10.0.1.1"]

# WiFi
[wifi.wlan0]
enabled = true
priority = 20
ssid = "MyNetwork"
psk = "password123"
method = "dhcp"

# LTE/Cellular
[lte.wwan0]
enabled = true
priority = 30
device = "eg25-g"
apn = "internet"

# WireGuard VPN
[wireguard.wg0]
enabled = true
private_key = "YOUR_PRIVATE_KEY="
address = "10.200.100.2/24"
peer_public_key = "PEER_PUBLIC_KEY="
peer_endpoint = "vpn.example.com:51820"
peer_allowed_ips = ["0.0.0.0/0"]
```

### Firewall

```toml
[firewall]
enabled = true
default_input_policy = "drop"
allow_established = true
allow_loopback = true

[firewall.address_groups.trusted]
addresses = ["192.168.1.0/24", "10.0.0.0/8"]

[firewall.services.ssh]
protocol = "tcp"
ports = [22]

[[firewall.input_rules]]
comment = "Allow SSH from trusted networks"
source_groups = ["trusted"]
service = "ssh"
action = "accept"
```

### Health Monitoring

```toml
[healthcheck]
interval_sec = 30
timeout_sec = 5
probe_targets = ["8.8.8.8", "1.1.1.1"]
failures_before_down = 3
successes_before_up = 2
```

## Usage

### Configuration Management

The `cfg` command (alias for `network-policy-cfg`) provides easy configuration management:

```bash
# View configuration values
cfg get ethernet.eth0.method
cfg get firewall.enabled

# Set configuration values
cfg set ethernet.eth0.method=dhcp
cfg set system.hostname="my-gateway"
cfg set firewall.enabled=true

# Add to lists
cfg set system.ntp_servers.[]="1.2.3.4"
cfg set system.ntp_servers.[]="5.6.7.8"

# Delete configuration
cfg del ethernet.eth1
cfg del wifi.wlan0

# Export config as commands
cfg export > config-backup.sh

# Enable debug logging (logs to /var/log/network-policy-cfg-debug.log)
cfg --debug set ethernet.eth0.method=static
cfg --debug reload
```

### Control Commands

```bash
# Reload configuration
cfg reload

# Check system status
cfg status

# View firewall rules
cfg firewall

# Validate configuration
network-policy-validate /data/network-policy.toml
```

### Service Management

```bash
# Start/stop services
sudo systemctl start network-policy-init.service
sudo systemctl start network-policy-healthcheck.service
sudo systemctl stop network-policy-healthcheck.service

# Enable/disable on boot
sudo systemctl enable network-policy-init.service
sudo systemctl enable network-policy-healthcheck.service

# View logs
sudo journalctl -u network-policy-init.service
sudo journalctl -u network-policy-healthcheck.service -f
```

## Use Cases

### Multi-WAN Router with Failover

Configure multiple internet connections with automatic failover:

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
probe_targets = ["8.8.8.8"]
failures_before_down = 3
```

When eth0 fails, traffic automatically switches to LTE.

### Secure Gateway with VPN

Route all traffic through WireGuard VPN:

```toml
[ethernet.eth0]
enabled = true
priority = 10
method = "dhcp"

[wireguard.wg0]
enabled = true
priority = 5  # Higher priority than physical interfaces
private_key = "YOUR_KEY="
address = "10.200.100.2/24"
peer_public_key = "PEER_KEY="
peer_endpoint = "vpn.example.com:51820"
peer_allowed_ips = ["0.0.0.0/0"]  # Route everything

[firewall]
enabled = true
default_input_policy = "drop"
```

### IoT Device with Cellular

Embedded device with LTE connectivity:

```toml
[lte.wwan0]
enabled = true
priority = 10
device = "eg25-g"
apn = "iot.provider.com"
user = "iot"
password = "secret"

[firewall]
enabled = true
default_input_policy = "drop"

[[firewall.input_rules]]
comment = "Allow management from VPN"
source_groups = ["management"]
service = "ssh"
action = "accept"
```

## Requirements

### System Requirements

- Debian 11+ or Ubuntu 20.04+
- Python 3.7 or higher
- 100 MB disk space
- Root/sudo access

### Dependencies

- python3 (>= 3.7)
- python3-toml
- network-manager
- modemmanager
- iproute2
- nftables
- systemd
- iputils-ping

## Building from Source

```bash
# Clone repository
git clone https://github.com/runborg/network-policy.git
cd network-policy

# Build Debian package
./build-deb.sh

# Install
sudo dpkg -i ../network-policy_*.deb
sudo apt-get install -f
```

## Development

### Project Structure

```
network-policy/
├── usr/local/lib/network-policy/  # Python library
│   ├── __init__.py
│   ├── config.py                   # Configuration loader
│   ├── schema.py                   # Validation schema
│   ├── logger.py                   # Logging system
│   ├── system.py                   # System management
│   ├── nm_profiles.py              # NetworkManager profiles
│   ├── routing.py                  # Policy routing
│   ├── firewall.py                 # Firewall management
│   ├── dns.py                      # DNS management
│   └── healthcheck.py              # Health monitoring
├── usr/local/bin/                  # Executables
│   ├── network-policy-init
│   ├── network-policy-healthcheck
│   ├── network-policy-ctl
│   └── network-policy-validate
├── etc/systemd/system/             # Systemd services
│   ├── network-policy-init.service
│   └── network-policy-healthcheck.service
├── usr/share/doc/network-policy/   # Documentation
│   └── example-config.toml
├── debian/                         # Debian packaging
│   ├── control
│   ├── changelog
│   ├── rules
│   └── ...
└── build-deb.sh                    # Build script
```

### Testing

```bash
# Validate configuration
network-policy-validate example-config.toml

# Test syntax
python3 -m py_compile usr/local/lib/network-policy/*.py

# Dry-run build
./build-deb.sh
```

## Troubleshooting

### Configuration Errors

```bash
# Validate configuration
network-policy-validate /data/network-policy.toml

# Check TOML syntax
python3 -c "import toml; toml.load(open('/data/network-policy.toml'))"
```

### Service Issues

```bash
# Check service status
sudo systemctl status network-policy-init.service
sudo systemctl status network-policy-healthcheck.service

# View logs
sudo journalctl -u network-policy-init.service -n 100
sudo journalctl -u network-policy-healthcheck.service -f
```

### Network Issues

```bash
# Check interfaces
ip addr show
nmcli device status

# Check routing
ip route show
ip rule list

# Check firewall
sudo nft list table inet network-policy

# Check health monitor
network-policy-ctl status
```

### Common Problems

**Problem**: Services fail to start
- Check configuration: `network-policy-validate /data/network-policy.toml`
- Check logs: `sudo journalctl -u network-policy-* -n 100`

**Problem**: Interfaces not coming up
- Check NetworkManager: `nmcli connection show`
- Check device status: `nmcli device status`
- Restart NetworkManager: `sudo systemctl restart NetworkManager`

**Problem**: Firewall blocking traffic
- View rules: `network-policy-ctl firewall`
- Check logs: `sudo journalctl -k | grep -i nft`
- Temporarily disable: Edit config, set `firewall.enabled = false`, reload

**Problem**: Health monitor not switching
- Check status: `network-policy-ctl status`
- Check logs: `sudo journalctl -u network-policy-healthcheck.service -f`
- Verify probe targets are reachable

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

GNU General Public License v3.0 - see [LICENSE](LICENSE) file for details.

## Authors

Network Policy Team

## Changelog

### v1.0.0 (2025-01-10)

- Initial release
- Support for Ethernet, WiFi, LTE, and WireGuard interfaces
- Integrated nftables firewall
- Health monitoring with automatic failover
- Policy-based routing
- DNS management
- System settings and user management
- Comprehensive configuration validation
- Debian package support

## Support

- GitHub Issues: https://github.com/runborg/network-policy/issues
- Documentation: `/usr/share/doc/network-policy/`

## Acknowledgments

Built with Python, NetworkManager, nftables, and systemd.
