from app.db.models.models import Model
from app.db.models.providers import Provider
from app.db.models.paper_tasks import (
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

def init_db():
    engine = get_engine()

    Base.metadata.create_all(bind=engine)
