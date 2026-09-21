"""
Download Manager - Versiyon Senkronizasyon Scripti (update_version.py)
"""
import sys
import re
import json
import os

def update_version(version_str: str):
    version_str = version_str.strip()
    if not version_str:
        print("[HATA] Gecersiz versiyon dizesi.")
        sys.exit(1)

    # 1. Parcalari hesapla (ornek: 1.1.0 -> 1, 1, 0, 0)
    parts = []
    for p in version_str.split("."):
        clean_p = "".join(filter(str.isdigit, p))
        parts.append(int(clean_p) if clean_p else 0)
    while len(parts) < 4:
        parts.append(0)
    v_tuple = tuple(parts[:4])
    v_four_str = f"{v_tuple[0]}.{v_tuple[1]}.{v_tuple[2]}.{v_tuple[3]}"

    root = os.path.dirname(os.path.abspath(__file__))

    # 2. app/__init__.py guncelle
    init_path = os.path.join(root, "app", "__init__.py")
    if os.path.exists(init_path):
        with open(init_path, "r", encoding="utf-8") as f:
            content = f.read()
        if re.search(r'__version__\s*=\s*["\'][^"\']+["\']', content):
            new_content = re.sub(r'__version__\s*=\s*["\'][^"\']+["\']', f'__version__ = "{version_str}"', content)
        else:
            new_content = content.rstrip() + f'\n__version__ = "{version_str}"\n'
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"[OK] app/__init__.py -> __version__ = \"{version_str}\"")

    # 3. extension/manifest.json guncelle
    manifest_path = os.path.join(root, "extension", "manifest.json")
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Chrome manifest version max 4 dot-separated integers
            data["version"] = f"{v_tuple[0]}.{v_tuple[1]}.{v_tuple[2]}"
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"[OK] extension/manifest.json -> version = \"{data['version']}\"")
        except Exception as e:
            print(f"[UYARI] manifest.json guncellenirken hata: {e}")

    # 4. PyInstaller Windows EXE VersionInfo dosyasi (file_version_info.txt)
    version_info_content = f"""# UTF-8
#
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={v_tuple},
    prodvers={v_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          '040904B0',
          [StringStruct('CompanyName', 'Download Manager'),
           StringStruct('FileDescription', 'Download Manager'),
           StringStruct('FileVersion', '{v_four_str}'),
           StringStruct('InternalName', 'DownloadManager'),
           StringStruct('LegalCopyright', 'Copyright (c) 2026'),
           StringStruct('OriginalFilename', 'DownloadManager.exe'),
           StringStruct('ProductName', 'Download Manager'),
           StringStruct('ProductVersion', '{version_str}')])
      ]), 
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    ver_info_path = os.path.join(root, "file_version_info.txt")
    with open(ver_info_path, "w", encoding="utf-8") as f:
        f.write(version_info_content)
    print(f"[OK] file_version_info.txt olusturuldu (Versiyon: {version_str})")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        update_version(sys.argv[1])
    else:
        print("Kullanim: python update_version.py <versiyon>")
        sys.exit(1)
