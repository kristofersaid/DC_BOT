# ==========================================
# FILE: dc_cleanup_images.py
# ==========================================

#!/usr/bin/env python3
"""
Konwertuje wszystkie obrazy w OUTPUT na PNG i usuwa oryginały/duplikaty.
Dla Discord Media Downloader.
Uruchamiany TYLKO na żądanie (przycisk w GUI).
"""

from pathlib import Path
from PIL import Image

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "OUTPUT"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".jfif"}


def convert_to_png(directory, recursive=True):
    if not directory.exists():
        return 0

    if recursive:
        files = [f for f in directory.rglob("*") if f.is_file() and f.suffix.lower() in IMAGE_EXTS]
    else:
        files = [f for f in directory.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTS]

    png_files = sorted([f for f in files if f.suffix.lower() == ".png"])
    other_files = sorted([f for f in files if f.suffix.lower() != ".png"])

    seen = {}
    converted = 0

    for f in png_files:
        key = (str(f.parent), f.stem.lower())
        if key in seen:
            print(f"  Duplikat PNG: {f} -> usuwam")
            f.unlink(missing_ok=True)
        else:
            seen[key] = f

    for f in other_files:
        key = (str(f.parent), f.stem.lower())
        png_path = f.parent / (f.stem + ".png")

        if key in seen:
            print(f"  PNG istnieje, usuwam: {f}")
            f.unlink(missing_ok=True)
        else:
            try:
                img = Image.open(f)
                img.load()
                img.save(png_path, "PNG")
                print(f"  Konwersja: {f.name} -> {png_path.name}")
                f.unlink(missing_ok=True)
                seen[key] = png_path
                converted += 1
            except Exception as e:
                print(f"  Błąd konwersji {f.name}: {e}")

    return converted


def cleanup():
    print("=" * 40)
    print("  DC Bot - Cleanup & PNG Converter")
    print("=" * 40)

    print("\n[OUTPUT]")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    count = convert_to_png(OUTPUT_DIR, recursive=True)

    print(f"\nSkonwertowano {count} plików.")
    print("Cleanup done.\n")
    return count


if __name__ == "__main__":
    cleanup()