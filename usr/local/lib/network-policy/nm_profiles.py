"""
NetworkManager profile generation.

Generates NetworkManager connection profiles for Ethernet, WiFi, LTE,
and WireGuard interfaces from configuration.
"""

import subprocess
import uuid
from pathlib import Path
from typing import Dict, Any, List

from .logger import get_logger

logger = get_logger(__name__)


def apply_nm_profiles(config: Dict[str, Any]) -> None:
    """
    Generate and apply all NetworkManager profiles from config.
    
    Args:
        config: Complete configuration dictionary
    """
    # Remove existing network-policy managed connections
    cleanup_existing_profiles()
    
    # Generate Ethernet profiles
    if "ethernet" in config:
        for iface_name, iface_config in config["ethernet"].items():
            if iface_config.get("enabled", True):
                create_ethernet_profile(iface_name, iface_config)
    
    # Generate WiFi profiles
    if "wifi" in config:
        for iface_name, iface_config in config["wifi"].items():
            if iface_config.get("enabled", True):
                create_wifi_profile(iface_name, iface_config)
    
    # Generate LTE profiles
    if "lte" in config:
        for iface_name, iface_config in config["lte"].items():
            if iface_config.get("enabled", True):
                create_lte_profile(iface_name, iface_config)
    
    # Generate WireGuard profiles
    if "wireguard" in config:
        for iface_name, iface_config in config["wireguard"].items():
            if iface_config.get("enabled", True):
                create_wireguard_profile(iface_name, iface_config)


def cleanup_existing_profiles() -> None:
    """Remove existing network-policy managed profiles."""
    try:
        # List connections managed by network-policy
        result = subprocess.run(
            ["nmcli", "-t", "-f", "NAME,UUID", "connection", "show"],
            check=True,
            capture_output=True,
            text=True
        )
        
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            
            parts = line.split(":")
            if len(parts) >= 2:
                name = parts[0]
                conn_uuid = parts[1]
                
                # Delete connections with network-policy prefix
                if name.startswith("network-policy-"):
                    logger.info(f"Removing existing profile: {name}")
                    subprocess.run(
                        ["nmcli", "connection", "delete", conn_uuid],
                        check=True,
                        capture_output=True,
                        text=True
                    )
    except subprocess.CalledProcessError as e:
        logger.warning(f"Error cleaning up existing profiles: {e}")


def create_ethernet_profile(iface_name: str, config: Dict[str, Any]) -> None:
    """
    Create Ethernet connection profile.
    
    Args:
        iface_name: Interface name (e.g., "eth0")
        config: Interface configuration
    """
    try:
        logger.info(f"Creating Ethernet profile for {iface_name}")
        
        conn_name = f"network-policy-{iface_name}"
        method = config.get("method", "auto")
        
        # Build nmcli command
        cmd = [
            "nmcli", "connection", "add",
            "type", "ethernet",
            "con-name", conn_name,
            "ifname", iface_name,
            "autoconnect", "yes"
        ]
        
        # Set IP method
        if method == "dhcp":
            cmd.extend(["ipv4.method", "auto"])
        elif method == "static":
            cmd.extend(["ipv4.method", "manual"])
            cmd.extend(["ipv4.addresses", config["address"]])
            
            if "gateway" in config:
                cmd.extend(["ipv4.gateway", config["gateway"]])
            
            if "dns" in config:
                cmd.extend(["ipv4.dns", ",".join(config["dns"])])
        else:  # auto
            cmd.extend(["ipv4.method", "auto"])
        
        # Set MTU if specified
        if "mtu" in config:
            cmd.extend(["ethernet.mtu", str(config["mtu"])])
        
        # Create connection
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Set connection priority
        if "priority" in config:
            subprocess.run(
                ["nmcli", "connection", "modify", conn_name,
                 "connection.autoconnect-priority", str(config["priority"])],
                check=True,
                capture_output=True,
                text=True
            )
        
        logger.info(f"Ethernet profile created: {conn_name}")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create Ethernet profile for {iface_name}: {e.stderr}")
        raise


def create_wifi_profile(iface_name: str, config: Dict[str, Any]) -> None:
    """
    Create WiFi connection profile.
    
    Args:
        iface_name: Interface name (e.g., "wlan0")
        config: Interface configuration
    """
    try:
        logger.info(f"Creating WiFi profile for {iface_name}")
        
        conn_name = f"network-policy-{iface_name}"
        ssid = config["ssid"]
        method = config.get("method", "auto")
        
        # Build nmcli command
        cmd = [
            "nmcli", "connection", "add",
            "type", "wifi",
            "con-name", conn_name,
            "ifname", iface_name,
            "ssid", ssid,
            "autoconnect", "yes"
        ]
        
        # Set WiFi security if PSK provided
        if "psk" in config:
            cmd.extend([
                "wifi-sec.key-mgmt", "wpa-psk",
                "wifi-sec.psk", config["psk"]
            ])
        
        # Set IP method
        if method == "dhcp":
            cmd.extend(["ipv4.method", "auto"])
        elif method == "static":
            cmd.extend(["ipv4.method", "manual"])
            cmd.extend(["ipv4.addresses", config["address"]])
            
            if "gateway" in config:
                cmd.extend(["ipv4.gateway", config["gateway"]])
            
            if "dns" in config:
                cmd.extend(["ipv4.dns", ",".join(config["dns"])])
        else:  # auto
            cmd.extend(["ipv4.method", "auto"])
        
        # Create connection
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Set connection priority
        if "priority" in config:
            subprocess.run(
                ["nmcli", "connection", "modify", conn_name,
                 "connection.autoconnect-priority", str(config["priority"])],
                check=True,
                capture_output=True,
                text=True
            )
        
        logger.info(f"WiFi profile created: {conn_name}")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create WiFi profile for {iface_name}: {e.stderr}")
        raise


def create_lte_profile(iface_name: str, config: Dict[str, Any]) -> None:
    """
    Create LTE/ModemManager connection profile.
    
    Args:
        iface_name: Interface name (e.g., "wwan0")
        config: Interface configuration
    """
    try:
        logger.info(f"Creating LTE profile for {iface_name}")
        
        conn_name = f"network-policy-{iface_name}"
        apn = config["apn"]
        
        # Build nmcli command
        cmd = [
            "nmcli", "connection", "add",
            "type", "gsm",
            "con-name", conn_name,
            "ifname", iface_name,
            "apn", apn,
            "autoconnect", "yes"
        ]
        
        # Add user if provided
        if "user" in config:
            cmd.extend(["gsm.username", config["user"]])
        
        # Add password if provided
        if "password" in config:
            cmd.extend(["gsm.password", config["password"]])
        
        # Add PIN if provided
        if "pin" in config:
            cmd.extend(["gsm.pin", config["pin"]])
        
        # Create connection
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Set connection priority
        if "priority" in config:
            subprocess.run(
                ["nmcli", "connection", "modify", conn_name,
                 "connection.autoconnect-priority", str(config["priority"])],
                check=True,
                capture_output=True,
                text=True
            )
        
        logger.info(f"LTE profile created: {conn_name}")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create LTE profile for {iface_name}: {e.stderr}")
        raise


def create_wireguard_profile(iface_name: str, config: Dict[str, Any]) -> None:
    """
    Create WireGuard connection profile.
    
    Args:
        iface_name: Interface name (e.g., "wg0")
        config: Interface configuration
    """
    try:
        logger.info(f"Creating WireGuard profile for {iface_name}")
        
        conn_name = f"network-policy-{iface_name}"
        
        # Build nmcli command
        cmd = [
            "nmcli", "connection", "add",
            "type", "wireguard",
            "con-name", conn_name,
            "ifname", iface_name,
            "autoconnect", "yes",
            "wireguard.private-key", config["private_key"],
            "ipv4.method", "manual",
            "ipv4.addresses", config["address"]
        ]
        
        # Set listen port if provided
        if "listen_port" in config:
            cmd.extend(["wireguard.listen-port", str(config["listen_port"])])
        
        # Set DNS if provided
        if "dns" in config:
            cmd.extend(["ipv4.dns", ",".join(config["dns"])])
        
        # Create connection
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Add peer configuration
        peer_cmd = [
            "nmcli", "connection", "modify", conn_name,
            "wireguard.peer",
            config["peer_public_key"]
        ]
        
        # Build peer arguments
        peer_args = []
        
        if "peer_endpoint" in config:
            peer_args.append(f"endpoint={config['peer_endpoint']}")
        
        if "peer_allowed_ips" in config:
            allowed_ips = ",".join(config["peer_allowed_ips"])
            peer_args.append(f"allowed-ips={allowed_ips}")
        
        if "peer_preshared_key" in config:
            peer_args.append(f"preshared-key={config['peer_preshared_key']}")
        
        if "peer_keepalive" in config:
            peer_args.append(f"persistent-keepalive={config['peer_keepalive']}")
        
        # Add peer arguments
        if peer_args:
            peer_cmd.extend(peer_args)
        
        subprocess.run(peer_cmd, check=True, capture_output=True, text=True)
        
        logger.info(f"WireGuard profile created: {conn_name}")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to create WireGuard profile for {iface_name}: {e.stderr}")
        raise
