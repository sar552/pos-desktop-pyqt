"""Dastur versiyasi va GitHub repo manzili (avto-yangilanish uchun).

YANGI VERSIYA CHIQARISH:
1. Quyidagi __version__ ni oshiring (masalan "1.0.0" -> "1.1.0").
2. develop -> main ga merge qiling.
3. Aynan shu raqam bilan teg qo'ying:  git tag v1.1.0 && git push origin v1.1.0
   (GitHub Actions release yaratadi; do'konlardagi dastur shu releasega yangilanadi.)
"""

__version__ = "1.0.9"

# Avto-yangilanish releaselarni shu repodan tekshiradi.
GITHUB_REPO = "sar552/pos-desktop-pyqt"
