"""ABV Crystal Vault — Encrypted File Storage Core.

Implements an encrypted file vault using AES-256-GCM.  Files are stored
in the ``.cryst`` format with an encrypted header (FAT), enabling
mount/unmount semantics similar to an encrypted volume.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.public.common.logging_utils import get_logger
from src.public.common.config import get_config

logger = get_logger("crystal.vault")

# .cryst file magic bytes
CRYST_MAGIC = b"CRYST01\x00"
NONCE_SIZE = 12
TAG_SIZE = 16


class VaultState(Enum):
    """Vault operational state."""
    SEALED = "sealed"
    MOUNTED = "mounted"
    LOCKED = "locked"
    DESTROYED = "destroyed"


@dataclass
class CrystEntry:
    """A single entry in the Crystal FAT (File Allocation Table)."""
    name: str
    size: int
    offset: int
    sha256: str
    created_at: float = field(default_factory=time.time)
    tags: List[str] = field(default_factory=list)


@dataclass
class VaultMetadata:
    """Metadata header for a .cryst vault file."""
    version: int = 1
    created_at: float = field(default_factory=time.time)
    entry_count: int = 0
    total_size: int = 0


class CrystalVault:
    """Encrypted file vault with FAT management.

    The vault stores files in a single ``.cryst`` container with
    AES-256-GCM encryption.  The FAT (index) is encrypted separately
    from file payloads, enabling fast directory listing without
    decrypting every file.
    """

    def __init__(self, vault_path: str) -> None:
        self._vault_path = Path(vault_path)
        self._state: VaultState = VaultState.SEALED
        self._key: Optional[bytes] = None
        self._fat: Dict[str, CrystEntry] = {}
        self._metadata: VaultMetadata = VaultMetadata()

        # BEGIN_PRIVATE
        # Extension hook: Crystal Vault private operations
        self._private_on_mount: Optional[Callable[["CrystalVault"], None]] = None
        self._private_on_unmount: Optional[Callable[["CrystalVault"], None]] = None
        self._private_on_destroy: Optional[Callable[["CrystalVault"], None]] = None
        # END_PRIVATE

    @staticmethod
    def derive_key(passphrase: str, salt: Optional[bytes] = None) -> tuple[bytes, bytes]:
        """Derive a 256-bit key from a passphrase using PBKDF2.

        Returns:
            Tuple of (key, salt).
        """
        if salt is None:
            salt = secrets.token_bytes(16)
        key = hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, iterations=600_000)
        return key, salt

    def create(self, passphrase: str) -> None:
        """Create a new empty vault file.

        Args:
            passphrase: Master passphrase for vault encryption.
        """
        if self._vault_path.exists():
            raise FileExistsError(f"Vault already exists: {self._vault_path}")

        key, salt = self.derive_key(passphrase)
        self._key = key
        self._fat = {}
        self._metadata = VaultMetadata()

        # Write initial vault: magic + salt + encrypted empty FAT
        fat_data = json.dumps({"entries": {}, "metadata": self._metadata.__dict__}).encode()
        nonce = secrets.token_bytes(NONCE_SIZE)
        aesgcm = AESGCM(key)
        encrypted_fat = aesgcm.encrypt(nonce, fat_data, CRYST_MAGIC)

        with open(self._vault_path, "wb") as f:
            f.write(CRYST_MAGIC)                          # 8 bytes magic
            f.write(salt)                                  # 16 bytes salt
            f.write(struct.pack("<I", len(encrypted_fat))) # 4 bytes FAT length
            f.write(nonce)                                 # 12 bytes nonce
            f.write(encrypted_fat)                         # variable-length encrypted FAT

        self._state = VaultState.MOUNTED
        logger.info("Vault created: %s", self._vault_path)

    def mount(self, passphrase: str) -> bool:
        """Mount (unlock) an existing vault.

        Args:
            passphrase: Master passphrase.

        Returns:
            ``True`` if the vault was successfully mounted.
        """
        if self._state == VaultState.MOUNTED:
            logger.warning("Vault is already mounted")
            return True

        if not self._vault_path.exists():
            logger.error("Vault file not found: %s", self._vault_path)
            return False

        with open(self._vault_path, "rb") as f:
            magic = f.read(8)
            if magic != CRYST_MAGIC:
                logger.error("Invalid vault file (bad magic)")
                return False

            salt = f.read(16)
            fat_len = struct.unpack("<I", f.read(4))[0]
            nonce = f.read(NONCE_SIZE)
            encrypted_fat = f.read(fat_len)

        key, _ = self.derive_key(passphrase, salt)
        aesgcm = AESGCM(key)

        try:
            fat_data = aesgcm.decrypt(nonce, encrypted_fat, CRYST_MAGIC)
        except Exception:
            logger.error("Vault mount failed — wrong passphrase or corrupted data")
            return False

        fat_json = json.loads(fat_data)
        self._key = key
        self._fat = {
            name: CrystEntry(**entry)
            for name, entry in fat_json.get("entries", {}).items()
        }
        meta = fat_json.get("metadata", {})
        self._metadata = VaultMetadata(**meta)
        self._state = VaultState.MOUNTED

        logger.info("Vault mounted: %s (%d entries)", self._vault_path, len(self._fat))

        # BEGIN_PRIVATE
        if self._private_on_mount is not None:
            self._private_on_mount(self)
        # END_PRIVATE

        return True

    def unmount(self) -> None:
        """Unmount (lock) the vault, flushing the FAT to disk."""
        if self._state != VaultState.MOUNTED:
            logger.warning("Vault is not mounted")
            return

        self._flush_fat()
        self._key = None
        self._fat = {}
        self._state = VaultState.SEALED
        logger.info("Vault unmounted: %s", self._vault_path)

        # BEGIN_PRIVATE
        if self._private_on_unmount is not None:
            self._private_on_unmount(self)
        # END_PRIVATE

    def add_file(self, name: str, data: bytes, tags: Optional[List[str]] = None) -> CrystEntry:
        """Add an encrypted file to the vault.

        Args:
            name: Logical file name within the vault.
            data: Raw file content.
            tags: Optional metadata tags.

        Returns:
            The created :class:`CrystEntry`.
        """
        self._require_mounted()

        if name in self._fat:
            raise FileExistsError(f"Entry already exists: {name}")

        nonce = secrets.token_bytes(NONCE_SIZE)
        aesgcm = AESGCM(self._key)
        encrypted = aesgcm.encrypt(nonce, data, name.encode())

        # Compute current payload section start so we store relative offsets
        payload_start = self._payload_section_start()

        # Append encrypted payload to vault file
        with open(self._vault_path, "ab") as f:
            abs_offset = f.tell()
            f.write(nonce)
            f.write(struct.pack("<I", len(encrypted)))
            f.write(encrypted)

        # Store offset relative to payload section start
        relative_offset = abs_offset - payload_start

        entry = CrystEntry(
            name=name,
            size=len(data),
            offset=relative_offset,
            sha256=hashlib.sha256(data).hexdigest(),
            tags=tags or [],
        )
        self._fat[name] = entry
        self._metadata.entry_count = len(self._fat)
        self._metadata.total_size += len(data)

        self._flush_fat()
        logger.info("Added to vault: %s (%d bytes)", name, len(data))
        return entry

    def read_file(self, name: str) -> bytes:
        """Read and decrypt a file from the vault.

        Args:
            name: Logical file name.

        Returns:
            Decrypted file content.
        """
        self._require_mounted()

        if name not in self._fat:
            raise FileNotFoundError(f"Entry not found: {name}")

        entry = self._fat[name]

        # Convert relative offset to absolute by adding payload section start
        payload_start = self._payload_section_start()
        abs_offset = payload_start + entry.offset

        with open(self._vault_path, "rb") as f:
            f.seek(abs_offset)
            nonce = f.read(NONCE_SIZE)
            enc_len = struct.unpack("<I", f.read(4))[0]
            encrypted = f.read(enc_len)

        aesgcm = AESGCM(self._key)
        return aesgcm.decrypt(nonce, encrypted, name.encode())

    def list_entries(self) -> List[CrystEntry]:
        """List all entries in the vault FAT."""
        self._require_mounted()
        return list(self._fat.values())

    def destroy(self) -> None:
        """Securely destroy the vault by overwriting with random data."""
        if self._vault_path.exists():
            size = self._vault_path.stat().st_size
            with open(self._vault_path, "wb") as f:
                f.write(secrets.token_bytes(size))
            self._vault_path.unlink()

        self._key = None
        self._fat = {}
        self._state = VaultState.DESTROYED
        logger.warning("Vault DESTROYED: %s", self._vault_path)

        # BEGIN_PRIVATE
        if self._private_on_destroy is not None:
            self._private_on_destroy(self)
        # END_PRIVATE

    @property
    def state(self) -> VaultState:
        """Return the current vault state."""
        return self._state

    @property
    def metadata(self) -> VaultMetadata:
        """Return vault metadata."""
        return self._metadata

    def _require_mounted(self) -> None:
        """Raise if the vault is not mounted."""
        if self._state != VaultState.MOUNTED:
            raise RuntimeError(f"Vault is not mounted (state={self._state.value})")

    def _payload_section_start(self) -> int:
        """Calculate the byte offset where the payload section begins.

        The vault header layout is:
          8 bytes  — magic
          16 bytes — salt
          4 bytes  — FAT length (N)
          12 bytes — nonce
          N bytes  — encrypted FAT
        """
        with open(self._vault_path, "rb") as f:
            f.read(8)   # magic
            f.read(16)  # salt
            fat_len = struct.unpack("<I", f.read(4))[0]
            # skip nonce + encrypted FAT
            return 8 + 16 + 4 + NONCE_SIZE + fat_len

    def _flush_fat(self) -> None:
        """Re-encrypt and write the FAT to the vault header."""
        if self._key is None:
            return

        fat_payload = json.dumps({
            "entries": {name: entry.__dict__ for name, entry in self._fat.items()},
            "metadata": self._metadata.__dict__,
        }).encode()

        nonce = secrets.token_bytes(NONCE_SIZE)
        aesgcm = AESGCM(self._key)
        encrypted_fat = aesgcm.encrypt(nonce, fat_payload, CRYST_MAGIC)

        # Read existing vault to preserve file payloads
        with open(self._vault_path, "rb") as f:
            f.read(8)   # magic
            salt = f.read(16)
            old_fat_len = struct.unpack("<I", f.read(4))[0]
            f.read(NONCE_SIZE)  # old nonce
            f.read(old_fat_len) # old encrypted FAT
            payload_data = f.read()  # everything after the FAT

        with open(self._vault_path, "wb") as f:
            f.write(CRYST_MAGIC)
            f.write(salt)
            f.write(struct.pack("<I", len(encrypted_fat)))
            f.write(nonce)
            f.write(encrypted_fat)
            f.write(payload_data)
