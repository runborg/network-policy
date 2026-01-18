"""
Firewall management with nftables.

Implements stateful firewall with:
- Address group sets (IPv4 and IPv6)
- Service definitions  
- Input chain with stateful filtering
- Multiple source groups per rule (OR logic)
- Per-rule logging with custom prefixes
- Integration with policy routing marks
- Full IPv6 support
"""

import subprocess
import ipaddress
from typing import Dict, Any, List, Set, Tuple
from pathlib import Path

from .logger import get_logger
from .routing import get_interface_mark_map

logger = get_logger(__name__)


def apply_firewall_config(config: Dict[str, Any]) -> None:
    """
    Apply firewall configuration using nftables.
    
    Args:
        config: Complete configuration dictionary
    """
    if "firewall" not in config:
        logger.info("No firewall configuration, skipping")
        return
    
    firewall_config = config["firewall"]
    
    if not firewall_config.get("enabled", True):
        logger.info("Firewall disabled, removing rules")
        _cleanup_firewall()
        return
    
    logger.info("Configuring firewall")
    
    # Generate nftables ruleset
    ruleset = _generate_nftables_ruleset(config)
    
    # Apply ruleset
    _apply_nftables_ruleset(ruleset)
    
    logger.info("Firewall configured successfully")


def _cleanup_firewall() -> None:
    """Remove network-policy firewall rules."""
    try:
        subprocess.run(
            ["nft", "delete", "table", "inet", "network-policy"],
            check=False,
            capture_output=True,
            text=True
        )
        logger.info("Firewall rules removed")
    except Exception as e:
        logger.error(f"Error removing firewall rules: {e}")


def _classify_addresses(addresses: List[str]) -> Tuple[List[str], List[str]]:
    """
    Classify addresses into IPv4 and IPv6.
    
    Args:
        addresses: List of IP addresses/networks
        
    Returns:
        Tuple of (ipv4_addresses, ipv6_addresses)
    """
    ipv4_addrs = []
    ipv6_addrs = []
    
    for addr in addresses:
        try:
            # Parse the address/network
            ip_net = ipaddress.ip_network(addr, strict=False)
            if ip_net.version == 4:
                ipv4_addrs.append(addr)
            else:
                ipv6_addrs.append(addr)
        except ValueError:
            # If parsing fails, skip (should have been caught in validation)
            logger.warning(f"Skipping invalid address in firewall: {addr}")
    
    return ipv4_addrs, ipv6_addrs


def _generate_service_match(service: Dict[str, Any], ipv6: bool = False) -> str:
    """
    Generate nftables match expression for a service.
    
    Args:
        service: Service configuration dictionary
        ipv6: If True, generate IPv6-specific match (for ICMP)
        
    Returns:
        nftables match expression string
    """
    protocol = service["protocol"]
    ports = service["ports"]
    
    if protocol in ["tcp", "udp"]:
        if len(ports) == 1:
            return f"{protocol} dport {ports[0]} "
        else:
            port_list = ", ".join(str(p) for p in ports)
            return f"{protocol} dport {{ {port_list} }} "
    elif protocol == "icmp":
        # Use icmpv6 for IPv6, icmp for IPv4
        if ipv6:
            return "icmpv6 type echo-request "
        else:
            return "icmp type echo-request "
    
    return ""


def _generate_nftables_ruleset(config: Dict[str, Any]) -> str:
    """
    Generate complete nftables ruleset with IPv4 and IPv6 support.
    
    Args:
        config: Complete configuration dictionary
        
    Returns:
        nftables ruleset as string
    """
    firewall_config = config["firewall"]
    
    lines = []
    lines.append("#!/usr/sbin/nft -f")
    lines.append("")
    lines.append("# Network Policy Firewall")
    lines.append("# Auto-generated - do not edit manually")
    lines.append("")
    
    # Flush and recreate table
    lines.append("flush table inet network-policy 2>/dev/null")
    lines.append("table inet network-policy {")
    lines.append("")
    
    # Define address group sets (separate IPv4 and IPv6)
    if "address_groups" in firewall_config:
        for group_name, group_config in firewall_config["address_groups"].items():
            addresses = group_config["addresses"]
            ipv4_addrs, ipv6_addrs = _classify_addresses(addresses)
            
            # Create IPv4 set if there are IPv4 addresses
            if ipv4_addrs:
                lines.append(f"    set {group_name}_v4 {{")
                lines.append("        type ipv4_addr")
                lines.append("        flags interval")
                lines.append(f"        elements = {{ {', '.join(ipv4_addrs)} }}")
                lines.append("    }")
                lines.append("")
            
            # Create IPv6 set if there are IPv6 addresses
            if ipv6_addrs:
                lines.append(f"    set {group_name}_v6 {{")
                lines.append("        type ipv6_addr")
                lines.append("        flags interval")
                lines.append(f"        elements = {{ {', '.join(ipv6_addrs)} }}")
                lines.append("    }")
                lines.append("")
    
    # Input chain
    lines.append("    chain input {")
    lines.append("        type filter hook input priority filter; policy drop;")
    lines.append("")
    
    # Default stateful rules
    if firewall_config.get("allow_established", True):
        lines.append("        # Allow established and related connections")
        lines.append("        ct state established,related accept")
        lines.append("")
    
    if firewall_config.get("allow_loopback", True):
        lines.append("        # Allow loopback")
        lines.append("        iif lo accept")
        lines.append("")
    
    # Add custom input rules
    if "input_rules" in firewall_config:
        services = firewall_config.get("services", {})
        address_groups = firewall_config.get("address_groups", {})
        
        for idx, rule in enumerate(firewall_config["input_rules"]):
            comment = rule.get("comment", f"Rule {idx + 1}")
            lines.append(f"        # {comment}")
            
            # Build conditions for IPv4 and IPv6 separately if needed
            has_source_groups = "source_groups" in rule
            has_service = "service" in rule
            
            if has_source_groups:
                # Need to generate separate rules for IPv4 and IPv6
                source_groups = rule["source_groups"]
                
                # Check which groups have IPv4/IPv6 addresses
                has_ipv4 = any(
                    _classify_addresses(address_groups[sg]["addresses"])[0]
                    for sg in source_groups
                )
                has_ipv6 = any(
                    _classify_addresses(address_groups[sg]["addresses"])[1]
                    for sg in source_groups
                )
                
                # Generate IPv4 rule if applicable
                if has_ipv4:
                    rule_line = "        "
                    
                    # Add source group conditions (OR logic)
                    if len(source_groups) == 1:
                        rule_line += f"ip saddr @{source_groups[0]}_v4 "
                    else:
                        # Multiple source groups - use OR logic
                        conditions = " || ".join([f"ip saddr @{sg}_v4" for sg in source_groups])
                        rule_line += f"({conditions}) "
                    
                    # Add service conditions
                    if has_service:
                        rule_line += _generate_service_match(services[rule["service"]])
                    
                    # Add logging if requested
                    if rule.get("log", False):
                        log_prefix = rule.get("log_prefix", f"FW-{comment[:20]}: ")
                        rule_line += f'log prefix "{log_prefix}" '
                    
                    # Add action
                    rule_line += rule["action"]
                    lines.append(rule_line)
                
                # Generate IPv6 rule if applicable
                if has_ipv6:
                    rule_line = "        "
                    
                    # Add source group conditions (OR logic)
                    if len(source_groups) == 1:
                        rule_line += f"ip6 saddr @{source_groups[0]}_v6 "
                    else:
                        # Multiple source groups - use OR logic
                        conditions = " || ".join([f"ip6 saddr @{sg}_v6" for sg in source_groups])
                        rule_line += f"({conditions}) "
                    
                    # Add service conditions
                    if has_service:
                        rule_line += _generate_service_match(services[rule["service"]], ipv6=True)
                    
                    # Add logging if requested
                    if rule.get("log", False):
                        log_prefix = rule.get("log_prefix", f"FW-{comment[:20]}: ")
                        rule_line += f'log prefix "{log_prefix}" '
                    
                    # Add action
                    rule_line += rule["action"]
                    lines.append(rule_line)
            else:
                # No source groups - single rule for both IPv4 and IPv6
                rule_line = "        "
                
                # Add service conditions
                if has_service:
                    # Generate match that works for both IPv4 and IPv6
                    service = services[rule["service"]]
                    protocol = service["protocol"]
                    ports = service["ports"]
                    
                    if protocol in ["tcp", "udp"]:
                        if len(ports) == 1:
                            rule_line += f"{protocol} dport {ports[0]} "
                        else:
                            port_list = ", ".join(str(p) for p in ports)
                            rule_line += f"{protocol} dport {{ {port_list} }} "
                    elif protocol == "icmp":
                        # For ICMP without source filtering, match both IPv4 and IPv6
                        rule_line += "meta l4proto { icmp, icmpv6 } "
                
                # Add logging if requested
                if rule.get("log", False):
                    log_prefix = rule.get("log_prefix", f"FW-{comment[:20]}: ")
                    rule_line += f'log prefix "{log_prefix}" '
                
                # Add action
                rule_line += rule["action"]
                lines.append(rule_line)
            
            lines.append("")
    
    # Default policy
    default_policy = firewall_config.get("default_input_policy", "drop")
    lines.append(f"        # Default policy: {default_policy}")
    lines.append(f"        {default_policy}")
    lines.append("    }")
    lines.append("")
    
    # Forward chain (allow all by default, can be customized later)
    lines.append("    chain forward {")
    lines.append("        type filter hook forward priority filter; policy accept;")
    lines.append("        ct state established,related accept")
    lines.append("    }")
    lines.append("")
    
    # Policy routing chains for connection marking
    interface_marks = get_interface_mark_map(config)
    
    if interface_marks:
        lines.append("    # Policy routing connection tracking")
        lines.append("")
        
        # Prerouting chain for marking incoming connections
        lines.append("    chain prerouting {")
        lines.append("        type filter hook prerouting priority mangle; policy accept;")
        lines.append("")
        
        for iface, mark in interface_marks.items():
            lines.append(f"        # Mark connections from {iface}")
            lines.append(f"        iif {iface} ct mark 0 ct mark set {hex(mark)}")
        
        lines.append("    }")
        lines.append("")
        
        # Output chain for marking locally-generated traffic
        lines.append("    chain output {")
        lines.append("        type route hook output priority mangle; policy accept;")
        lines.append("")
        lines.append("        # Restore connection mark to packet mark")
        lines.append("        ct mark != 0 meta mark set ct mark")
        lines.append("    }")
        lines.append("")
        
        # Postrouting chain for saving packet mark to connection
        lines.append("    chain postrouting {")
        lines.append("        type filter hook postrouting priority mangle; policy accept;")
        lines.append("")
        lines.append("        # Save packet mark to connection mark")
        lines.append("        meta mark != 0 ct mark set meta mark")
        lines.append("    }")
        lines.append("")
    
    lines.append("}")
    
    return "\n".join(lines)


def _apply_nftables_ruleset(ruleset: str) -> None:
    """
    Apply nftables ruleset.
    
    Args:
        ruleset: Complete nftables ruleset
    """
    try:
        # Write ruleset to temporary file
        ruleset_file = Path("/tmp/network-policy-nftables.conf")
        with open(ruleset_file, 'w') as f:
            f.write(ruleset)
        
        # Apply ruleset
        result = subprocess.run(
            ["nft", "-f", str(ruleset_file)],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Remove temporary file
        ruleset_file.unlink()
        
        logger.debug("nftables ruleset applied successfully")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to apply nftables ruleset: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error applying nftables ruleset: {e}")
        raise


def get_firewall_status() -> Dict[str, Any]:
    """
    Get current firewall status.
    
    Returns:
        Dictionary with firewall status information
    """
    try:
        result = subprocess.run(
            ["nft", "list", "table", "inet", "network-policy"],
            check=True,
            capture_output=True,
            text=True
        )
        
        return {
            "enabled": True,
            "ruleset": result.stdout
        }
        
    except subprocess.CalledProcessError:
        return {
            "enabled": False,
            "ruleset": None
        }
    except Exception as e:
        logger.error(f"Error getting firewall status: {e}")
        return {
            "enabled": False,
            "error": str(e)
        }


def reload_firewall(config: Dict[str, Any]) -> None:
    """
    Reload firewall configuration.
    
    Args:
        config: Complete configuration dictionary
    """
    logger.info("Reloading firewall configuration")
    apply_firewall_config(config)


def show_firewall_rules() -> str:
    """
    Get formatted firewall rules.
    
    Returns:
        Formatted firewall rules as string
    """
    try:
        result = subprocess.run(
            ["nft", "list", "table", "inet", "network-policy"],
            check=True,
            capture_output=True,
            text=True
        )
        
        return result.stdout
        
    except subprocess.CalledProcessError as e:
        return f"Error: {e.stderr}"
    except Exception as e:
        return f"Error: {e}"


def test_firewall_syntax(config: Dict[str, Any]) -> bool:
    """
    Test firewall configuration syntax without applying.
    
    Args:
        config: Complete configuration dictionary
        
    Returns:
        True if syntax is valid, False otherwise
    """
    try:
        ruleset = _generate_nftables_ruleset(config)
        
        # Write to temporary file
        test_file = Path("/tmp/network-policy-nftables-test.conf")
        with open(test_file, 'w') as f:
            f.write(ruleset)
        
        # Test syntax
        result = subprocess.run(
            ["nft", "-c", "-f", str(test_file)],
            check=True,
            capture_output=True,
            text=True
        )
        
        test_file.unlink()
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Firewall syntax error: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Error testing firewall syntax: {e}")
        return False
