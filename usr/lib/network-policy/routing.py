"""
Policy routing with per-interface routing tables.

Implements policy-based routing with:
- Dynamic interface-to-table mapping
- Connection tracking marks per interface
- nftables policy routing (prerouting, output, postrouting)
- fwmark-based routing rules
- Source-based routing rules
- Priority-based failover
"""

import subprocess
from typing import Dict, Any, List, Set

from logger import get_logger

logger = get_logger(__name__)

# Base routing table number
BASE_TABLE = 100

# Base connection mark
BASE_MARK = 0x100


def apply_routing_config(config: Dict[str, Any]) -> None:
    """
    Apply policy routing configuration.
    
    Args:
        config: Complete configuration dictionary
    """
    # Build interface map
    interface_map = _build_interface_map(config)
    
    if not interface_map:
        logger.info("No enabled interfaces, skipping routing configuration")
        return
    
    logger.info(f"Configuring policy routing for {len(interface_map)} interfaces")
    
    # Setup routing tables
    _setup_routing_tables(interface_map)
    
    # Setup routing rules
    _setup_routing_rules(interface_map, config)
    
    # Setup static routes if configured
    if "routes" in config:
        _setup_static_routes(config["routes"], interface_map)
    
    logger.info("Policy routing configured")


def _build_interface_map(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Build map of enabled interfaces with table and mark assignments.
    
    Returns:
        Dict mapping interface names to config with table/mark info
    """
    interface_map = {}
    table_num = BASE_TABLE
    
    # Process all interface types
    for iface_type in ["ethernet", "wifi", "lte", "wireguard"]:
        if iface_type not in config:
            continue
        
        for iface_name, iface_config in config[iface_type].items():
            if not iface_config.get("enabled", True):
                continue
            
            priority = iface_config.get("priority", 100)
            
            interface_map[iface_name] = {
                "type": iface_type,
                "priority": priority,
                "table": table_num,
                "mark": BASE_MARK + (table_num - BASE_TABLE),
                "config": iface_config
            }
            
            table_num += 1
    
    return interface_map


def _setup_routing_tables(interface_map: Dict[str, Dict[str, Any]]) -> None:
    """
    Setup per-interface routing tables.
    
    Args:
        interface_map: Interface mapping with table assignments
    """
    # Update /etc/iproute2/rt_tables if needed
    try:
        rt_tables_path = "/etc/iproute2/rt_tables"
        
        # Read existing content
        with open(rt_tables_path, 'r') as f:
            existing_lines = f.readlines()
        
        # Filter out old network-policy entries
        new_lines = [line for line in existing_lines 
                     if not line.strip().endswith("# network-policy")]
        
        # Add new entries
        for iface_name, iface_info in interface_map.items():
            table_num = iface_info["table"]
            new_lines.append(f"{table_num}\t{iface_name}\t# network-policy\n")
        
        # Write back
        with open(rt_tables_path, 'w') as f:
            f.writelines(new_lines)
        
        logger.debug("Updated /etc/iproute2/rt_tables")
        
    except Exception as e:
        logger.warning(f"Failed to update rt_tables: {e}")
    
    # Populate routing tables
    for iface_name, iface_info in interface_map.items():
        _populate_interface_table(iface_name, iface_info)


def _populate_interface_table(iface_name: str, iface_info: Dict[str, Any]) -> None:
    """
    Populate routing table for an interface.
    
    Args:
        iface_name: Interface name
        iface_info: Interface info with table number
    """
    try:
        table_num = iface_info["table"]
        
        # Flush existing routes in table
        subprocess.run(
            ["ip", "route", "flush", "table", str(table_num)],
            check=False,
            capture_output=True,
            text=True
        )
        
        # Get interface IP and gateway
        result = subprocess.run(
            ["ip", "-o", "addr", "show", iface_name],
            check=True,
            capture_output=True,
            text=True
        )
        
        # Parse IP address
        ip_addr = None
        for line in result.stdout.split("\n"):
            if "inet " in line:
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "inet" and i + 1 < len(parts):
                        ip_addr = parts[i + 1]
                        break
                break
        
        if not ip_addr:
            logger.warning(f"No IP address found for {iface_name}")
            return
        
        # Extract network from IP
        network_parts = ip_addr.split('/')
        if len(network_parts) != 2:
            logger.warning(f"Invalid IP format for {iface_name}: {ip_addr}")
            return
        
        # Add local network route
        subprocess.run(
            ["ip", "route", "add", ip_addr.split('/')[0], "dev", iface_name, 
             "scope", "link", "table", str(table_num)],
            check=False,
            capture_output=True,
            text=True
        )
        
        # Try to get default gateway
        result = subprocess.run(
            ["ip", "route", "show", "dev", iface_name],
            check=True,
            capture_output=True,
            text=True
        )
        
        gateway = None
        for line in result.stdout.split("\n"):
            if "default via" in line or "via" in line:
                parts = line.split()
                try:
                    via_idx = parts.index("via")
                    if via_idx + 1 < len(parts):
                        gateway = parts[via_idx + 1]
                        break
                except ValueError:
                    continue
        
        # If no gateway found from routes, try config
        if not gateway and "gateway" in iface_info["config"]:
            gateway = iface_info["config"]["gateway"]
        
        # Add default route if we have a gateway
        if gateway:
            subprocess.run(
                ["ip", "route", "add", "default", "via", gateway,
                 "dev", iface_name, "table", str(table_num)],
                check=False,
                capture_output=True,
                text=True
            )
            logger.debug(f"Added default route via {gateway} for {iface_name} (table {table_num})")
        else:
            logger.warning(f"No gateway found for {iface_name}")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error populating routing table for {iface_name}: {e.stderr}")
    except Exception as e:
        logger.error(f"Error populating routing table for {iface_name}: {e}")


def _setup_routing_rules(interface_map: Dict[str, Dict[str, Any]], config: Dict[str, Any]) -> None:
    """
    Setup IP routing rules for policy routing.
    
    Args:
        interface_map: Interface mapping with table/mark assignments
        config: Complete configuration
    """
    try:
        # Flush old network-policy rules (tables 100-199)
        for table_num in range(BASE_TABLE, BASE_TABLE + 100):
            subprocess.run(
                ["ip", "rule", "del", "table", str(table_num)],
                check=False,
                capture_output=True,
                text=True
            )
            subprocess.run(
                ["ip", "rule", "del", "fwmark", hex(BASE_MARK + (table_num - BASE_TABLE)),
                 "table", str(table_num)],
                check=False,
                capture_output=True,
                text=True
            )
        
        # Add fwmark-based rules for each interface
        for iface_name, iface_info in interface_map.items():
            table_num = iface_info["table"]
            mark = iface_info["mark"]
            
            # Add fwmark rule
            subprocess.run(
                ["ip", "rule", "add", "fwmark", hex(mark), "table", str(table_num)],
                check=True,
                capture_output=True,
                text=True
            )
            
            logger.debug(f"Added fwmark rule: mark {hex(mark)} -> table {table_num} ({iface_name})")
        
        # Add priority-based fallback rules (highest priority = lowest number)
        sorted_ifaces = sorted(
            interface_map.items(),
            key=lambda x: x[1]["priority"]
        )
        
        for iface_name, iface_info in sorted_ifaces:
            table_num = iface_info["table"]
            priority = iface_info["priority"]
            
            # Add priority-based rule (higher table priority for lower priority numbers)
            rule_priority = 10000 + priority
            subprocess.run(
                ["ip", "rule", "add", "priority", str(rule_priority),
                 "table", str(table_num)],
                check=False,
                capture_output=True,
                text=True
            )
            
            logger.debug(f"Added priority rule: priority {rule_priority} -> table {table_num} ({iface_name})")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error setting up routing rules: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error setting up routing rules: {e}")
        raise


def _setup_static_routes(routes: List[Dict[str, Any]], interface_map: Dict[str, Dict[str, Any]]) -> None:
    """
    Setup static routes for specific interfaces.
    
    Args:
        routes: List of route configurations
        interface_map: Interface mapping with table assignments
    """
    for route in routes:
        iface_name = route["interface"]
        destinations = route["destinations"]
        
        if iface_name not in interface_map:
            logger.warning(f"Interface {iface_name} not found for static route")
            continue
        
        table_num = interface_map[iface_name]["table"]
        
        for dest in destinations:
            try:
                # Add route to interface table
                subprocess.run(
                    ["ip", "route", "add", dest, "dev", iface_name, "table", str(table_num)],
                    check=True,
                    capture_output=True,
                    text=True
                )
                
                # Also add to main table
                subprocess.run(
                    ["ip", "route", "add", dest, "dev", iface_name],
                    check=False,
                    capture_output=True,
                    text=True
                )
                
                logger.info(f"Added static route {dest} via {iface_name}")
                
            except subprocess.CalledProcessError as e:
                logger.warning(f"Failed to add static route {dest} via {iface_name}: {e.stderr}")


def get_interface_table_map(config: Dict[str, Any]) -> Dict[str, int]:
    """
    Get interface to routing table mapping.
    
    Args:
        config: Complete configuration dictionary
        
    Returns:
        Dict mapping interface names to table numbers
    """
    interface_map = _build_interface_map(config)
    return {iface: info["table"] for iface, info in interface_map.items()}


def get_interface_mark_map(config: Dict[str, Any]) -> Dict[str, int]:
    """
    Get interface to connection mark mapping.
    
    Args:
        config: Complete configuration dictionary
        
    Returns:
        Dict mapping interface names to mark values
    """
    interface_map = _build_interface_map(config)
    return {iface: info["mark"] for iface, info in interface_map.items()}
