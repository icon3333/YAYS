#!/usr/bin/env python3
"""
Centralized file locking utility
Provides cross-platform file locking using filelock library
"""
from contextlib import contextmanager

# Use filelock library for cross-platform file locking
try:
    from filelock import FileLock, Timeout
except ImportError:
    # Fallback: basic implementation without locking
    print("Warning: filelock not installed. File locking disabled.")
    class FileLock:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    class Timeout(Exception):
        pass


@contextmanager
def locked_file(file_path: str, timeout: int = 10):
    """
    Context manager for safe file locking

    Usage:
        with locked_file('config.txt'):
            with open('config.txt', 'r') as f:
                data = f.read()

    Args:
        file_path: Path to the file to lock
        timeout: Timeout in seconds for acquiring lock

    Raises:
        TimeoutError: If lock cannot be acquired within timeout

    Example:
        with locked_file('config.txt', timeout=5):
            # File is locked for exclusive access
            with open('config.txt', 'w') as f:
                f.write('data')
            # Lock automatically released when exiting context
    """
    lock_path = f"{file_path}.lock"
    lock = FileLock(lock_path, timeout=timeout)

    try:
        with lock:
            yield
    except Timeout:
        raise TimeoutError(f"Could not acquire lock on {file_path} after {timeout}s")
