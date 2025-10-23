#!/usr/bin/env python3
"""
Encryption utilities for secure settings storage
Uses Fernet symmetric encryption for secrets in database
"""

import os
import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet


class SettingsEncryption:
    """
    Handles encryption/decryption of sensitive settings in database.

    Uses Fernet (symmetric encryption) with a key derived from:
    1. YAYS_MASTER_KEY environment variable (if set)
    2. Machine-specific identifier (fallback)

    This ensures secrets are encrypted at rest in the database.
    """

    def __init__(self, master_key: Optional[str] = None):
        """
        Initialize encryption with master key.

        Args:
            master_key: Optional master key. If None, uses env var or generates one.
        """
        self._key = self._get_or_create_key(master_key)
        self._cipher = Fernet(self._key)

    def _get_or_create_key(self, master_key: Optional[str] = None) -> bytes:
        """
        Get or create encryption key.

        Priority:
        1. Provided master_key parameter
        2. YAYS_MASTER_KEY environment variable
        3. Machine-specific derived key (fallback)

        Returns:
            32-byte base64-encoded Fernet key
        """
        if master_key:
            # Use provided key
            return self._derive_key(master_key)

        # Check environment variable
        env_key = os.environ.get('YAYS_MASTER_KEY')
        if env_key:
            return self._derive_key(env_key)

        # Fallback: Use machine-specific key
        # This is less secure but allows the app to work without manual key setup
        # For production, users should set YAYS_MASTER_KEY environment variable
        machine_id = self._get_machine_id()
        return self._derive_key(machine_id)

    def _get_machine_id(self) -> str:
        """
        Get a machine-specific identifier.

        Uses docker container hostname, system hostname, or fallback.
        """
        # Try Docker container ID
        if os.path.exists('/proc/self/cgroup'):
            try:
                with open('/proc/self/cgroup', 'r') as f:
                    for line in f:
                        if 'docker' in line:
                            # Extract container ID from cgroup path
                            parts = line.strip().split('/')
                            if len(parts) > 2:
                                return parts[-1][:32]
            except:
                pass

        # Fallback to hostname
        import socket
        hostname = socket.gethostname()

        # If still generic, use a stable fallback
        if not hostname or hostname == 'localhost':
            # Use a combination of factors to create a stable ID
            import platform
            factors = [
                platform.node(),
                platform.system(),
                platform.machine(),
                'yays-default-key-v1'
            ]
            return '-'.join(factors)

        return hostname

    def _derive_key(self, password: str) -> bytes:
        """
        Derive a Fernet key from password using PBKDF2.

        Args:
            password: Password/seed to derive key from

        Returns:
            32-byte base64-encoded Fernet key
        """
        # Use PBKDF2 to derive a 32-byte key
        # Salt is fixed for deterministic key generation from same password
        # For production, consider storing salt separately
        salt = b'yays-settings-salt-v1'

        kdf_key = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt,
            iterations=100000,
            dklen=32
        )

        # Fernet requires base64-encoded key
        return base64.urlsafe_b64encode(kdf_key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a string.

        Args:
            plaintext: String to encrypt

        Returns:
            Encrypted string (base64-encoded)
        """
        if not plaintext:
            return ''

        encrypted_bytes = self._cipher.encrypt(plaintext.encode('utf-8'))
        return encrypted_bytes.decode('utf-8')

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a string.

        Args:
            ciphertext: Encrypted string (base64-encoded)

        Returns:
            Decrypted plaintext string
        """
        if not ciphertext:
            return ''

        try:
            decrypted_bytes = self._cipher.decrypt(ciphertext.encode('utf-8'))
            return decrypted_bytes.decode('utf-8')
        except Exception as e:
            # If decryption fails, return empty string
            # This can happen if key changed or data is corrupted
            print(f"⚠️ Decryption failed: {e}")
            return ''

    def is_encrypted(self, value: str) -> bool:
        """
        Check if a value appears to be encrypted.

        Fernet tokens start with 'gAAAAA' after base64 encoding.

        Args:
            value: String to check

        Returns:
            True if value appears to be encrypted
        """
        if not value:
            return False

        # Fernet tokens have specific format
        try:
            # Try to decrypt - if it works, it's encrypted
            self.decrypt(value)
            return True
        except:
            return False


# Global instance (lazy-loaded)
_encryption_instance = None


def get_encryption() -> SettingsEncryption:
    """
    Get global encryption instance (singleton pattern).

    Returns:
        SettingsEncryption instance
    """
    global _encryption_instance
    if _encryption_instance is None:
        _encryption_instance = SettingsEncryption()
    return _encryption_instance


if __name__ == '__main__':
    # Test encryption
    print("Testing SettingsEncryption...")

    enc = SettingsEncryption()

    # Test encryption/decryption
    test_data = [
        'sk-test-api-key-123456789',
        'mypassword123',
        'user@example.com',
        '',
    ]

    print("\n1. Encryption/Decryption tests:")
    for data in test_data:
        encrypted = enc.encrypt(data)
        decrypted = enc.decrypt(encrypted)

        status = "✅" if decrypted == data else "❌"
        print(f"   {status} '{data}' -> '{encrypted[:50]}...' -> '{decrypted}'")

    # Test key derivation consistency
    print("\n2. Key derivation consistency:")
    enc1 = SettingsEncryption(master_key='test-password')
    enc2 = SettingsEncryption(master_key='test-password')

    secret = 'my-secret-value'
    encrypted1 = enc1.encrypt(secret)
    decrypted2 = enc2.decrypt(encrypted1)

    status = "✅" if decrypted2 == secret else "❌"
    print(f"   {status} Same password produces compatible encryption: {decrypted2 == secret}")

    print("\n✅ Tests complete")
