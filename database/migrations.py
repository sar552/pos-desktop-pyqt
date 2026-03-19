from database.models import db, ALL_MODELS, SchemaVersion
from core.logger import get_logger

logger = get_logger(__name__)

CURRENT_VERSION = 2

def initialize_db():
    """Baza jadvallarini yaratish va migratsiyalarni tekshirish"""
    try:
        db.connect(reuse_if_open=True)
        
        # Jadvallarni yaratish (agar mavjud bo'lmasa)
        db.create_tables(ALL_MODELS)
        
        # Versiyani tekshirish
        version_record, created = SchemaVersion.get_or_create(
            version=CURRENT_VERSION,
            defaults={'description': 'Initial enhanced schema with SalesInvoice models'}
        )
        
        if not created and version_record.version < CURRENT_VERSION:
            # Bu yerda kelajakda ALTER TABLE mantiqlari bo'ladi
            logger.info("Bazani yangilash: %d -> %d", version_record.version, CURRENT_VERSION)
            version_record.version = CURRENT_VERSION
            version_record.save()
            
        logger.info("Ma'lumotlar bazasi tayyor.")
    except Exception as e:
        logger.error("Bazani inicializatsiya qilishda xatolik: %s", e)
    finally:
        if not db.is_closed():
            db.close()
