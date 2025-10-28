#!/usr/bin/env python3
"""
Restart Manager - Handles application restart for both Docker and Python modes
"""

import os
import subprocess
from pathlib import Path


def detect_docker_compose_command():
    """
    Detect which Docker Compose command is available
    Returns: list with command parts, or None if not available
    """
    # Try modern 'docker compose' first
    try:
        result = subprocess.run(
            ['docker', 'compose', 'version'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            return ['docker', 'compose']
    except:
        pass

    # Try legacy 'docker-compose'
    try:
        result = subprocess.run(
            ['docker-compose', 'version'],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            return ['docker-compose']
    except:
        pass

    return None


def detect_runtime_environment():
    """
    Detect if running in Docker or native Python
    Returns: tuple ('docker'|'python', command_description)

    NOTE: When we're INSIDE a Docker container, we restart the Python process.
    We only try to use docker-compose when running outside containers (native mode).
    """
    # Check if running in Docker container (most reliable check)
    if os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv'):
        return ('python', 'restart_python_process')

    # Check if running inside a Docker container by checking cgroup
    try:
        with open('/proc/1/cgroup', 'r') as f:
            if 'docker' in f.read():
                return ('python', 'restart_python_process')
    except:
        pass

    # Running in native Python mode
    # In Python mode, we restart the process using os.execv
    return ('python', 'restart_python_processes')


def restart_application():
    """
    Restart the application based on detected runtime environment
    Returns: dict with keys: success (bool), message (str), restart_type (str)
    """
    env_type, command = detect_runtime_environment()

    try:
        if env_type == 'docker':
            # Detect which Docker Compose command is available
            docker_compose_cmd = detect_docker_compose_command()

            if docker_compose_cmd is None:
                return {
                    "success": False,
                    "message": "Neither 'docker compose' nor 'docker-compose' found. Please install Docker Compose or restart manually",
                    "restart_type": "docker"
                }

            # Try to restart Docker containers
            result = subprocess.run(
                docker_compose_cmd + ['restart'],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=Path(__file__).parent.parent.parent  # Navigate to project root
            )

            if result.returncode == 0:
                return {
                    "success": True,
                    "message": "Docker containers restarted successfully",
                    "restart_type": "docker"
                }
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                return {
                    "success": False,
                    "message": f"Failed to restart containers: {error_msg}",
                    "restart_type": "docker"
                }

        else:  # python mode (or inside Docker container)
            # When running inside a Docker container, we exit and let Docker restart us
            # When running in native Python, we use os.execv to restart the process
            import sys

            # Check if we're inside Docker
            in_docker = os.path.exists('/.dockerenv') or os.path.exists('/run/.containerenv')

            if in_docker:
                # Exit with code 0 so Docker's restart policy kicks in
                # We'll schedule this to happen after the response is sent
                return {
                    "success": True,
                    "message": "Restarting application... (this may take 10-20 seconds)",
                    "restart_type": "python",
                    "restart_method": "docker_exit"
                }
            else:
                # Native Python mode: restart using os.execv
                return {
                    "success": True,
                    "message": "Restarting application...",
                    "restart_type": "python",
                    "restart_method": "execv",
                    "restart_command": [sys.executable, sys.argv[0]] + sys.argv[1:]
                }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "Restart command timed out after 30 seconds",
            "restart_type": env_type
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Restart error: {str(e)}",
            "restart_type": env_type
        }
