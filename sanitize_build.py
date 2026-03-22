#!/usr/bin/env python3
"""ABV Sovereign Stack — Sanitize Build Tool.

Strips private code blocks (between ``# BEGIN_PRIVATE`` / ``# END_PRIVATE``
markers) from source files and copies them to a public distribution directory.

Supports: .py, .kt, .ino, .jsx files.
Outputs a sanitization manifest for audit purposes.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List

SRC_DIR = "src/"
DEST_DIR = "public_dist/"

# Pattern to match private code blocks across all supported languages
PRIVATE_PATTERNS = {
    ".py": re.compile(
        r"[ \t]*# BEGIN_PRIVATE.*?# END_PRIVATE[^\n]*\n?",
        re.DOTALL,
    ),
    ".kt": re.compile(
        r"[ \t]*// BEGIN_PRIVATE.*?// END_PRIVATE[^\n]*\n?",
        re.DOTALL,
    ),
    ".ino": re.compile(
        r"[ \t]*// BEGIN_PRIVATE.*?// END_PRIVATE[^\n]*\n?",
        re.DOTALL,
    ),
    ".jsx": re.compile(
        r"[ \t]*\{?/\* BEGIN_PRIVATE.*?END_PRIVATE \*/\}?[^\n]*\n?",
        re.DOTALL,
    ),
}

SUPPORTED_EXTENSIONS = set(PRIVATE_PATTERNS.keys())

REDACT_REPLACEMENTS = {
    ".py": "# [REDACTED FOR PUBLIC BUILD]\n",
    ".kt": "// [REDACTED FOR PUBLIC BUILD]\n",
    ".ino": "// [REDACTED FOR PUBLIC BUILD]\n",
    ".jsx": "{/* [REDACTED FOR PUBLIC BUILD] */}\n",
}


@dataclass
class SanitizedFile:
    """Record of a single sanitized file."""
    source_path: str
    dest_path: str
    extension: str
    blocks_redacted: int
    original_lines: int
    sanitized_lines: int


@dataclass
class SanitizeManifest:
    """Manifest of the entire sanitization run."""
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ"))
    source_dir: str = SRC_DIR
    dest_dir: str = DEST_DIR
    files_processed: int = 0
    files_with_redactions: int = 0
    total_blocks_redacted: int = 0
    entries: List[SanitizedFile] = field(default_factory=list)


def sanitize_content(content: str, ext: str) -> tuple[str, int]:
    """Sanitize file content by replacing private blocks.

    Args:
        content: Original file content.
        ext: File extension (e.g. ".py").

    Returns:
        Tuple of (sanitized content, number of blocks redacted).
    """
    pattern = PRIVATE_PATTERNS.get(ext)
    if pattern is None:
        return content, 0

    replacement = REDACT_REPLACEMENTS.get(ext, "# [REDACTED FOR PUBLIC BUILD]\n")
    sanitized, count = pattern.subn(replacement, content)
    return sanitized, count


def sanitize() -> SanitizeManifest:
    """Run the full sanitization pipeline.

    Walks the source directory, sanitizes all supported files,
    copies them to the public distribution directory, and
    generates a manifest.

    Returns:
        A :class:`SanitizeManifest` recording all operations.
    """
    manifest = SanitizeManifest()

    if not os.path.exists(DEST_DIR):
        os.makedirs(DEST_DIR)

    for root, dirs, files in os.walk(SRC_DIR):
        # Skip private directory entirely
        if "private" in root.split(os.sep):
            continue

        for filename in files:
            ext = Path(filename).suffix
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            src_path = os.path.join(root, filename)

            with open(src_path, "r", encoding="utf-8") as f:
                content = f.read()

            original_lines = content.count("\n")
            sanitized, blocks = sanitize_content(content, ext)
            sanitized_lines = sanitized.count("\n")

            # Write to dest
            dest_path = root.replace(SRC_DIR, DEST_DIR, 1)
            if not os.path.exists(dest_path):
                os.makedirs(dest_path)

            dest_file = os.path.join(dest_path, filename)
            with open(dest_file, "w", encoding="utf-8") as f:
                f.write(sanitized)

            entry = SanitizedFile(
                source_path=src_path,
                dest_path=dest_file,
                extension=ext,
                blocks_redacted=blocks,
                original_lines=original_lines,
                sanitized_lines=sanitized_lines,
            )
            manifest.entries.append(entry)
            manifest.files_processed += 1

            if blocks > 0:
                manifest.files_with_redactions += 1
                manifest.total_blocks_redacted += blocks

    # Also process platform files (wearos/, esp32/, react/)
    platform_dirs = ["wearos/", "esp32/", "react/"]
    for platform_dir in platform_dirs:
        if not os.path.exists(platform_dir):
            continue
        for root, dirs, files in os.walk(platform_dir):
            for filename in files:
                ext = Path(filename).suffix
                if ext not in SUPPORTED_EXTENSIONS:
                    continue

                src_path = os.path.join(root, filename)
                with open(src_path, "r", encoding="utf-8") as f:
                    content = f.read()

                original_lines = content.count("\n")
                sanitized, blocks = sanitize_content(content, ext)
                sanitized_lines = sanitized.count("\n")

                dest_path = os.path.join(DEST_DIR, root)
                if not os.path.exists(dest_path):
                    os.makedirs(dest_path)

                dest_file = os.path.join(dest_path, filename)
                with open(dest_file, "w", encoding="utf-8") as f:
                    f.write(sanitized)

                entry = SanitizedFile(
                    source_path=src_path,
                    dest_path=dest_file,
                    extension=ext,
                    blocks_redacted=blocks,
                    original_lines=original_lines,
                    sanitized_lines=sanitized_lines,
                )
                manifest.entries.append(entry)
                manifest.files_processed += 1

                if blocks > 0:
                    manifest.files_with_redactions += 1
                    manifest.total_blocks_redacted += blocks

    # Write manifest
    manifest_path = os.path.join(DEST_DIR, "sanitize_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(asdict(manifest), f, indent=2)

    return manifest


def main() -> None:
    """Entry point for the sanitize build tool."""
    print("ABV Sovereign Stack — Sanitize Build")
    print(f"Source: {SRC_DIR}")
    print(f"Destination: {DEST_DIR}")
    print()

    manifest = sanitize()

    print(f"Files processed:      {manifest.files_processed}")
    print(f"Files with redactions: {manifest.files_with_redactions}")
    print(f"Total blocks redacted: {manifest.total_blocks_redacted}")
    print()

    if manifest.entries:
        print("Sanitized files:")
        for entry in manifest.entries:
            marker = f" [{entry.blocks_redacted} redacted]" if entry.blocks_redacted else ""
            print(f"  {entry.source_path} -> {entry.dest_path}{marker}")

    print(f"\nManifest written to: {DEST_DIR}sanitize_manifest.json")


if __name__ == "__main__":
    main()
