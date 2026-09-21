"""Generate missing knowledge-library questions without replacing user text."""
import json
from fastapi import HTTPException
from .store import uid


def schedule(store, workspace, user, bid):
    from .knowledge import choose_model
    with store.connect(write=True) as db:
        book = db.execute('SELECT description FROM knowledge_bases WHERE id=? AND workspace_id=?', (bid, workspace)).fetchone()
        if not book or book['description'].strip():
            return None
        pending = db.execute("SELECT * FROM jobs WHERE workspace_id=? AND resource_id=? AND kind='book_questions' AND state IN ('queued','running')", (workspace, bid)).fetchone()
        if pending:
            return dict(pending)
        config = choose_model(store, workspace)
        return store.enqueue(workspace, user, 'book_questions', config, 'book-questions:'+uid(), resource_id=bid, billable=True, db=db)


def schedule_optional(store, workspace, user, bid):
    # Creating a library or adding a paper must still succeed if quota/config is unavailable.
    try:
        return schedule(store, workspace, user, bid)
    except (HTTPException, ValueError):
        return None


def decorate(store, workspace, books):
    for book in books:
        latest = store.one("SELECT state FROM jobs WHERE workspace_id=? AND resource_id=? AND kind='book_questions' ORDER BY created DESC LIMIT 1", (workspace, book['id']))
        book['questions_status'] = 'ready' if book['description'].strip() else latest['state'] if latest else 'not_started'
    return books


def execute(store, job, owner, client_factory):
    from .knowledge import owned_book, excerpts, json_completion
    from .worker import complete
    workspace, bid = job['workspace_id'], job['resource_id']
    book = owned_book(store, workspace, bid)
    if book['description'].strip():
        with store.connect(write=True) as db:
            store.assert_lease(db, job, owner)
            complete(db, job, {'knowledge_id': bid, 'preserved': True})
        return
    # Read membership at execution time so papers added while queued are included.
    papers = store.all('SELECT p.id,p.active_version,p.title FROM papers p JOIN knowledge_papers k ON k.paper_id=p.id WHERE k.knowledge_id=? AND p.workspace_id=? AND p.archived=0 ORDER BY p.id LIMIT 30', (bid, workspace))
    sources = excerpts(store, workspace, papers) if papers else []
    client = client_factory(store, job, json.loads(job['payload']), owner)
    try:
        result = json_completion(client,
            '为知识库写一到两个具体的研究问题，作为卡片上的“关注的问题”。用自然简洁的中文，合计20至100字。'
            '有论文时根据提供的论文题目和原文片段，提炼共同关注的问题；没有论文时仅根据知识库名称提出待研究的问题，不要声称已有论文或结论。'
            '只写问题，不写宣传口号、功能介绍或“按研究主题连接论文”这类占位话。返回 {"description": "问题文本"}。',
            {'name': book['name'], 'paper_titles': [p['title'] for p in papers], 'sources': sources})
    finally:
        client.client.close()
    text = result.get('description')
    if not isinstance(text, str) or not 10 <= len(text.strip()) <= 200 or not any(c in text for c in '?？'):
        raise ValueError('模型未返回简短的研究问题')
    with store.connect(write=True) as db:
        store.assert_lease(db, job, owner)
        changed = db.execute("UPDATE knowledge_bases SET description=? WHERE id=? AND workspace_id=? AND trim(description)=''", (text.strip(), bid, workspace)).rowcount
        complete(db, job, {'knowledge_id': bid, 'generated': bool(changed)})
