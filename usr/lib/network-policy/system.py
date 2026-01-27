"""
System settings and user management.

Handles system configuration including hostname, timezone, NTP, locale,
and user account management with SSH keys.
"""

import os
import pwd
import grp
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

from logger import get_logger

logger = get_logger(__name__)


def apply_system_config(config: Dict[str, Any]) -> None:
    """
    Apply all system configuration from config.
    
    Args:
        config: Complete configuration dictionary
    """
    if "system" in config:
        system_config = config["system"]
        
        if "hostname" in system_config:
            set_hostname(system_config["hostname"])
        
        if "timezone" in system_config:
            set_timezone(system_config["timezone"])
        
        if "ntp_servers" in system_config:
            set_ntp_servers(system_config["ntp_servers"])
        
        if "locale" in system_config:
            set_locale(system_config["locale"])
    
    if "users" in config:
        for username, user_config in config["users"].items():
            create_or_update_user(username, user_config)


def set_hostname(hostname: str) -> None:
    """
    Set system hostname.
    
    Args:
        hostname: New hostname
    """
    try:
        logger.info(f"Setting hostname to {hostname}")
        
        # Set runtime hostname
        subprocess.run(
            ["hostnamectl", "set-hostname", hostname],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info(f"Hostname set to {hostname}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to set hostname: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error setting hostname: {e}")
        raise


def set_timezone(timezone: str) -> None:
    """
    Set system timezone.
    
    Args:
        timezone: Timezone (e.g., "Europe/Copenhagen")
    """
    try:
        logger.info(f"Setting timezone to {timezone}")
        
        subprocess.run(
            ["timedatectl", "set-timezone", timezone],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info(f"Timezone set to {timezone}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to set timezone: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error setting timezone: {e}")
        raise


def set_ntp_servers(servers: List[str]) -> None:
    """
    Configure NTP servers.
    
    Args:
        servers: List of NTP server addresses
    """
    try:
        logger.info(f"Configuring NTP servers: {', '.join(servers)}")
        
        # Create timesyncd config drop-in
        config_dir = Path("/etc/systemd/timesyncd.conf.d")
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_file = config_dir / "network-policy.conf"
        with open(config_file, 'w') as f:
            f.write("[Time]\n")
            f.write(f"NTP={' '.join(servers)}\n")
        
        # Restart timesyncd
        subprocess.run(
            ["systemctl", "restart", "systemd-timesyncd"],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info("NTP servers configured")
    except Exception as e:
        logger.error(f"Error configuring NTP servers: {e}")
        raise


def set_locale(locale: str) -> None:
    """
    Set system locale.
    
    Args:
        locale: Locale string (e.g., "en_US.UTF-8")
    """
    try:
        logger.info(f"Setting locale to {locale}")
        
        subprocess.run(
            ["localectl", "set-locale", f"LANG={locale}"],
            check=True,
            capture_output=True,
            text=True
        )
        
        logger.info(f"Locale set to {locale}")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to set locale: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error setting locale: {e}")
        raise


def create_or_update_user(username: str, user_config: Dict[str, Any]) -> None:
    """
    Create or update user account.
    
    Args:
        username: Username
        user_config: User configuration dictionary
    """
    try:
        # Check if user exists
        try:
            pwd.getpwnam(username)
            user_exists = True
            logger.info(f"Updating user: {username}")
        except KeyError:
            user_exists = False
            logger.info(f"Creating user: {username}")
        
        # Create user if doesn't exist
        if not user_exists:
            shell = user_config.get("shell", "/bin/bash")
            cmd = ["useradd", "-m", "-s", shell, username]
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Set password if provided
        if "password_hash" in user_config:
            password_hash = user_config["password_hash"]
            subprocess.run(
                ["usermod", "-p", password_hash, username],
                check=True,
                capture_output=True,
                text=True
            )
        
        # Set groups if provided
        if "groups" in user_config:
            groups = user_config["groups"]
            
            # Ensure groups exist
            for group in groups:
                try:
                    grp.getgrnam(group)
                except KeyError:
                    logger.warning(f"Group {group} doesn't exist, creating it")
                    subprocess.run(
                        ["groupadd", group],
                        check=True,
                        capture_output=True,
                        text=True
                    )
            
            # Add user to groups
            subprocess.run(
                ["usermod", "-a", "-G", ",".join(groups), username],
                check=True,
                capture_output=True,
                text=True
            )
        
        # Set shell if provided and user exists
        if user_exists and "shell" in user_config:
            shell = user_config["shell"]
            subprocess.run(
                ["usermod", "-s", shell, username],
                check=True,
                capture_output=True,
                text=True
            )
        
        # Setup SSH keys if provided
        if "ssh_keys" in user_config:
            setup_ssh_keys(username, user_config["ssh_keys"])
        
        logger.info(f"User {username} configured successfully")
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to configure user {username}: {e.stderr}")
        raise
    except Exception as e:
        logger.error(f"Error configuring user {username}: {e}")
        raise


def setup_ssh_keys(username: str, ssh_keys: List[str]) -> None:
    """
    Setup SSH authorized keys for user.
    
    Args:
        username: Username
        ssh_keys: List of SSH public keys
    """
    try:
        # Get user info
        user_info = pwd.getpwnam(username)
        home_dir = Path(user_info.pw_dir)
        ssh_dir = home_dir / ".ssh"
        authorized_keys = ssh_dir / "authorized_keys"
        
        # Create .ssh directory if doesn't exist
        ssh_dir.mkdir(mode=0o700, exist_ok=True)
        os.chown(ssh_dir, user_info.pw_uid, user_info.pw_gid)
        
        # Write authorized_keys file
        with open(authorized_keys, 'w') as f:
            for key in ssh_keys:
                f.write(f"{key}\n")
        
        # Set proper permissions
        authorized_keys.chmod(0o600)
        os.chown(authorized_keys, user_info.pw_uid, user_info.pw_gid)
        
        logger.info(f"SSH keys configured for user {username}")
        
    except Exception as e:
        logger.error(f"Error setting up SSH keys for {username}: {e}")
        raise
