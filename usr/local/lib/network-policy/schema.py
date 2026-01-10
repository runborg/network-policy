"""
Comprehensive configuration schema validator.

Validates all configuration options including:
- Unknown options (typos in field names)
- Missing required fields
- Wrong types (str vs int vs bool vs list)
- Invalid values (not in allowed list)
- Out of range values (min/max)
- Bad references (unknown services, address groups, interfaces)
- Conditional requirements
"""

import ipaddress
import re
from typing import Any, Dict, List, Optional, Set, Tuple


class ValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


# Valid log levels
VALID_LOG_LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

# Valid firewall actions
VALID_FIREWALL_ACTIONS = ["accept", "drop", "reject"]

# Valid firewall policies
VALID_FIREWALL_POLICIES = ["accept", "drop"]

# Valid protocols
VALID_PROTOCOLS = ["tcp", "udp", "icmp"]

# Valid network methods
VALID_NETWORK_METHODS = ["dhcp", "static", "auto"]

# Valid shells
VALID_SHELLS = ["/bin/bash", "/bin/sh", "/bin/zsh", "/usr/bin/fish"]

# LTE device types
VALID_LTE_DEVICES = ["eg25-g", "mc7455", "mc7354", "generic"]


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate complete configuration against schema.
    
    Args:
        config: Configuration dictionary from TOML
        
    Raises:
        ValidationError: If validation fails
    """
    if not isinstance(config, dict):
        raise ValidationError("Configuration must be a dictionary")
    
    # Track all interface names for reference validation
    interfaces: Set[str] = set()
    
    # Validate each top-level section
    for key in config.keys():
        if key not in ["system", "users", "ethernet", "wifi", "lte", "wireguard",
                       "firewall", "healthcheck", "dns", "logging", "routes"]:
            raise ValidationError(f"Unknown top-level section: {key}")
    
    # Validate system section
    if "system" in config:
        _validate_system(config["system"])
    
    # Validate users section
    if "users" in config:
        _validate_users(config["users"])
    
    # Validate network interfaces and collect interface names
    if "ethernet" in config:
        for iface_name, iface_config in config["ethernet"].items():
            _validate_ethernet(iface_name, iface_config)
            if iface_config.get("enabled", True):
                interfaces.add(iface_name)
    
    if "wifi" in config:
        for iface_name, iface_config in config["wifi"].items():
            _validate_wifi(iface_name, iface_config)
            if iface_config.get("enabled", True):
                interfaces.add(iface_name)
    
    if "lte" in config:
        for iface_name, iface_config in config["lte"].items():
            _validate_lte(iface_name, iface_config)
            if iface_config.get("enabled", True):
                interfaces.add(iface_name)
    
    if "wireguard" in config:
        for iface_name, iface_config in config["wireguard"].items():
            _validate_wireguard(iface_name, iface_config)
            if iface_config.get("enabled", True):
                interfaces.add(iface_name)
    
    # Validate firewall section
    address_groups: Set[str] = set()
    services: Set[str] = set()
    if "firewall" in config:
        ag, svc = _validate_firewall(config["firewall"])
        address_groups = ag
        services = svc
    
    # Validate healthcheck section
    if "healthcheck" in config:
        _validate_healthcheck(config["healthcheck"])
    
    # Validate DNS section
    if "dns" in config:
        _validate_dns(config["dns"])
    
    # Validate logging section
    if "logging" in config:
        _validate_logging(config["logging"])
    
    # Validate routes section
    if "routes" in config:
        _validate_routes(config["routes"], interfaces)


def _validate_system(system: Any) -> None:
    """Validate system section."""
    if not isinstance(system, dict):
        raise ValidationError("system section must be a dictionary")
    
    # Check for unknown fields
    valid_fields = ["hostname", "timezone", "ntp_servers", "locale"]
    for key in system.keys():
        if key not in valid_fields:
            raise ValidationError(f"Unknown field in system section: {key}")
    
    # Validate hostname
    if "hostname" in system:
        hostname = system["hostname"]
        if not isinstance(hostname, str):
            raise ValidationError("system.hostname must be a string")
        if not hostname or len(hostname) > 253:
            raise ValidationError("system.hostname must be 1-253 characters")
        if not re.match(r'^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?$', hostname):
            raise ValidationError("system.hostname contains invalid characters")
    
    # Validate timezone
    if "timezone" in system:
        timezone = system["timezone"]
        if not isinstance(timezone, str):
            raise ValidationError("system.timezone must be a string")
        if not timezone:
            raise ValidationError("system.timezone cannot be empty")
    
    # Validate NTP servers
    if "ntp_servers" in system:
        ntp_servers = system["ntp_servers"]
        if not isinstance(ntp_servers, list):
            raise ValidationError("system.ntp_servers must be a list")
        for idx, server in enumerate(ntp_servers):
            if not isinstance(server, str):
                raise ValidationError(f"system.ntp_servers[{idx}] must be a string")
            if not server:
                raise ValidationError(f"system.ntp_servers[{idx}] cannot be empty")
    
    # Validate locale
    if "locale" in system:
        locale = system["locale"]
        if not isinstance(locale, str):
            raise ValidationError("system.locale must be a string")
        if not locale:
            raise ValidationError("system.locale cannot be empty")


def _validate_users(users: Any) -> None:
    """Validate users section."""
    if not isinstance(users, dict):
        raise ValidationError("users section must be a dictionary")
    
    for username, user_config in users.items():
        if not isinstance(username, str):
            raise ValidationError("User name must be a string")
        if not re.match(r'^[a-z_][a-z0-9_-]*[$]?$', username):
            raise ValidationError(f"Invalid username: {username}")
        
        if not isinstance(user_config, dict):
            raise ValidationError(f"User config for {username} must be a dictionary")
        
        # Check for unknown fields
        valid_fields = ["password_hash", "groups", "shell", "ssh_keys"]
        for key in user_config.keys():
            if key not in valid_fields:
                raise ValidationError(f"Unknown field in users.{username}: {key}")
        
        # Validate password_hash
        if "password_hash" in user_config:
            password_hash = user_config["password_hash"]
            if not isinstance(password_hash, str):
                raise ValidationError(f"users.{username}.password_hash must be a string")
            if not password_hash.startswith("$"):
                raise ValidationError(f"users.{username}.password_hash must be a valid hash")
        
        # Validate groups
        if "groups" in user_config:
            groups = user_config["groups"]
            if not isinstance(groups, list):
                raise ValidationError(f"users.{username}.groups must be a list")
            for idx, group in enumerate(groups):
                if not isinstance(group, str):
                    raise ValidationError(f"users.{username}.groups[{idx}] must be a string")
        
        # Validate shell
        if "shell" in user_config:
            shell = user_config["shell"]
            if not isinstance(shell, str):
                raise ValidationError(f"users.{username}.shell must be a string")
            if shell not in VALID_SHELLS:
                raise ValidationError(
                    f"users.{username}.shell must be one of: {', '.join(VALID_SHELLS)}"
                )
        
        # Validate SSH keys
        if "ssh_keys" in user_config:
            ssh_keys = user_config["ssh_keys"]
            if not isinstance(ssh_keys, list):
                raise ValidationError(f"users.{username}.ssh_keys must be a list")
            for idx, key in enumerate(ssh_keys):
                if not isinstance(key, str):
                    raise ValidationError(f"users.{username}.ssh_keys[{idx}] must be a string")
                if not key.startswith(("ssh-rsa", "ssh-ed25519", "ecdsa-sha2-", "ssh-dss")):
                    raise ValidationError(f"users.{username}.ssh_keys[{idx}] invalid format")


def _validate_ethernet(iface_name: str, config: Any) -> None:
    """Validate ethernet interface configuration."""
    if not isinstance(config, dict):
        raise ValidationError(f"ethernet.{iface_name} must be a dictionary")
    
    # Check for unknown fields
    valid_fields = ["enabled", "priority", "method", "address", "gateway", "dns", "mtu"]
    for key in config.keys():
        if key not in valid_fields:
            raise ValidationError(f"Unknown field in ethernet.{iface_name}: {key}")
    
    # Validate enabled
    if "enabled" in config and not isinstance(config["enabled"], bool):
        raise ValidationError(f"ethernet.{iface_name}.enabled must be a boolean")
    
    # Validate priority
    if "priority" in config:
        priority = config["priority"]
        if not isinstance(priority, int):
            raise ValidationError(f"ethernet.{iface_name}.priority must be an integer")
        if priority < 0 or priority > 1000:
            raise ValidationError(f"ethernet.{iface_name}.priority must be 0-1000")
    
    # Validate method
    if "method" in config:
        method = config["method"]
        if not isinstance(method, str):
            raise ValidationError(f"ethernet.{iface_name}.method must be a string")
        if method not in VALID_NETWORK_METHODS:
            raise ValidationError(
                f"ethernet.{iface_name}.method must be one of: {', '.join(VALID_NETWORK_METHODS)}"
            )
        
        # If static, require address
        if method == "static":
            if "address" not in config:
                raise ValidationError(f"ethernet.{iface_name}.address required when method=static")
    
    # Validate address
    if "address" in config:
        _validate_ip_address(config["address"], f"ethernet.{iface_name}.address")
    
    # Validate gateway
    if "gateway" in config:
        _validate_ip_address(config["gateway"], f"ethernet.{iface_name}.gateway", require_cidr=False)
    
    # Validate DNS
    if "dns" in config:
        dns = config["dns"]
        if not isinstance(dns, list):
            raise ValidationError(f"ethernet.{iface_name}.dns must be a list")
        for idx, server in enumerate(dns):
            _validate_ip_address(server, f"ethernet.{iface_name}.dns[{idx}]", require_cidr=False)
    
    # Validate MTU
    if "mtu" in config:
        mtu = config["mtu"]
        if not isinstance(mtu, int):
            raise ValidationError(f"ethernet.{iface_name}.mtu must be an integer")
        if mtu < 68 or mtu > 9000:
            raise ValidationError(f"ethernet.{iface_name}.mtu must be 68-9000")


def _validate_wifi(iface_name: str, config: Any) -> None:
    """Validate WiFi interface configuration."""
    if not isinstance(config, dict):
        raise ValidationError(f"wifi.{iface_name} must be a dictionary")
    
    # Check for unknown fields
    valid_fields = ["enabled", "priority", "ssid", "psk", "method", "address", "gateway", "dns"]
    for key in config.keys():
        if key not in valid_fields:
            raise ValidationError(f"Unknown field in wifi.{iface_name}: {key}")
    
    # Validate enabled
    if "enabled" in config and not isinstance(config["enabled"], bool):
        raise ValidationError(f"wifi.{iface_name}.enabled must be a boolean")
    
    # Validate priority
    if "priority" in config:
        priority = config["priority"]
        if not isinstance(priority, int):
            raise ValidationError(f"wifi.{iface_name}.priority must be an integer")
        if priority < 0 or priority > 1000:
            raise ValidationError(f"wifi.{iface_name}.priority must be 0-1000")
    
    # If enabled, require SSID
    if config.get("enabled", True):
        if "ssid" not in config:
            raise ValidationError(f"wifi.{iface_name}.ssid is required when enabled")
    
    # Validate SSID
    if "ssid" in config:
        ssid = config["ssid"]
        if not isinstance(ssid, str):
            raise ValidationError(f"wifi.{iface_name}.ssid must be a string")
        if not ssid or len(ssid) > 32:
            raise ValidationError(f"wifi.{iface_name}.ssid must be 1-32 characters")
    
    # Validate PSK
    if "psk" in config:
        psk = config["psk"]
        if not isinstance(psk, str):
            raise ValidationError(f"wifi.{iface_name}.psk must be a string")
        if len(psk) < 8 or len(psk) > 63:
            raise ValidationError(f"wifi.{iface_name}.psk must be 8-63 characters")
    
    # Validate method
    if "method" in config:
        method = config["method"]
        if not isinstance(method, str):
            raise ValidationError(f"wifi.{iface_name}.method must be a string")
        if method not in VALID_NETWORK_METHODS:
            raise ValidationError(
                f"wifi.{iface_name}.method must be one of: {', '.join(VALID_NETWORK_METHODS)}"
            )
        
        # If static, require address
        if method == "static":
            if "address" not in config:
                raise ValidationError(f"wifi.{iface_name}.address required when method=static")
    
    # Validate address
    if "address" in config:
        _validate_ip_address(config["address"], f"wifi.{iface_name}.address")
    
    # Validate gateway
    if "gateway" in config:
        _validate_ip_address(config["gateway"], f"wifi.{iface_name}.gateway", require_cidr=False)
    
    # Validate DNS
    if "dns" in config:
        dns = config["dns"]
        if not isinstance(dns, list):
            raise ValidationError(f"wifi.{iface_name}.dns must be a list")
        for idx, server in enumerate(dns):
            _validate_ip_address(server, f"wifi.{iface_name}.dns[{idx}]", require_cidr=False)


def _validate_lte(iface_name: str, config: Any) -> None:
    """Validate LTE interface configuration."""
    if not isinstance(config, dict):
        raise ValidationError(f"lte.{iface_name} must be a dictionary")
    
    # Check for unknown fields
    valid_fields = ["enabled", "priority", "device", "apn", "user", "password", "pin"]
    for key in config.keys():
        if key not in valid_fields:
            raise ValidationError(f"Unknown field in lte.{iface_name}: {key}")
    
    # Validate enabled
    if "enabled" in config and not isinstance(config["enabled"], bool):
        raise ValidationError(f"lte.{iface_name}.enabled must be a boolean")
    
    # Validate priority
    if "priority" in config:
        priority = config["priority"]
        if not isinstance(priority, int):
            raise ValidationError(f"lte.{iface_name}.priority must be an integer")
        if priority < 0 or priority > 1000:
            raise ValidationError(f"lte.{iface_name}.priority must be 0-1000")
    
    # Validate device
    if "device" in config:
        device = config["device"]
        if not isinstance(device, str):
            raise ValidationError(f"lte.{iface_name}.device must be a string")
        if device not in VALID_LTE_DEVICES:
            raise ValidationError(
                f"lte.{iface_name}.device must be one of: {', '.join(VALID_LTE_DEVICES)}"
            )
    
    # If enabled, require APN
    if config.get("enabled", True):
        if "apn" not in config:
            raise ValidationError(f"lte.{iface_name}.apn is required when enabled")
    
    # Validate APN
    if "apn" in config:
        apn = config["apn"]
        if not isinstance(apn, str):
            raise ValidationError(f"lte.{iface_name}.apn must be a string")
        if not apn:
            raise ValidationError(f"lte.{iface_name}.apn cannot be empty")
    
    # Validate user
    if "user" in config and not isinstance(config["user"], str):
        raise ValidationError(f"lte.{iface_name}.user must be a string")
    
    # Validate password
    if "password" in config and not isinstance(config["password"], str):
        raise ValidationError(f"lte.{iface_name}.password must be a string")
    
    # Validate PIN
    if "pin" in config:
        pin = config["pin"]
        if not isinstance(pin, str):
            raise ValidationError(f"lte.{iface_name}.pin must be a string")
        if not re.match(r'^\d{4,8}$', pin):
            raise ValidationError(f"lte.{iface_name}.pin must be 4-8 digits")


def _validate_wireguard(iface_name: str, config: Any) -> None:
    """Validate WireGuard interface configuration."""
    if not isinstance(config, dict):
        raise ValidationError(f"wireguard.{iface_name} must be a dictionary")
    
    # Check for unknown fields
    valid_fields = [
        "enabled", "private_key", "address", "listen_port", "dns",
        "peer_public_key", "peer_preshared_key", "peer_endpoint",
        "peer_allowed_ips", "peer_keepalive"
    ]
    for key in config.keys():
        if key not in valid_fields:
            raise ValidationError(f"Unknown field in wireguard.{iface_name}: {key}")
    
    # Validate enabled
    if "enabled" in config and not isinstance(config["enabled"], bool):
        raise ValidationError(f"wireguard.{iface_name}.enabled must be a boolean")
    
    # If enabled, require private_key, address, and peer configuration
    if config.get("enabled", True):
        required = ["private_key", "address", "peer_public_key", "peer_allowed_ips"]
        for field in required:
            if field not in config:
                raise ValidationError(f"wireguard.{iface_name}.{field} is required when enabled")
    
    # Validate private_key
    if "private_key" in config:
        private_key = config["private_key"]
        if not isinstance(private_key, str):
            raise ValidationError(f"wireguard.{iface_name}.private_key must be a string")
        if not re.match(r'^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw480]=$', private_key):
            raise ValidationError(f"wireguard.{iface_name}.private_key invalid format")
    
    # Validate address
    if "address" in config:
        _validate_ip_address(config["address"], f"wireguard.{iface_name}.address")
    
    # Validate listen_port
    if "listen_port" in config:
        port = config["listen_port"]
        if not isinstance(port, int):
            raise ValidationError(f"wireguard.{iface_name}.listen_port must be an integer")
        if port < 1 or port > 65535:
            raise ValidationError(f"wireguard.{iface_name}.listen_port must be 1-65535")
    
    # Validate DNS
    if "dns" in config:
        dns = config["dns"]
        if not isinstance(dns, list):
            raise ValidationError(f"wireguard.{iface_name}.dns must be a list")
        for idx, server in enumerate(dns):
            _validate_ip_address(server, f"wireguard.{iface_name}.dns[{idx}]", require_cidr=False)
    
    # Validate peer_public_key
    if "peer_public_key" in config:
        peer_public_key = config["peer_public_key"]
        if not isinstance(peer_public_key, str):
            raise ValidationError(f"wireguard.{iface_name}.peer_public_key must be a string")
        if not re.match(r'^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw480]=$', peer_public_key):
            raise ValidationError(f"wireguard.{iface_name}.peer_public_key invalid format")
    
    # Validate peer_preshared_key
    if "peer_preshared_key" in config:
        psk = config["peer_preshared_key"]
        if not isinstance(psk, str):
            raise ValidationError(f"wireguard.{iface_name}.peer_preshared_key must be a string")
        if not re.match(r'^[A-Za-z0-9+/]{42}[AEIMQUYcgkosw480]=$', psk):
            raise ValidationError(f"wireguard.{iface_name}.peer_preshared_key invalid format")
    
    # Validate peer_endpoint
    if "peer_endpoint" in config:
        endpoint = config["peer_endpoint"]
        if not isinstance(endpoint, str):
            raise ValidationError(f"wireguard.{iface_name}.peer_endpoint must be a string")
        if not re.match(r'^[^:]+:\d+$', endpoint):
            raise ValidationError(f"wireguard.{iface_name}.peer_endpoint must be host:port")
    
    # Validate peer_allowed_ips
    if "peer_allowed_ips" in config:
        allowed_ips = config["peer_allowed_ips"]
        if not isinstance(allowed_ips, list):
            raise ValidationError(f"wireguard.{iface_name}.peer_allowed_ips must be a list")
        for idx, cidr in enumerate(allowed_ips):
            _validate_ip_address(cidr, f"wireguard.{iface_name}.peer_allowed_ips[{idx}]")
    
    # Validate peer_keepalive
    if "peer_keepalive" in config:
        keepalive = config["peer_keepalive"]
        if not isinstance(keepalive, int):
            raise ValidationError(f"wireguard.{iface_name}.peer_keepalive must be an integer")
        if keepalive < 0 or keepalive > 65535:
            raise ValidationError(f"wireguard.{iface_name}.peer_keepalive must be 0-65535")


def _validate_firewall(firewall: Any) -> Tuple[Set[str], Set[str]]:
    """
    Validate firewall section.
    
    Returns:
        Tuple of (address_groups, services) sets for reference validation
    """
    if not isinstance(firewall, dict):
        raise ValidationError("firewall section must be a dictionary")
    
    # Check for unknown fields
    valid_fields = [
        "enabled", "default_input_policy", "allow_established", "allow_loopback",
        "address_groups", "services", "input_rules"
    ]
    for key in firewall.keys():
        if key not in valid_fields:
            raise ValidationError(f"Unknown field in firewall section: {key}")
    
    # Validate enabled
    if "enabled" in firewall and not isinstance(firewall["enabled"], bool):
        raise ValidationError("firewall.enabled must be a boolean")
    
    # Validate default_input_policy
    if "default_input_policy" in firewall:
        policy = firewall["default_input_policy"]
        if not isinstance(policy, str):
            raise ValidationError("firewall.default_input_policy must be a string")
        if policy not in VALID_FIREWALL_POLICIES:
            raise ValidationError(
                f"firewall.default_input_policy must be one of: {', '.join(VALID_FIREWALL_POLICIES)}"
            )
    
    # Validate allow_established
    if "allow_established" in firewall and not isinstance(firewall["allow_established"], bool):
        raise ValidationError("firewall.allow_established must be a boolean")
    
    # Validate allow_loopback
    if "allow_loopback" in firewall and not isinstance(firewall["allow_loopback"], bool):
        raise ValidationError("firewall.allow_loopback must be a boolean")
    
    # Validate address groups
    address_groups: Set[str] = set()
    if "address_groups" in firewall:
        if not isinstance(firewall["address_groups"], dict):
            raise ValidationError("firewall.address_groups must be a dictionary")
        
        for group_name, group_config in firewall["address_groups"].items():
            if not isinstance(group_name, str):
                raise ValidationError("Address group name must be a string")
            address_groups.add(group_name)
            
            if not isinstance(group_config, dict):
                raise ValidationError(f"firewall.address_groups.{group_name} must be a dictionary")
            
            # Check for unknown fields
            valid_group_fields = ["description", "addresses"]
            for key in group_config.keys():
                if key not in valid_group_fields:
                    raise ValidationError(
                        f"Unknown field in firewall.address_groups.{group_name}: {key}"
                    )
            
            # Require addresses
            if "addresses" not in group_config:
                raise ValidationError(f"firewall.address_groups.{group_name}.addresses is required")
            
            addresses = group_config["addresses"]
            if not isinstance(addresses, list):
                raise ValidationError(f"firewall.address_groups.{group_name}.addresses must be a list")
            
            if not addresses:
                raise ValidationError(f"firewall.address_groups.{group_name}.addresses cannot be empty")
            
            for idx, addr in enumerate(addresses):
                _validate_ip_address(
                    addr,
                    f"firewall.address_groups.{group_name}.addresses[{idx}]"
                )
    
    # Validate services
    services: Set[str] = set()
    if "services" in firewall:
        if not isinstance(firewall["services"], dict):
            raise ValidationError("firewall.services must be a dictionary")
        
        for service_name, service_config in firewall["services"].items():
            if not isinstance(service_name, str):
                raise ValidationError("Service name must be a string")
            services.add(service_name)
            
            if not isinstance(service_config, dict):
                raise ValidationError(f"firewall.services.{service_name} must be a dictionary")
            
            # Check for unknown fields
            valid_service_fields = ["protocol", "ports"]
            for key in service_config.keys():
                if key not in valid_service_fields:
                    raise ValidationError(f"Unknown field in firewall.services.{service_name}: {key}")
            
            # Require protocol and ports
            if "protocol" not in service_config:
                raise ValidationError(f"firewall.services.{service_name}.protocol is required")
            if "ports" not in service_config:
                raise ValidationError(f"firewall.services.{service_name}.ports is required")
            
            # Validate protocol
            protocol = service_config["protocol"]
            if not isinstance(protocol, str):
                raise ValidationError(f"firewall.services.{service_name}.protocol must be a string")
            if protocol not in VALID_PROTOCOLS:
                raise ValidationError(
                    f"firewall.services.{service_name}.protocol must be one of: {', '.join(VALID_PROTOCOLS)}"
                )
            
            # Validate ports
            ports = service_config["ports"]
            if not isinstance(ports, list):
                raise ValidationError(f"firewall.services.{service_name}.ports must be a list")
            if not ports:
                raise ValidationError(f"firewall.services.{service_name}.ports cannot be empty")
            
            for idx, port in enumerate(ports):
                if not isinstance(port, int):
                    raise ValidationError(
                        f"firewall.services.{service_name}.ports[{idx}] must be an integer"
                    )
                if port < 1 or port > 65535:
                    raise ValidationError(
                        f"firewall.services.{service_name}.ports[{idx}] must be 1-65535"
                    )
    
    # Validate input rules
    if "input_rules" in firewall:
        if not isinstance(firewall["input_rules"], list):
            raise ValidationError("firewall.input_rules must be a list")
        
        for idx, rule in enumerate(firewall["input_rules"]):
            if not isinstance(rule, dict):
                raise ValidationError(f"firewall.input_rules[{idx}] must be a dictionary")
            
            # Check for unknown fields
            valid_rule_fields = ["comment", "source_groups", "service", "action", "log", "log_prefix"]
            for key in rule.keys():
                if key not in valid_rule_fields:
                    raise ValidationError(f"Unknown field in firewall.input_rules[{idx}]: {key}")
            
            # Require action
            if "action" not in rule:
                raise ValidationError(f"firewall.input_rules[{idx}].action is required")
            
            # Validate action
            action = rule["action"]
            if not isinstance(action, str):
                raise ValidationError(f"firewall.input_rules[{idx}].action must be a string")
            if action not in VALID_FIREWALL_ACTIONS:
                raise ValidationError(
                    f"firewall.input_rules[{idx}].action must be one of: {', '.join(VALID_FIREWALL_ACTIONS)}"
                )
            
            # Validate comment
            if "comment" in rule and not isinstance(rule["comment"], str):
                raise ValidationError(f"firewall.input_rules[{idx}].comment must be a string")
            
            # Validate source_groups
            if "source_groups" in rule:
                source_groups = rule["source_groups"]
                if not isinstance(source_groups, list):
                    raise ValidationError(f"firewall.input_rules[{idx}].source_groups must be a list")
                
                for sg_idx, group_name in enumerate(source_groups):
                    if not isinstance(group_name, str):
                        raise ValidationError(
                            f"firewall.input_rules[{idx}].source_groups[{sg_idx}] must be a string"
                        )
                    if group_name not in address_groups:
                        raise ValidationError(
                            f"firewall.input_rules[{idx}].source_groups[{sg_idx}]: "
                            f"unknown address group '{group_name}'"
                        )
            
            # Validate service
            if "service" in rule:
                service = rule["service"]
                if not isinstance(service, str):
                    raise ValidationError(f"firewall.input_rules[{idx}].service must be a string")
                if service not in services:
                    raise ValidationError(
                        f"firewall.input_rules[{idx}].service: unknown service '{service}'"
                    )
            
            # Validate log
            if "log" in rule and not isinstance(rule["log"], bool):
                raise ValidationError(f"firewall.input_rules[{idx}].log must be a boolean")
            
            # Validate log_prefix
            if "log_prefix" in rule:
                log_prefix = rule["log_prefix"]
                if not isinstance(log_prefix, str):
                    raise ValidationError(f"firewall.input_rules[{idx}].log_prefix must be a string")
                if len(log_prefix) > 29:
                    raise ValidationError(
                        f"firewall.input_rules[{idx}].log_prefix must be <= 29 characters"
                    )
    
    return address_groups, services


def _validate_healthcheck(healthcheck: Any) -> None:
    """Validate healthcheck section."""
    if not isinstance(healthcheck, dict):
        raise ValidationError("healthcheck section must be a dictionary")
    
    # Check for unknown fields
    valid_fields = [
        "interval_sec", "timeout_sec", "probe_targets",
        "failures_before_down", "successes_before_up"
    ]
    for key in healthcheck.keys():
        if key not in valid_fields:
            raise ValidationError(f"Unknown field in healthcheck section: {key}")
    
    # Validate interval_sec
    if "interval_sec" in healthcheck:
        interval = healthcheck["interval_sec"]
        if not isinstance(interval, int):
            raise ValidationError("healthcheck.interval_sec must be an integer")
        if interval < 1 or interval > 3600:
            raise ValidationError("healthcheck.interval_sec must be 1-3600")
    
    # Validate timeout_sec
    if "timeout_sec" in healthcheck:
        timeout = healthcheck["timeout_sec"]
        if not isinstance(timeout, int):
            raise ValidationError("healthcheck.timeout_sec must be an integer")
        if timeout < 1 or timeout > 60:
            raise ValidationError("healthcheck.timeout_sec must be 1-60")
    
    # Validate probe_targets
    if "probe_targets" in healthcheck:
        targets = healthcheck["probe_targets"]
        if not isinstance(targets, list):
            raise ValidationError("healthcheck.probe_targets must be a list")
        if not targets:
            raise ValidationError("healthcheck.probe_targets cannot be empty")
        
        for idx, target in enumerate(targets):
            _validate_ip_address(target, f"healthcheck.probe_targets[{idx}]", require_cidr=False)
    
    # Validate failures_before_down
    if "failures_before_down" in healthcheck:
        failures = healthcheck["failures_before_down"]
        if not isinstance(failures, int):
            raise ValidationError("healthcheck.failures_before_down must be an integer")
        if failures < 1 or failures > 100:
            raise ValidationError("healthcheck.failures_before_down must be 1-100")
    
    # Validate successes_before_up
    if "successes_before_up" in healthcheck:
        successes = healthcheck["successes_before_up"]
        if not isinstance(successes, int):
            raise ValidationError("healthcheck.successes_before_up must be an integer")
        if successes < 1 or successes > 100:
            raise ValidationError("healthcheck.successes_before_up must be 1-100")


def _validate_dns(dns: Any) -> None:
    """Validate DNS section."""
    if not isinstance(dns, dict):
        raise ValidationError("dns section must be a dictionary")
    
    # Check for unknown fields
    valid_fields = ["enabled", "fallback_servers"]
    for key in dns.keys():
        if key not in valid_fields:
            raise ValidationError(f"Unknown field in dns section: {key}")
    
    # Validate enabled
    if "enabled" in dns and not isinstance(dns["enabled"], bool):
        raise ValidationError("dns.enabled must be a boolean")
    
    # Validate fallback_servers
    if "fallback_servers" in dns:
        servers = dns["fallback_servers"]
        if not isinstance(servers, list):
            raise ValidationError("dns.fallback_servers must be a list")
        
        for idx, server in enumerate(servers):
            _validate_ip_address(server, f"dns.fallback_servers[{idx}]", require_cidr=False)


def _validate_logging(logging_config: Any) -> None:
    """Validate logging section."""
    if not isinstance(logging_config, dict):
        raise ValidationError("logging section must be a dictionary")
    
    # Check for unknown fields
    valid_fields = ["path", "level"]
    for key in logging_config.keys():
        if key not in valid_fields:
            raise ValidationError(f"Unknown field in logging section: {key}")
    
    # Validate path
    if "path" in logging_config:
        path = logging_config["path"]
        if not isinstance(path, str):
            raise ValidationError("logging.path must be a string")
        if not path:
            raise ValidationError("logging.path cannot be empty")
    
    # Validate level
    if "level" in logging_config:
        level = logging_config["level"]
        if not isinstance(level, str):
            raise ValidationError("logging.level must be a string")
        if level not in VALID_LOG_LEVELS:
            raise ValidationError(
                f"logging.level must be one of: {', '.join(VALID_LOG_LEVELS)}"
            )


def _validate_routes(routes: Any, interfaces: Set[str]) -> None:
    """Validate routes section."""
    if not isinstance(routes, list):
        raise ValidationError("routes section must be a list")
    
    for idx, route in enumerate(routes):
        if not isinstance(route, dict):
            raise ValidationError(f"routes[{idx}] must be a dictionary")
        
        # Check for unknown fields
        valid_fields = ["interface", "destinations"]
        for key in route.keys():
            if key not in valid_fields:
                raise ValidationError(f"Unknown field in routes[{idx}]: {key}")
        
        # Require interface and destinations
        if "interface" not in route:
            raise ValidationError(f"routes[{idx}].interface is required")
        if "destinations" not in route:
            raise ValidationError(f"routes[{idx}].destinations is required")
        
        # Validate interface
        interface = route["interface"]
        if not isinstance(interface, str):
            raise ValidationError(f"routes[{idx}].interface must be a string")
        if interface not in interfaces:
            raise ValidationError(f"routes[{idx}].interface: unknown interface '{interface}'")
        
        # Validate destinations
        destinations = route["destinations"]
        if not isinstance(destinations, list):
            raise ValidationError(f"routes[{idx}].destinations must be a list")
        if not destinations:
            raise ValidationError(f"routes[{idx}].destinations cannot be empty")
        
        for dest_idx, dest in enumerate(destinations):
            _validate_ip_address(dest, f"routes[{idx}].destinations[{dest_idx}]")


def _validate_ip_address(value: Any, field_name: str, require_cidr: bool = True) -> None:
    """
    Validate IP address or CIDR.
    
    Args:
        value: Value to validate
        field_name: Field name for error messages
        require_cidr: Whether to require CIDR notation (default: True)
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    
    try:
        if require_cidr:
            # Parse as network (requires /prefix)
            ipaddress.ip_network(value, strict=False)
        else:
            # Try parsing as address first, then as network
            try:
                ipaddress.ip_address(value)
            except ValueError:
                ipaddress.ip_network(value, strict=False)
    except ValueError as e:
        raise ValidationError(f"{field_name}: invalid IP address/network: {e}")
