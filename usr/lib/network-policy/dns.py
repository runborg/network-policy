"""
DNS management with failover following default route.

Manages system DNS configuration and updates it when the default
route changes during health monitoring failover.
"""

import subprocess
from pathlib import Path
from typing import Dict, Any, List, Optional

from logger import get_logger

logger = get_logger(__name__)


def apply_dns_config(config: Dict[str, Any]) -> None:
    """
    Apply DNS configuration from config.
    
    Args:
        config: Complete configuration dictionary
    """
    if "dns" not in config:
        return
    
    dns_config = config["dns"]
    
    if not dns_config.get("enabled", True):
        logger.info("DNS management disabled")
        return
    
    # Get fallback servers
    fallback_servers = dns_config.get("fallback_servers", ["8.8.8.8", "1.1.1.1"])
    
    # Update DNS to use fallback servers initially
    update_dns(fallback_servers)


def update_dns(dns_servers: List[str]) -> None:
    """
    Update system DNS servers.
    
    Args:
        dns_servers: List of DNS server IP addresses
    """
    try:
        logger.info(f"Updating DNS servers: {', '.join(dns_servers)}")
        
        # Update systemd-resolved
        # First, flush existing DNS settings
        subprocess.run(
            ["resolvectl", "flush-caches"],
            check=False,  # Don't fail if this doesn't work
            capture_output=True,
            text=True
        )
        
        # Set DNS servers globally
        for server in dns_servers:
            subprocess.run(
                ["resolvectl", "dns", server],
                check=False,
                capture_output=True,
                text=True
            )
        
        logger.info("DNS servers updated")
        
    except Exception as e:
        logger.error(f"Error updating DNS servers: {e}")
        # Don't raise - DNS update failure shouldn't stop system


def update_dns_for_interface(interface: str, dns_servers: Optional[List[str]] = None) -> None:
    """
    Update DNS servers for a specific interface.
    
    Args:
        interface: Interface name
        dns_servers: List of DNS servers (None to use interface's DHCP DNS)
    """
    try:
        if dns_servers:
            logger.info(f"Setting DNS for {interface}: {', '.join(dns_servers)}")
            
            # Set DNS for specific interface
            dns_arg = " ".join(dns_servers)
            subprocess.run(
                ["resolvectl", "dns", interface, dns_arg],
                check=True,
                capture_output=True,
                text=True
            )
        else:
            logger.info(f"Resetting DNS for {interface} to default")
            subprocess.run(
                ["resolvectl", "revert", interface],
                check=True,
                capture_output=True,
                text=True
            )
        
    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to update DNS for {interface}: {e.stderr}")
    except Exception as e:
        logger.error(f"Error updating DNS for {interface}: {e}")


def get_current_dns() -> List[str]:
    """
    Get current system DNS servers.
    
    Returns:
        List of current DNS server IP addresses
    """
    try:
        result = subprocess.run(
            ["resolvectl", "status"],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Parse DNS servers from output
        dns_servers = []
        in_dns_section = False
        
        for line in result.stdout.split("\n"):
            line = line.strip()
            
            if "DNS Servers:" in line:
                in_dns_section = True
                # Extract IP from same line if present
                parts = line.split(":")
                if len(parts) > 1:
                    ip = parts[1].strip()
                    if ip:
                        dns_servers.append(ip)
            elif in_dns_section:
                # Check if this is a DNS server IP
                if line and not line.startswith(("Link", "Current", "DNSSEC", "Protocols")):
                    dns_servers.append(line)
                else:
                    in_dns_section = False
        
        return dns_servers
        
    except Exception as e:
        logger.error(f"Error getting current DNS servers: {e}")
        return []


def get_default_interface() -> Optional[str]:
    """
    Get the current default route interface.
    
    Returns:
        Interface name or None if no default route
    """
    try:
        result = subprocess.run(
            ["ip", "-o", "route", "show", "default"],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Parse output: "default via X.X.X.X dev INTERFACE ..."
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            
            parts = line.split()
            try:
                dev_idx = parts.index("dev")
                if dev_idx + 1 < len(parts):
                    return parts[dev_idx + 1]
            except (ValueError, IndexError):
                continue
        
        return None
        
    except subprocess.CalledProcessError:
        return None
    except Exception as e:
        logger.error(f"Error getting default interface: {e}")
        return None


def update_dns_for_default_route(config: Dict[str, Any]) -> None:
    """
    Update DNS based on current default route interface.
    
    Args:
        config: Complete configuration dictionary
    """
    if "dns" not in config or not config["dns"].get("enabled", True):
        return
    
    default_iface = get_default_interface()
    
    if not default_iface:
        logger.warning("No default route found, using fallback DNS")
        fallback_servers = config["dns"].get("fallback_servers", ["8.8.8.8", "1.1.1.1"])
        update_dns(fallback_servers)
        return
    
    logger.info(f"Default route via {default_iface}")
    
    # Check if interface has custom DNS in config
    dns_servers = None
    
    # Check all interface types
    for iface_type in ["ethernet", "wifi", "lte", "wireguard"]:
        if iface_type in config and default_iface in config[iface_type]:
            iface_config = config[iface_type][default_iface]
            if "dns" in iface_config:
                dns_servers = iface_config["dns"]
                break
    
    # Update DNS
    if dns_servers:
        logger.info(f"Using custom DNS from config: {', '.join(dns_servers)}")
        update_dns(dns_servers)
    else:
        logger.info(f"Using DHCP DNS from {default_iface}")
        update_dns_for_interface(default_iface, None)
