"""
Firewall management with nftables.

Implements stateful firewall with:
- Address group sets
- Service definitions  
- Input chain with stateful filtering
- Multiple source groups per rule (OR logic)
- Per-rule logging with custom prefixes
- Integration with policy routing marks
"""

import subprocess
from typing import Dict, Any, List, Set
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


def _generate_nftables_ruleset(config: Dict[str, Any]) -> str:
    """
    Generate complete nftables ruleset.
    
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
    
    # Define address group sets
    if "address_groups" in firewall_config:
        for group_name, group_config in firewall_config["address_groups"].items():
            addresses = group_config["addresses"]
            lines.append(f"    set {group_name} {{")
            lines.append("        type ipv4_addr")
            lines.append("        flags interval")
            lines.append(f"        elements = {{ {', '.join(addresses)} }}")
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
        
        for idx, rule in enumerate(firewall_config["input_rules"]):
            comment = rule.get("comment", f"Rule {idx + 1}")
            lines.append(f"        # {comment}")
            
            rule_line = "        "
            
            # Add source group conditions (OR logic)
            if "source_groups" in rule:
                source_groups = rule["source_groups"]
                if len(source_groups) == 1:
                    rule_line += f"ip saddr @{source_groups[0]} "
                else:
                    # Multiple source groups - use OR logic
                    conditions = " || ".join([f"ip saddr @{sg}" for sg in source_groups])
                    rule_line += f"({conditions}) "
            
            # Add service conditions
            if "service" in rule:
                service_name = rule["service"]
                if service_name in services:
                    service = services[service_name]
                    protocol = service["protocol"]
                    ports = service["ports"]
                    
                    if protocol in ["tcp", "udp"]:
                        if len(ports) == 1:
                            rule_line += f"{protocol} dport {ports[0]} "
                        else:
                            port_list = ", ".join(str(p) for p in ports)
                            rule_line += f"{protocol} dport {{ {port_list} }} "
                    elif protocol == "icmp":
                        rule_line += "icmp type echo-request "
            
            # Add logging if requested
            if rule.get("log", False):
                log_prefix = rule.get("log_prefix", f"FW-{comment[:20]}: ")
                rule_line += f'log prefix "{log_prefix}" '
            
            # Add action
            action = rule["action"]
            rule_line += action
            
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
