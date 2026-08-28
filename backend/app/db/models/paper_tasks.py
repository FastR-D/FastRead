from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.db.engine import Base


class PaperTask(Base):
    __tablename__ = "paper_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String, unique=True, nullable=False, index=True)
    title = Column(Text, nullable=False)
    authors_json = Column(Text, nullable=False, default="[]")
    year = Column(Integer, nullable=True)
    venue_id = Column(String, nullable=False, default="")
    venue_name = Column(Text, nullable=False, default="")
    venue_track = Column(String, nullable=False, default="")
    identity_status = Column(String, nullable=False, default="incomplete", index=True)
    doi = Column(String, nullable=False, default="")
    source_url = Column(Text, nullable=False, default="")
    resolved_source_url = Column(Text, nullable=False, default="")
    pdf_url = Column(Text, nullable=False, default="")
    upload_filename = Column(Text, nullable=False, default="")
    content_hash = Column(String, nullable=False, index=True)
    report_version = Column(String, nullable=False, default="")
    collection_folder = Column(String, nullable=False, default="默认收藏夹")
    collection_tags_json = Column(Text, nullable=False, default="[]")
    collection_note = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class RelatedWorkSnapshotRecord(Base):
    __tablename__ = "related_work_snapshots"

    id = Column(String, primary_key=True)
    task_id = Column(String, nullable=False, index=True)
    paper_content_hash = Column(String, nullable=False, index=True)
    report_version = Column(String, nullable=False)
    cache_key = Column(String, unique=True, nullable=False, index=True)
    search_backend = Column(String, nullable=False)
    anchors_json = Column(Text, nullable=False, default="[]")
    neighbors_json = Column(Text, nullable=False, default="[]")
    provider_status_json = Column(Text, nullable=False, default="{}")
    generated_at = Column(DateTime, server_default=func.now(), nullable=False)


class PaperIndexJob(Base):
    __tablename__ = "paper_index_jobs"

    id = Column(String, primary_key=True)
    status = Column(String, nullable=False, index=True)
    provider_id = Column(String, nullable=False, default="")
    model_name = Column(String, nullable=False, default="")
    prompt_version = Column(String, nullable=False)
    strategy_version = Column(String, nullable=False)
    corpus_count = Column(Integer, nullable=False, default=0)
    ai_keyword_count = Column(Integer, nullable=False, default=0)
    fallback_count = Column(Integer, nullable=False, default=0)
    fallback_reasons_json = Column(Text, nullable=False, default="{}")
    local_index_count = Column(Integer, nullable=False, default=0)
    elasticsearch_index_count = Column(Integer, nullable=False, default=0)
    search_backend = Column(String, nullable=False, default="local_inverted_index")
    error = Column(Text, nullable=False, default="")
    started_at = Column(DateTime, server_default=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)


class PaperKeywordRecord(Base):
    __tablename__ = "paper_keyword_records"

    id = Column(String, primary_key=True)
    job_id = Column(String, nullable=False, index=True)
    paper_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, default="", index=True)
    title = Column(Text, nullable=False, default="")
    abstract_hash = Column(String, nullable=False, default="")
    keywords_json = Column(Text, nullable=False, default="[]")
    execution_status = Column(String, nullable=False, index=True)
    fallback_reason = Column(Text, nullable=False, default="")
    provider_id = Column(String, nullable=False, default="")
    model_name = Column(String, nullable=False, default="")
    prompt_version = Column(String, nullable=False)
    strategy_version = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
