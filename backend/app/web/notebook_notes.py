import json
import time
from typing import Annotated, Literal
from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from .auth import Principal, require_user
from .store import uid, encode
User = Annotated[Principal, Depends(require_user)]
SCHEMA = '''
CREATE TABLE IF NOT EXISTS notebook_notes(
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 scope TEXT NOT NULL, scope_id TEXT NOT NULL, title TEXT NOT NULL, content TEXT NOT NULL,
 evidence TEXT NOT NULL, source_message_id TEXT, created REAL NOT NULL, updated REAL NOT NULL,
 UNIQUE(workspace_id,scope,scope_id,source_message_id));
'''
class NoteInput(BaseModel):
    scope: Literal['paper','book']
    scope_id: str = Field(max_length=100)
    title: str = Field(default='研究笔记',min_length=1,max_length=120)
    content: str = Field(default='',max_length=30000)
    source_message_id: str | None = Field(default=None,max_length=100)
class EditInput(BaseModel):
    title: str = Field(min_length=1,max_length=120)
    content: str = Field(max_length=30000)
def register(api,store):
    def owned(user,scope,sid):
        if scope=='paper':
            row=store.paper(user.workspace_id,sid)
        else:
            row=store.one('SELECT id FROM knowledge_bases WHERE id=? AND workspace_id=?',(sid,user.workspace_id))
        if not row: raise LookupError('scope_not_found')
    @api.get('/workspace-notes')
    def notes(user:User,scope:Literal['paper','book'],scope_id:str=Query(max_length=100)):
        owned(user,scope,scope_id)
        rows=store.all('SELECT * FROM notebook_notes WHERE workspace_id=? AND scope=? AND scope_id=? ORDER BY updated DESC',(user.workspace_id,scope,scope_id))
        return {'items':[r|{'evidence':json.loads(r['evidence'])} for r in rows]}
    @api.post('/workspace-notes',status_code=201)
    def create(data:NoteInput,user:User):
        owned(user,data.scope,data.scope_id)
        content,evidence=data.content,'{}'
        if data.source_message_id:
            if data.scope=='book':
                message=store.one("SELECT content,evidence FROM knowledge_messages WHERE id=? AND knowledge_id=? AND role='assistant'",(data.source_message_id,data.scope_id))
            else:
                message=store.one("SELECT m.content,m.evidence FROM messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=? AND c.paper_id=? AND c.workspace_id=? AND m.role='assistant'",(data.source_message_id,data.scope_id,user.workspace_id))
            if not message: raise LookupError('message_not_found')
            content,evidence=message['content'],message['evidence']
        if not content.strip(): raise HTTPException(422,'笔记内容不能为空')
        with store.connect(write=True) as db:
            nid,now=uid(),time.time()
            db.execute('INSERT OR IGNORE INTO notebook_notes VALUES(?,?,?,?,?,?,?,?,?,?)',(nid,user.workspace_id,data.scope,data.scope_id,data.title,content,evidence,data.source_message_id,now,now))
            if data.source_message_id:
                nid=db.execute('SELECT id FROM notebook_notes WHERE workspace_id=? AND scope=? AND scope_id=? AND source_message_id=?',(user.workspace_id,data.scope,data.scope_id,data.source_message_id)).fetchone()['id']
        return {'id':nid}
    @api.put('/workspace-notes/{nid}')
    def edit(nid:str,data:EditInput,user:User):
        with store.connect(write=True) as db:
            if not db.execute('UPDATE notebook_notes SET title=?,content=?,updated=? WHERE id=? AND workspace_id=?',(data.title,data.content,time.time(),nid,user.workspace_id)).rowcount: raise LookupError('note_not_found')
        return {'ok':True}
    @api.delete('/workspace-notes/{nid}')
    def delete(nid:str,user:User):
        with store.connect(write=True) as db:
            if not db.execute('DELETE FROM notebook_notes WHERE id=? AND workspace_id=?',(nid,user.workspace_id)).rowcount: raise LookupError('note_not_found')
        return {'ok':True}
