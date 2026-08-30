from app.db.models.models import Model
from app.db.models.providers import Provider
from app.db.models.paper_tasks import (
    InteractionReceipt,
    MetadataMigrationRun,
    PaperIndexJob,
    PaperKeywordRecord,
    PaperTask,
    RelatedWorkSelectionRecord,
    RelatedWorkSnapshotRecord,
)
from app.db.models.evidence_hub import (
    FastWriteHandoff,
    PaperAnnotation,
    PaperCandidate,
    ResearchTopic,
    ResearchTopicPaper,
    TopicEvidenceItem,
    TopicSynthesisRecord,
)
from app.db.engine import get_engine, Base
from sqlalchemy import inspect, text


_PAPER_TASK_METADATA_COLUMNS = {
    "raw_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
    "normalized_metadata_json": "TEXT NOT NULL DEFAULT '{}'",
    "verified_identity_json": "TEXT NOT NULL DEFAULT '{}'",
    "metadata_schema_version": "VARCHAR NOT NULL DEFAULT ''",
    "metadata_parser_version": "VARCHAR NOT NULL DEFAULT ''",
    "metadata_strategy_version": "VARCHAR NOT NULL DEFAULT ''",
    "metadata_execution_status": "VARCHAR NOT NULL DEFAULT 'not_run'",
    "metadata_fallback_reasons_json": "TEXT NOT NULL DEFAULT '[]'",
}

_RELATED_WORK_COLUMNS = {
    "rejected_neighbors_json": "TEXT NOT NULL DEFAULT '[]'",
}


def _upgrade_paper_task_columns(engine) -> None:
    inspector = inspect(engine)
    if "paper_tasks" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("paper_tasks")}
    with engine.begin() as connection:
        for name, definition in _PAPER_TASK_METADATA_COLUMNS.items():
            if name not in existing:
                connection.execute(text(f'ALTER TABLE paper_tasks ADD COLUMN "{name}" {definition}'))
    inspector = inspect(engine)
    if "related_work_snapshots" in inspector.get_table_names():
        related_existing = {column["name"] for column in inspector.get_columns("related_work_snapshots")}
        with engine.begin() as connection:
            for name, definition in _RELATED_WORK_COLUMNS.items():
                if name not in related_existing:
                    connection.execute(text(f'ALTER TABLE related_work_snapshots ADD COLUMN "{name}" {definition}'))

def init_db():
    engine = get_engine()

    Base.metadata.create_all(bind=engine)
    _upgrade_paper_task_columns(engine)
