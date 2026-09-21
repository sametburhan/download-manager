"""
Download Manager - Dosya Yardımcı Araçları (file_utils.py)

Bu modül, dosya adı temizleme (sanitization), indirilen parçaların (chunks)
hedef dosyada kayıpsız birleştirilmesi (merging) ve geçici dosyaların
temizlenmesi gibi kritik I/O işlemlerini gerçekleştirir.
"""

import os
import re
import hashlib
from typing import List, Callable, Optional


def sanitize_filename(name: str, default: str = "downloaded_file") -> str:
    """
    Windows ve diğer işletim sistemlerinde yasaklı karakterleri temizler.
    Yasaklı karakterler: < > : " / \\ | ? *
    """
    if not name:
        return default

    # Yasaklı karakterleri alt çizgi ile değiştir
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    name = name.strip('. ')

    if not name:
        return default
    return name[:255]  # Maksimum dosya adı uzunluğu


def merge_chunks(
    chunk_paths: List[str],
    destination_path: str,
    buffer_size: int = 1024 * 1024,  # 1 MB bellek tamponu
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> bool:
    """
    İndirilmiş geçici parça (.part) dosyalarını sıralı olarak okur ve
    hedef dosyaya birleştirir. Düşük bellek (RAM) tüketir.

    :param chunk_paths: Sıralı geçici dosya yolları listesi
    :param destination_path: Birleştirilmiş dosyanın kaydedileceği yol
    :param buffer_size: Okuma/yazma tampon büyüklüğü (varsayılan: 1MB)
    :param progress_callback: (yazılan_byte, toplam_byte) bildiren geri çağırım
    :return: İşlem başarılı ise True
    """
    # Toplam beklenen boyutu hesapla
    total_bytes = 0
    for path in chunk_paths:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Parça dosyası bulunamadı: {path}")
        total_bytes += os.path.getsize(path)

    # Hedef dizinin varlığını garanti et
    dest_dir = os.path.dirname(destination_path)
    if dest_dir and not os.path.exists(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)

    bytes_written = 0

    # Hedef dosyayı ikili yazma modunda aç
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


def cleanup_temp_files(chunk_paths: List[str], meta_file_path: Optional[str] = None) -> None:
    """
    Birleştirme sonrasında veya iptal durumunda geçici .part ve .meta dosyalarını siler.
    """
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


def calculate_file_hash(file_path: str, algorithm: str = "sha256") -> str:
    """Dosyanın bütünlüğünü teyit etmek için hash değerini hesaplar."""
    hasher = hashlib.new(algorithm)
    with open(file_path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            hasher.update(block)
    return hasher.hexdigest()
