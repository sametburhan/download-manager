"""
Download Manager - File Utilities (file_utils.py)

This module performs critical I/O operations such as filename sanitization,
lossless chunk merging into target files, and temporary file cleanup.
"""

import os
import re
import hashlib
from typing import List, Callable, Optional


def sanitize_filename(name: str, default: str = "downloaded_file") -> str:
    """
    Sanitizes prohibited characters for Windows and other operating systems.
    Prohibited characters: < > : " / \\ | ? *
    """
    if not name:
        return default

    # Replace forbidden characters with underscore
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip('. ')

    if not name:
        return default
    return name[:255]  # Maximum filename length


def merge_chunks(
    chunk_paths: List[str],
    destination_path: str,
    buffer_size: int = 1024 * 1024,  # 1 MB buffer
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> bool:
    """
    Sequentially reads downloaded temporary chunk (.part) files and
    merges them into the destination file. Low memory (RAM) usage.

    :param chunk_paths: Ordered list of temporary chunk file paths
    :param destination_path: Target path where merged file will be written
    :param buffer_size: Read/write buffer size (default: 1MB)
    :param progress_callback: Optional callback reporting (bytes_written, total_bytes)
    :return: True if operation succeeds
    """
    # Calculate total expected size
    total_bytes = 0
    for path in chunk_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Chunk file not found: {path}")
        total_bytes += os.path.getsize(path)

    # Ensure destination directory exists
    dest_dir = os.path.dirname(destination_path)
    if dest_dir and not os.path.exists(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)

    bytes_written = 0

    # Open destination file in binary write mode
    with open(destination_path, "wb") as dest_file:
        for chunk_idx, chunk_file_path in enumerate(chunk_paths):
            with open(chunk_file_path, "rb") as part_file:
                while True:
                    chunk_data = part_file.read(buffer_size)
                    if not chunk_data:
                        break
                    dest_file.write(chunk_data)
                    bytes_written += len(chunk_data)
                    if progress_callback:
                        progress_callback(bytes_written, total_bytes)

    return True


def cleanup_temp_files(
    chunk_paths: List[str],
    meta_file_path: Optional[str] = None,
    temp_dir: Optional[str] = None
) -> None:
    """
    Cleans up temporary .part and .meta files after merging or upon cancellation,
    including the task temporary folder if present.
    """
    import shutil

    for path in chunk_paths:
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

    if meta_file_path:
        try:
            if os.path.exists(meta_file_path):
                os.remove(meta_file_path)
        except OSError:
            pass

    if temp_dir and os.path.exists(temp_dir):
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except OSError:
            pass


def calculate_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """Calculates file hash to verify integrity."""
    hasher = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            hasher.update(block)
    return hasher.hexdigest()

