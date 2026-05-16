from sqlalchemy import Column, Integer, String, DateTime, Text, func

from app.db.engine import Base


class VideoTask(Base):
    __tablename__ = "video_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String, nullable=False)
    platform = Column(String, nullable=False)
    task_id = Column(String, unique=True, nullable=False)
    video_url = Column(Text, nullable=True)
    title = Column(Text, nullable=True)
    cover_url = Column(Text, nullable=True)
    collection_folder = Column(String, nullable=True)
    collection_tags = Column(Text, nullable=True)
    collection_note = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
