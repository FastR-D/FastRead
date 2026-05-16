from app.db.models.models import Model
from app.db.models.providers import Provider
from app.db.models.video_tasks import VideoTask
from app.db.engine import get_engine, Base
from sqlalchemy import inspect, text


VIDEO_TASK_COLUMNS = {
    "video_url": "TEXT",
    "title": "TEXT",
    "cover_url": "TEXT",
    "collection_folder": "VARCHAR",
    "collection_tags": "TEXT",
    "collection_note": "TEXT",
    "updated_at": "DATETIME",
}


def _ensure_video_task_columns(engine):
    """SQLite create_all will not alter existing tables; add demo-era columns in place."""
    inspector = inspect(engine)
    if "video_tasks" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("video_tasks")}
    missing = [(name, column_type) for name, column_type in VIDEO_TASK_COLUMNS.items() if name not in existing]
    if not missing:
        return

    with engine.begin() as conn:
        for name, column_type in missing:
            conn.execute(text(f"ALTER TABLE video_tasks ADD COLUMN {name} {column_type}"))

def init_db():
    engine = get_engine()

    Base.metadata.create_all(bind=engine)
    _ensure_video_task_columns(engine)
