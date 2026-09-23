"""Persistent FastCAS mappings. Call event application only after SDK verification."""
import json
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS fastcas_transactions(state TEXT PRIMARY KEY,payload TEXT NOT NULL,expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS fastcas_links(
 issuer TEXT NOT NULL,id TEXT NOT NULL,client_id TEXT NOT NULL,
 user_id TEXT NOT NULL REFERENCES users(id),subject TEXT NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('prepared','active','revoked')),
 version INTEGER NOT NULL CHECK(version>0),payload TEXT NOT NULL,
 PRIMARY KEY(issuer,id));
CREATE UNIQUE INDEX IF NOT EXISTS fastcas_local_live ON fastcas_links(issuer,client_id,user_id) WHERE state!='revoked';
CREATE UNIQUE INDEX IF NOT EXISTS fastcas_subject_live ON fastcas_links(issuer,client_id,subject) WHERE state!='revoked';
CREATE TABLE IF NOT EXISTS fastcas_events(issuer TEXT NOT NULL,id TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(issuer,id));
"""


class FastCASTransactions:
    def __init__(self, store):
        self.store = store

    def put(self, transaction):
        with self.store.connect(write=True) as db:
            db.execute('DELETE FROM fastcas_transactions WHERE expires<?', (time.time(),))
            db.execute('INSERT INTO fastcas_transactions VALUES(?,?,?)',
                       (transaction['state'], json.dumps(transaction), transaction['expires_at']))

    def take(self, state):
        with self.store.connect(write=True) as db:
            row = db.execute('SELECT payload FROM fastcas_transactions WHERE state=?', (state,)).fetchone()
            db.execute('DELETE FROM fastcas_transactions WHERE state=?', (state,))
            return json.loads(row['payload']) if row else None


class FastCASLinks:
    def __init__(self, store, issuer, client_id):
        self.store, self.issuer, self.client_id = store, issuer, client_id

    def _validate(self, link):
        if link['client_id'] != self.client_id or link['state'] not in {'prepared', 'active', 'revoked'}:
            raise ValueError('Invalid FastCAS link')
        if type(link['version']) is not int or link['version'] < 1:
            raise ValueError('Invalid FastCAS link version')
        if any(not isinstance(link.get(k), str) or not link[k] for k in ('id', 'subject', 'local_account_ref')):
            raise ValueError('Invalid FastCAS link identity')

    def _save(self, db, link):
        self._validate(link)
        current = db.execute('SELECT * FROM fastcas_links WHERE issuer=? AND id=?', (self.issuer, link['id'])).fetchone()
        if current:
            if (current['user_id'], current['subject'], current['client_id']) != (link['local_account_ref'], link['subject'], self.client_id):
                raise ValueError('FastCAS link identity changed')
            if current['version'] >= link['version'] or current['state'] == 'revoked':
                return
        db.execute('''INSERT INTO fastcas_links VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(issuer,id) DO UPDATE SET state=excluded.state,version=excluded.version,payload=excluded.payload''',
            (self.issuer, link['id'], self.client_id, link['local_account_ref'], link['subject'], link['state'], link['version'], json.dumps(link)))

    def save(self, link):
        with self.store.connect(write=True) as db:
            self._save(db, link)

    def apply_verified_event(self, event):
        link = event['link']
        self._validate(link)
        if event['type'] != 'account_link.revoked' or link['state'] != 'revoked':
            raise ValueError('Unsupported FastCAS event')
        with self.store.connect(write=True) as db:
            if db.execute('SELECT 1 FROM fastcas_events WHERE issuer=? AND id=?', (self.issuer, event['id'])).fetchone():
                return
            # Ignore mappings for accounts this instance has never provisioned.
            if db.execute('SELECT 1 FROM users WHERE id=?', (link['local_account_ref'],)).fetchone():
                self._save(db, link)
                db.execute('''DELETE FROM sessions WHERE auth_source='fastcas' AND cas_issuer=?
                    AND cas_link_id=? AND cas_link_version<=?''', (self.issuer, link['id'], link['version']))
            db.execute('INSERT INTO fastcas_events VALUES(?,?,?)', (self.issuer, event['id'], time.time()))

    def apply_verified_logout(self, notice):
        if (not isinstance(notice.get('id'), str) or not notice['id'] or
                not isinstance(notice.get('subject'), str) or not notice['subject'] or
                (notice.get('sid') is not None and not isinstance(notice['sid'], str))):
            raise ValueError('Invalid FastCAS logout')
        with self.store.connect(write=True) as db:
            if db.execute('SELECT 1 FROM fastcas_events WHERE issuer=? AND id=?', (self.issuer, notice['id'])).fetchone():
                return
            db.execute('''DELETE FROM sessions WHERE auth_source='fastcas' AND cas_issuer=?
                AND cas_link_id IN (SELECT id FROM fastcas_links WHERE issuer=? AND client_id=? AND subject=?)
                AND (? IS NULL OR cas_sid=?)''', (self.issuer, self.issuer, self.client_id,
                   notice['subject'], notice.get('sid'), notice.get('sid')))
            db.execute('INSERT INTO fastcas_events VALUES(?,?,?)', (self.issuer, notice['id'], time.time()))
