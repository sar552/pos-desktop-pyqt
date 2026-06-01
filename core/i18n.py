"""Oddiy i18n (ko'p tillilik) tizimi.

Manba til — O'zbekcha (lotin). Ya'ni `tr("Kassa ochish")` dagi kalit aynan
o'zbekcha matn. Ruscha/inglizcha uchun quyidagi TRANSLATIONS lug'ati ishlatiladi;
tarjima topilmasa, o'zbekcha matnning o'zi qaytariladi (xavfsiz fallback).

Foydalanish:
    from core.i18n import tr
    label = QLabel(tr("Kassa ochish"))

Tilni o'zgartirish:
    from core.i18n import i18n
    i18n.set_language("ru")
"""

from PyQt6.QtCore import QObject, pyqtSignal

from core.config import load_config, save_config
from core.logger import get_logger

logger = get_logger(__name__)

# Qo'llab-quvvatlanadigan tillar: kod -> ko'rsatiladigan nom
SUPPORTED_LANGUAGES = {
    "uz": "O'zbekcha",
    "ru": "Русский",
    "en": "English",
}
DEFAULT_LANGUAGE = "uz"

# Tarjimalar: til -> { o'zbekcha_matn: tarjima }.
# uz uchun lug'at shart emas — kalitning o'zi qaytadi.
# Lug'atning o'zi core/translations.py da (toza saqlash uchun).
from core.translations import TRANSLATIONS  # noqa: E402


class _I18n(QObject):
    """Joriy tilni saqlovchi va tarjima beruvchi singleton."""

    language_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        lang = (load_config().get("language") or DEFAULT_LANGUAGE).strip()
        self._lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    @property
    def language(self) -> str:
        return self._lang

    def set_language(self, lang: str, persist: bool = True):
        if lang not in SUPPORTED_LANGUAGES:
            lang = DEFAULT_LANGUAGE
        if lang == self._lang:
            return
        self._lang = lang
        if persist:
            try:
                save_config({"language": lang})
            except Exception as e:
                logger.debug("Til saqlanmadi: %s", e)
        self.language_changed.emit(lang)

    def tr(self, text: str) -> str:
        if not text or self._lang == DEFAULT_LANGUAGE:
            return text
        return TRANSLATIONS.get(self._lang, {}).get(text, text)


# Global singleton
i18n = _I18n()


def tr(text: str) -> str:
    """Joriy tilga tarjima qiladi (o'zbekcha matnni kalit sifatida oladi)."""
    return i18n.tr(text)
