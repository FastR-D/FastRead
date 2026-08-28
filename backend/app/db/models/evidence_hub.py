from sqlalchemy import Column, DateTime, Float, Integer, String, Text, UniqueConstraint, func

from app.db.engine import Base


class PaperAnnotation(Base):
    __tablename__ = "paper_annotations"

    id = Column(String, primary_key=True)
    task_id = Column(String, nullable=False, index=True)
    page = Column(Integer, nullable=False)
    start_offset = Column(Integer, nullable=False)
    end_offset = Column(Integer, nullable=False)
    exact_quote = Column(Text, nullable=False)
    note = Column(Text, nullable=False, default="")
    source_hash = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class PaperCandidate(Base):
    __tablename__ = "paper_candidates"

    id = Column(String, primary_key=True)
    title = Column(Text, nullable=False)
    authors_json = Column(Text, nullable=False, default="[]")
    year = Column(Integer, nullable=True)
    venue = Column(Text, nullable=False, default="")
    abstract = Column(Text, nullable=False, default="")
    doi = Column(String, nullable=False, default="")
    doi_norm = Column(String, nullable=False, default="", index=True)
    arxiv_id = Column(String, nullable=False, default="")
    arxiv_norm = Column(String, nullable=False, default="", index=True)
    detail_url = Column(Text, nullable=False, default="")
    canonical_url = Column(Text, nullable=False, default="")
    canonical_url_norm = Column(Text, nullable=False, default="", index=True)
    pdf_url = Column(Text, nullable=False, default="")
    pdf_sha256 = Column(String, nullable=False, default="", index=True)
    producer = Column(String, nullable=False, index=True)
    upstream_id = Column(Text, nullable=False, default="")
    source_commit = Column(String, nullable=False, default="")
    fetched_at = Column(String, nullable=False, default="")
    warnings_json = Column(Text, nullable=False, default="[]")
    match_score = Column(Float, nullable=True)
    raw_json = Column(Text, nullable=False, default="{}")
    import_status = Column(String, nullable=False, default="pending", index=True)
    task_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ResearchTopic(Base):
    __tablename__ = "research_topics"

    id = Column(String, primary_key=True)
    question = Column(Text, nullable=False)
    scope_statement = Column(Text, nullable=False, default="")
    user_hypotheses_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class ResearchTopicPaper(Base):
    __tablename__ = "research_topic_papers"

    topic_id = Column(String, primary_key=True)
    task_id = Column(String, primary_key=True)
    added_at = Column(DateTime, server_default=func.now(), nullable=False)


class TopicEvidenceItem(Base):
    __tablename__ = "topic_evidence_items"

    id = Column(String, primary_key=True)
    topic_id = Column(String, nullable=False, index=True)
    task_id = Column(String, nullable=False, index=True)
    page = Column(Integer, nullable=False)
    exact_quote = Column(Text, nullable=False)
    user_note = Column(Text, nullable=False, default="")
    role = Column(String, nullable=False, default="other", index=True)
    source_kind = Column(String, nullable=False, default="manual")
    source_ref = Column(String, nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class TopicSynthesisRecord(Base):
    __tablename__ = "topic_syntheses"

    id = Column(String, primary_key=True)
    topic_id = Column(String, nullable=False, index=True)
    artifact_path = Column(Text, nullable=False)
    kind = Column(String, nullable=False, default="manual")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class FastWriteHandoff(Base):
    __tablename__ = "fastwrite_handoffs"
    __table_args__ = (UniqueConstraint("bundle_id", "project_id", name="uq_fastwrite_bundle_project"),)

    id = Column(String, primary_key=True)
    bundle_id = Column(String, nullable=False, index=True)
    project_id = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="pending", index=True)
    target_path = Column(Text, nullable=False)
    files_json = Column(Text, nullable=False, default="[]")
    successful_files_json = Column(Text, nullable=False, default="[]")
    error = Column(Text, nullable=False, default="")
    manifest_hash = Column(String, nullable=False, default="")
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
