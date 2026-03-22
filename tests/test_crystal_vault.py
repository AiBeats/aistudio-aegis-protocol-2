"""Tests for ABV Crystal Vault encrypted file storage."""

from __future__ import annotations

import os
import tempfile
import unittest

os.environ.setdefault("ABV_LOG_LEVEL", "WARNING")

from src.public.crystal.vault_core import CrystalVault, VaultState
from src.public.crystal.vault_client_api import VaultClientAPI


class TestCrystalVaultLifecycle(unittest.TestCase):
    """Test vault create / mount / unmount / destroy lifecycle."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.tmpdir, "test.cryst")
        self.passphrase = "test-passphrase-256"

    def tearDown(self) -> None:
        # Clean up
        if os.path.exists(self.vault_path):
            os.unlink(self.vault_path)
        os.rmdir(self.tmpdir)

    def test_create_vault(self) -> None:
        vault = CrystalVault(self.vault_path)
        vault.create(self.passphrase)
        self.assertEqual(vault.state, VaultState.MOUNTED)
        self.assertTrue(os.path.exists(self.vault_path))

    def test_create_duplicate_raises(self) -> None:
        vault = CrystalVault(self.vault_path)
        vault.create(self.passphrase)
        vault2 = CrystalVault(self.vault_path)
        with self.assertRaises(FileExistsError):
            vault2.create(self.passphrase)

    def test_mount_unmount(self) -> None:
        vault = CrystalVault(self.vault_path)
        vault.create(self.passphrase)
        vault.unmount()
        self.assertEqual(vault.state, VaultState.SEALED)

        vault2 = CrystalVault(self.vault_path)
        result = vault2.mount(self.passphrase)
        self.assertTrue(result)
        self.assertEqual(vault2.state, VaultState.MOUNTED)

    def test_wrong_passphrase(self) -> None:
        vault = CrystalVault(self.vault_path)
        vault.create(self.passphrase)
        vault.unmount()

        vault2 = CrystalVault(self.vault_path)
        result = vault2.mount("wrong-passphrase")
        self.assertFalse(result)
        self.assertEqual(vault2.state, VaultState.SEALED)


class TestCrystalVaultFileOps(unittest.TestCase):
    """Test file add / read / list operations."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.tmpdir, "test.cryst")
        self.passphrase = "test-passphrase-256"
        self.vault = CrystalVault(self.vault_path)
        self.vault.create(self.passphrase)

    def tearDown(self) -> None:
        if self.vault.state == VaultState.MOUNTED:
            self.vault.unmount()
        if os.path.exists(self.vault_path):
            os.unlink(self.vault_path)
        os.rmdir(self.tmpdir)

    def test_add_and_read_file(self) -> None:
        data = b"Hello, Crystal Vault!"
        entry = self.vault.add_file("hello.txt", data, tags=["test"])

        self.assertEqual(entry.name, "hello.txt")
        self.assertEqual(entry.size, len(data))

        read_back = self.vault.read_file("hello.txt")
        self.assertEqual(read_back, data)

    def test_add_duplicate_raises(self) -> None:
        self.vault.add_file("dup.txt", b"first")
        with self.assertRaises(FileExistsError):
            self.vault.add_file("dup.txt", b"second")

    def test_read_nonexistent_raises(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.vault.read_file("nonexistent.txt")

    def test_list_entries(self) -> None:
        self.vault.add_file("a.txt", b"aaa")
        self.vault.add_file("b.txt", b"bbb")
        entries = self.vault.list_entries()
        names = {e.name for e in entries}
        self.assertEqual(names, {"a.txt", "b.txt"})

    def test_file_persists_across_mount(self) -> None:
        data = b"persistent data"
        self.vault.add_file("persist.txt", data)
        self.vault.unmount()

        vault2 = CrystalVault(self.vault_path)
        vault2.mount(self.passphrase)
        read_back = vault2.read_file("persist.txt")
        self.assertEqual(read_back, data)
        vault2.unmount()


class TestCrystalVaultDestroy(unittest.TestCase):
    """Test vault destruction."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.tmpdir, "test.cryst")

    def tearDown(self) -> None:
        if os.path.exists(self.vault_path):
            os.unlink(self.vault_path)
        if os.path.exists(self.tmpdir):
            os.rmdir(self.tmpdir)

    def test_destroy_removes_file(self) -> None:
        vault = CrystalVault(self.vault_path)
        vault.create("passphrase")
        vault.destroy()
        self.assertFalse(os.path.exists(self.vault_path))
        self.assertEqual(vault.state, VaultState.DESTROYED)


class TestVaultClientAPI(unittest.TestCase):
    """Test the VaultClientAPI wrapper."""

    def setUp(self) -> None:
        self.tmpdir = tempfile.mkdtemp()
        self.vault_path = os.path.join(self.tmpdir, "api_test.cryst")
        self.passphrase = "api-test-pass"

    def tearDown(self) -> None:
        if os.path.exists(self.vault_path):
            os.unlink(self.vault_path)
        os.rmdir(self.tmpdir)

    def test_client_create_and_status(self) -> None:
        api = VaultClientAPI(self.vault_path)
        status = api.create(self.passphrase)
        self.assertEqual(status.state, "mounted")
        self.assertEqual(status.entry_count, 0)

    def test_client_add_and_read(self) -> None:
        api = VaultClientAPI(self.vault_path)
        api.create(self.passphrase)
        api.add("test.bin", b"\x00\x01\x02\x03")
        data = api.read("test.bin")
        self.assertEqual(data, b"\x00\x01\x02\x03")

    def test_client_open_close(self) -> None:
        api = VaultClientAPI(self.vault_path)
        api.create(self.passphrase)
        api.close()
        self.assertFalse(api.is_mounted)

        result = api.open(self.passphrase)
        self.assertTrue(result)
        self.assertTrue(api.is_mounted)


if __name__ == "__main__":
    unittest.main()
