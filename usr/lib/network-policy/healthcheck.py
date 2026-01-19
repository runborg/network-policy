"""
Health monitoring daemon with control socket.

Monitors interface health with ICMP pings and automatic failover:
- InterfaceState class for tracking state
- ICMP ping via specific interface  
- Automatic priority rule management
- Control socket server (UNIX socket at /run/network-policy.sock)
- Reload capability
- Status reporting (JSON)
- DNS update on default route change
"""

import json
import os
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, Any, List, Optional

from logger import get_logger
from routing import get_interface_table_map
from dns import update_dns_for_default_route, get_default_interface
from config import load_config

logger = get_logger(__name__)


@dataclass
class InterfaceState:
    """State tracking for a monitored interface."""
    name: str
    priority: int
    table: int
    ip: Optional[str] = None
    gateway: Optional[str] = None
    failures: int = 0
    successes: int = 0
    active: bool = False
    last_check: Optional[float] = None
    last_success: Optional[float] = None
    last_failure: Optional[float] = None


class HealthMonitor:
    """Health monitoring daemon."""
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize health monitor.
        
        Args:
            config: Complete configuration dictionary
        """
        self.config = config
        self.running = False
        self.interfaces: Dict[str, InterfaceState] = {}
        self.socket_path = "/run/network-policy.sock"
        self.socket_server: Optional[socket.socket] = None
        
        # Get health check config
        hc_config = config.get("healthcheck", {})
        self.interval = hc_config.get("interval_sec", 30)
        self.timeout = hc_config.get("timeout_sec", 5)
        self.probe_targets = hc_config.get("probe_targets", ["8.8.8.8", "1.1.1.1"])
        self.failures_before_down = hc_config.get("failures_before_down", 3)
        self.successes_before_up = hc_config.get("successes_before_up", 2)
        
        self._initialize_interfaces()
    
    def _initialize_interfaces(self) -> None:
        """Initialize interface state tracking."""
        interface_tables = get_interface_table_map(self.config)
        
        for iface_name, table in interface_tables.items():
            # Get priority from config
            priority = 100
            for iface_type in ["ethernet", "wifi", "lte", "wireguard"]:
                if iface_type in self.config:
                    if iface_name in self.config[iface_type]:
                        priority = self.config[iface_type][iface_name].get("priority", 100)
                        break
            
            # Get interface IP and gateway
            ip_addr, gateway = self._get_interface_info(iface_name)
            
            state = InterfaceState(
                name=iface_name,
                priority=priority,
                table=table,
                ip=ip_addr,
                gateway=gateway,
                active=True  # Start optimistically
            )
            
            self.interfaces[iface_name] = state
            logger.info(f"Monitoring interface {iface_name} (priority={priority}, table={table})")
    
    def _get_interface_info(self, iface_name: str) -> tuple[Optional[str], Optional[str]]:
        """
        Get IP address and gateway for interface.
        
        Returns:
            Tuple of (ip_address, gateway)
        """
        try:
            # Get IP address
            result = subprocess.run(
                ["ip", "-o", "addr", "show", iface_name],
                check=True,
                capture_output=True,
                text=True
            )
            
            ip_addr = None
            for line in result.stdout.split("\n"):
                if "inet " in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == "inet" and i + 1 < len(parts):
                            ip_addr = parts[i + 1].split('/')[0]
                            break
                    break
            
            # Get gateway from routing table
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
            
            return ip_addr, gateway
            
        except Exception as e:
            logger.warning(f"Error getting info for {iface_name}: {e}")
            return None, None
    
    def _ping_interface(self, iface_name: str, target: str) -> bool:
        """
        Ping target via specific interface.
        
        Args:
            iface_name: Interface to use for ping
            target: Target IP address
            
        Returns:
            True if ping successful, False otherwise
        """
        try:
            result = subprocess.run(
                ["ping", "-I", iface_name, "-c", "1", "-W", str(self.timeout), target],
                check=True,
                capture_output=True,
                text=True,
                timeout=self.timeout + 1
            )
            return result.returncode == 0
            
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
        except Exception as e:
            logger.error(f"Error pinging {target} via {iface_name}: {e}")
            return False
    
    def _check_interface(self, iface_name: str) -> bool:
        """
        Check interface health by pinging all targets.
        
        Args:
            iface_name: Interface to check
            
        Returns:
            True if at least one target responds, False otherwise
        """
        state = self.interfaces[iface_name]
        state.last_check = time.time()
        
        # Try all targets
        for target in self.probe_targets:
            if self._ping_interface(iface_name, target):
                logger.debug(f"{iface_name}: Ping to {target} successful")
                return True
        
        logger.debug(f"{iface_name}: All ping targets failed")
        return False
    
    def _update_interface_state(self, iface_name: str, success: bool) -> None:
        """
        Update interface state based on check result.
        
        Args:
            iface_name: Interface name
            success: Whether check was successful
        """
        state = self.interfaces[iface_name]
        
        if success:
            state.successes += 1
            state.failures = 0  # Reset failure counter
            state.last_success = time.time()
            
            # Bring interface up if enough successes
            if not state.active and state.successes >= self.successes_before_up:
                logger.warning(f"{iface_name}: Bringing interface UP (successes={state.successes})")
                self._set_interface_active(iface_name, True)
                state.active = True
                state.successes = 0
        else:
            state.failures += 1
            state.successes = 0  # Reset success counter
            state.last_failure = time.time()
            
            # Bring interface down if enough failures
            if state.active and state.failures >= self.failures_before_down:
                logger.warning(f"{iface_name}: Bringing interface DOWN (failures={state.failures})")
                self._set_interface_active(iface_name, False)
                state.active = False
                state.failures = 0
    
    def _set_interface_active(self, iface_name: str, active: bool) -> None:
        """
        Set interface active/inactive by managing routing rules.
        
        Args:
            iface_name: Interface name
            active: Whether to activate or deactivate
        """
        try:
            state = self.interfaces[iface_name]
            table = state.table
            priority_rule = 10000 + state.priority
            
            if active:
                # Add routing rule back
                subprocess.run(
                    ["ip", "rule", "add", "priority", str(priority_rule), "table", str(table)],
                    check=True,
                    capture_output=True,
                    text=True
                )
                logger.info(f"{iface_name}: Added routing rule (priority {priority_rule})")
            else:
                # Remove routing rule
                subprocess.run(
                    ["ip", "rule", "del", "priority", str(priority_rule), "table", str(table)],
                    check=False,
                    capture_output=True,
                    text=True
                )
                logger.info(f"{iface_name}: Removed routing rule (priority {priority_rule})")
            
            # Update DNS if default route changed
            old_default = get_default_interface()
            update_dns_for_default_route(self.config)
            new_default = get_default_interface()
            
            if old_default != new_default:
                logger.info(f"Default route changed: {old_default} -> {new_default}")
            
        except Exception as e:
            logger.error(f"Error setting {iface_name} active={active}: {e}")
    
    def _monitoring_loop(self) -> None:
        """Main monitoring loop."""
        logger.info("Health monitoring started")
        
        while self.running:
            # Check all interfaces
            for iface_name in self.interfaces.keys():
                if not self.running:
                    break
                
                success = self._check_interface(iface_name)
                self._update_interface_state(iface_name, success)
            
            # Sleep for interval
            time.sleep(self.interval)
        
        logger.info("Health monitoring stopped")
    
    def _handle_client(self, client_socket: socket.socket) -> None:
        """
        Handle control socket client connection.
        
        Args:
            client_socket: Connected client socket
        """
        try:
            # Receive command
            data = client_socket.recv(4096).decode('utf-8')
            command = json.loads(data)
            
            action = command.get("action")
            
            if action == "status":
                response = self._get_status()
            elif action == "reload":
                config_path = command.get("config_path", "/data/network-policy.toml")
                response = self._reload_config(config_path)
            else:
                response = {"error": f"Unknown action: {action}"}
            
            # Send response
            client_socket.sendall(json.dumps(response).encode('utf-8'))
            
        except Exception as e:
            logger.error(f"Error handling client: {e}")
            error_response = {"error": str(e)}
            try:
                client_socket.sendall(json.dumps(error_response).encode('utf-8'))
            except:
                pass
        finally:
            client_socket.close()
    
    def _socket_server_loop(self) -> None:
        """Control socket server loop."""
        try:
            # Remove existing socket
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
            
            # Create UNIX socket
            self.socket_server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.socket_server.bind(self.socket_path)
            self.socket_server.listen(5)
            os.chmod(self.socket_path, 0o666)
            
            logger.info(f"Control socket listening at {self.socket_path}")
            
            while self.running:
                try:
                    self.socket_server.settimeout(1.0)
                    client_socket, _ = self.socket_server.accept()
                    
                    # Handle client in separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client_socket,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        logger.error(f"Socket server error: {e}")
                    break
        finally:
            if self.socket_server:
                self.socket_server.close()
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
    
    def _get_status(self) -> Dict[str, Any]:
        """Get current status."""
        return {
            "running": self.running,
            "interval": self.interval,
            "timeout": self.timeout,
            "probe_targets": self.probe_targets,
            "interfaces": {
                name: asdict(state)
                for name, state in self.interfaces.items()
            }
        }
    
    def _reload_config(self, config_path: str) -> Dict[str, Any]:
        """Reload configuration."""
        try:
            logger.info(f"Reloading configuration from {config_path}")
            
            # Load new config
            new_config = load_config(config_path)
            self.config = new_config
            
            # Reinitialize interfaces
            self.interfaces.clear()
            self._initialize_interfaces()
            
            return {"success": True, "message": "Configuration reloaded"}
            
        except Exception as e:
            logger.error(f"Error reloading config: {e}")
            return {"success": False, "error": str(e)}
    
    def start(self) -> None:
        """Start health monitoring daemon."""
        self.running = True
        
        # Start monitoring thread
        monitor_thread = threading.Thread(target=self._monitoring_loop)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Start socket server (blocking)
        self._socket_server_loop()
    
    def stop(self) -> None:
        """Stop health monitoring daemon."""
        logger.info("Stopping health monitor")
        self.running = False
