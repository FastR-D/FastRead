from app.db.engine import get_db
from app.db.models.video_tasks import VideoTask
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _serialize_tags(tags):
    if tags is None:
        return None
    if isinstance(tags, list):
        return ",".join(str(tag).strip() for tag in tags if str(tag).strip())
    return str(tags)


def _to_dict(task: VideoTask) -> dict:
    return {
        "id": task.id,
        "video_id": task.video_id,
        "platform": task.platform,
        "task_id": task.task_id,
        "video_url": task.video_url,
        "title": task.title,
        "cover_url": task.cover_url,
        "collection_folder": task.collection_folder,
        "collection_tags": task.collection_tags,
        "collection_note": task.collection_note,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


def upsert_video_task(
    video_id: str,
    platform: str,
    task_id: str,
    video_url: str | None = None,
    title: str | None = None,
    cover_url: str | None = None,
    collection_folder: str | None = None,
    collection_tags=None,
    collection_note: str | None = None,
):
    db = next(get_db())
    try:
        task = db.query(VideoTask).filter_by(task_id=task_id).first()
        if not task:
            task = VideoTask(video_id=video_id or "", platform=platform, task_id=task_id)
            db.add(task)
        task.video_id = video_id or task.video_id or ""
        task.platform = platform or task.platform
        if video_url is not None:
            task.video_url = video_url
        if title is not None:
            task.title = title
        if cover_url is not None:
            task.cover_url = cover_url
        if collection_folder is not None:
            task.collection_folder = collection_folder
        if collection_tags is not None:
            task.collection_tags = _serialize_tags(collection_tags)
        if collection_note is not None:
            task.collection_note = collection_note
        db.commit()
        db.refresh(task)
        logger.info(f"Video task upserted successfully. video_id: {video_id}, platform: {platform}, task_id: {task_id}")
        return _to_dict(task)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to upsert video task: {e}")
        raise
    finally:
        db.close()


# 插入任务
def insert_video_task(video_id: str, platform: str, task_id: str):
    return upsert_video_task(video_id=video_id, platform=platform, task_id=task_id)


# 查询任务（最新一条）
def get_task_by_video(video_id: str, platform: str):
    db = next(get_db())
    try:
        task = (
            db.query(VideoTask)
            .filter_by(video_id=video_id, platform=platform)
            .order_by(VideoTask.created_at.desc())
            .first()
        )
        if task:
            logger.info(f"Task found for video_id: {video_id} and platform: {platform}")
            return task.task_id
        else:
            logger.info(f"No task found for video_id: {video_id} and platform: {platform}")
            return None
    except Exception as e:
        logger.error(f"Failed to get task by video: {e}")
    finally:
        db.close()


def get_task_by_id(task_id: str):
    db = next(get_db())
    try:
        task = db.query(VideoTask).filter_by(task_id=task_id).first()
        return _to_dict(task) if task else None
    except Exception as e:
        logger.error(f"Failed to get task by id: {e}")
        return None
    finally:
        db.close()


def list_task_ids_by_video(video_id: str, platform: str):
    db = next(get_db())
    try:
        tasks = (
            db.query(VideoTask.task_id)
            .filter_by(video_id=video_id, platform=platform)
            .all()
        )
        return [task_id for (task_id,) in tasks if task_id]
    except Exception as e:
        logger.error(f"Failed to list task ids by video: {e}")
        return []
    finally:
        db.close()


def list_video_tasks():
    db = next(get_db())
    try:
        tasks = db.query(VideoTask).order_by(VideoTask.created_at.desc()).all()
        return [_to_dict(task) for task in tasks]
    except Exception as e:
        logger.error(f"Failed to list video tasks: {e}")
        return []
    finally:
        db.close()


def delete_task_by_task_id(task_id: str):
    db = next(get_db())
    try:
        task = db.query(VideoTask).filter_by(task_id=task_id).first()
        if not task:
            return 0
        db.delete(task)
        db.commit()
        logger.info(f"Task deleted for task_id: {task_id}")
        return 1
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete task by task_id: {e}")
        return 0
    finally:
        db.close()


def update_task_collection(
    task_id: str,
    collection_folder: str | None = None,
    collection_tags=None,
    collection_note: str | None = None,
):
    db = next(get_db())
    try:
        task = db.query(VideoTask).filter_by(task_id=task_id).first()
        if not task:
            return None
        if collection_folder is not None:
            task.collection_folder = collection_folder
        if collection_tags is not None:
            task.collection_tags = _serialize_tags(collection_tags)
        if collection_note is not None:
            task.collection_note = collection_note
        db.commit()
        db.refresh(task)
        logger.info(f"Task collection updated. task_id: {task_id}")
        return _to_dict(task)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update task collection: {e}")
        raise
    finally:
        db.close()


# 删除任务
def delete_task_by_video(video_id: str, platform: str):
    db = next(get_db())
    try:
        tasks = (
            db.query(VideoTask)
            .filter_by(video_id=video_id, platform=platform)
            .all()
        )
        for task in tasks:
            db.delete(task)
        db.commit()
        logger.info(f"Task(s) deleted for video_id: {video_id} and platform: {platform}")
        return len(tasks)
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete task by video: {e}")
        return 0
    finally:
        db.close()
