"""ABV Crystal Vault — Client API.

High-level API for vault operations, suitable for integration with
CLI tools, REST endpoints, or the LOCAL-MIND desktop UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from .vault_core import CrystalVault, CrystEntry, VaultState
from src.public.common.logging_utils import get_logger

logger = get_logger("crystal.client_api")


@dataclass
class VaultStatus:
    """Summary status of a Crystal Vault."""
    path: str
    state: str
    entry_count: int
    total_size: int


class VaultClientAPI:
    """Client-facing API wrapping :class:`CrystalVault` operations.

    Provides simplified create / open / close / add / read / list / destroy
    methods with consistent error handling and logging.
    """

    def __init__(self, vault_path: str) -> None:
        self._vault = CrystalVault(vault_path)
        self._vault_path = vault_path

    def create(self, passphrase: str) -> VaultStatus:
        """Create a new vault.

        Args:
            passphrase: Master passphrase for encryption.

        Returns:
            :class:`VaultStatus` of the newly created vault.
        """
        self._vault.create(passphrase)
        logger.info("Vault created via client API: %s", self._vault_path)
        return self.status()

    def open(self, passphrase: str) -> bool:
        """Open (mount) an existing vault.

        Returns:
            ``True`` if mount succeeded.
        """
        return self._vault.mount(passphrase)

    def close(self) -> None:
        """Close (unmount) the vault."""
        self._vault.unmount()

    def add(self, name: str, data: bytes, tags: Optional[List[str]] = None) -> CrystEntry:
        """Add a file to the vault.

        Args:
            name: Logical file name.
            data: File content bytes.
            tags: Optional metadata tags.

        Returns:
            The created :class:`CrystEntry`.
        """
        return self._vault.add_file(name, data, tags)

    def add_from_path(self, file_path: str, tags: Optional[List[str]] = None) -> CrystEntry:
        """Add a file from the filesystem into the vault.

        Args:
            file_path: Path to the source file.
            tags: Optional metadata tags.

        Returns:
            The created :class:`CrystEntry`.
        """
        p = Path(file_path)
        data = p.read_bytes()
        return self.add(p.name, data, tags)

    def read(self, name: str) -> bytes:
        """Read a file from the vault.

        Args:
            name: Logical file name.

        Returns:
            Decrypted file content.
        """
        return self._vault.read_file(name)

    def extract(self, name: str, dest_dir: str) -> str:
        """Extract a file from the vault to the filesystem.

        Args:
            name: Logical file name in the vault.
            dest_dir: Destination directory.

        Returns:
            Path to the extracted file.
        """
        data = self._vault.read_file(name)
        dest = Path(dest_dir) / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        logger.info("Extracted: %s -> %s", name, dest)
        return str(dest)

    def list_files(self) -> List[CrystEntry]:
        """List all files in the vault."""
        return self._vault.list_entries()

    def destroy(self) -> None:
        """Securely destroy the vault."""
        self._vault.destroy()
        logger.warning("Vault destroyed via client API: %s", self._vault_path)

    def status(self) -> VaultStatus:
        """Return the current vault status."""
        meta = self._vault.metadata
        return VaultStatus(
            path=self._vault_path,
            state=self._vault.state.value,
            entry_count=meta.entry_count,
            total_size=meta.total_size,
        )

    @property
    def is_mounted(self) -> bool:
        """Return whether the vault is currently mounted."""
        return self._vault.state == VaultState.MOUNTED
