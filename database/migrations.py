from core.logger import get_logger
from database.models import ALL_MODELS, Item, SchemaVersion, db

logger = get_logger(__name__)

# Each migration is: (version, description, list_of_sql_statements)
MIGRATIONS = [
    (1, "Initial schema - create all tables", []),
]


def get_current_version() -> int:
    try:
        row = SchemaVersion.select().order_by(SchemaVersion.version.desc()).first()
        return row.version if row else 0
    except Exception:
        return 0


def initialize_db():
    db.connect(reuse_if_open=True)
    try:
        had_data_before = _has_existing_data()
        # Create all tables (safe=True skips existing)
        db.create_tables(ALL_MODELS, safe=True)

        current = get_current_version()
        if current == 0 and had_data_before:
            # Existing DB without version tracking — mark all migrations as applied
            for version, desc, _ in MIGRATIONS:
                SchemaVersion.get_or_create(version=version, defaults={"description": desc})
            logger.info(
                "Mavjud DB uchun migratsiya versiyalari qayd etildi (v%d)",
                MIGRATIONS[-1][0],
            )
            return

        # Apply pending migrations
        for version, desc, statements in MIGRATIONS:
            if version <= current:
                continue
            try:
                with db.atomic():
                    for sql in statements:
                        try:
                            db.execute_sql(sql)
                        except Exception as e:
                            if "duplicate column" in str(e).lower():
                                logger.debug(
                                    "Migratsiya v%d: ustun allaqachon mavjud, o'tkazib yuborildi",
                                    version,
                                )
                            else:
                                raise
                    SchemaVersion.get_or_create(
                        version=version, defaults={"description": desc}
                    )
                logger.info("Migratsiya v%d qo'llanildi: %s", version, desc)
            except Exception as e:
                logger.error("Migratsiya v%d xatosi: %s", version, e)
                raise
    finally:
        if not db.is_closed():
            db.close()


def _has_existing_data() -> bool:
    """True if a non-versioned DB already holds real data (e.g. items)."""
    try:
        return Item.table_exists() and Item.select().limit(1).exists()
    except Exception:
        return False
