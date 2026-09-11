"""Local application state. Credentials are encrypted, never returned by the API."""
import json
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet
from .providers import provider_settings


def uid():
    return uuid.uuid4().hex


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        key = root / 'local.key'
        if not key.exists():
            try:
                fd = os.open(key, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, 'wb') as f:
                    f.write(Fernet.generate_key())
            except FileExistsError:
                pass
        self.cipher = Fernet(key.read_bytes())
        self.db = root / 'app.sqlite3'
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, title TEXT NOT NULL, source_id TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                role TEXT NOT NULL, content TEXT NOT NULL, result TEXT, created_at TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=10)
        c.row_factory = sqlite3.Row
        c.execute('PRAGMA foreign_keys=ON')
        try:
            with c:
                yield c
        finally:
            c.close()

    def encrypt(self, value):
        return self.cipher.encrypt(value.encode()).decode() if value else ''

    def decrypt(self, value):
        return self.cipher.decrypt(value.encode()).decode() if value else ''

    def settings(self, private=False):
        with self.connect() as c:
            row = c.execute('SELECT payload FROM settings WHERE id=1').fetchone()
        data = json.loads(row['payload']) if row else {
            'mode': 'demo', 'provider': 'deepseek', 'api_key_encrypted': '',
        }
        data = provider_settings(data)
        data['has_api_key'] = bool(data.get('api_key_encrypted'))
        if private:
            data['api_key'] = self.decrypt(data.get('api_key_encrypted', ''))
        else:
            data.pop('api_key', None)
        data.pop('api_key_encrypted', None)
        return data

    def save_settings(self, data):
        old = self.settings(private=True)
        key = data.pop('api_key', None)
        old.update(data)
        current_key = old.pop('api_key', '')
        old['api_key_encrypted'] = self.encrypt(current_key if key is None else key)
        old.pop('has_api_key', None)
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO settings VALUES (1,?)', (json.dumps(old),))

    def sources(self):
        with self.connect() as c:
            return [json.loads(r['payload']) for r in c.execute('SELECT payload FROM sources ORDER BY rowid')]

    def source(self, source_id):
        with self.connect() as c:
            row = c.execute('SELECT payload FROM sources WHERE id=?', (source_id,)).fetchone()
        if not row:
            raise ValueError('数据源不存在，请重新选择。')
        return json.loads(row['payload'])

    def save_source(self, source):
        with self.connect() as c:
            c.execute('INSERT OR REPLACE INTO sources VALUES (?,?)', (source['id'], json.dumps(source, ensure_ascii=False)))

    def conversations(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM conversations ORDER BY updated_at DESC')]

    def conversation(self, cid):
        with self.connect() as c:
            row = c.execute('SELECT * FROM conversations WHERE id=?', (cid,)).fetchone()
        if not row:
            raise ValueError('对话不存在。')
        return dict(row)

    def create_conversation(self, source_id):
        self.source(source_id)
        cid, stamp = uid(), now()
        with self.connect() as c:
            c.execute('INSERT INTO conversations VALUES (?,?,?,?,?)', (cid, '新分析', source_id, stamp, stamp))
        return self.conversation(cid)

    def messages(self, cid):
        self.conversation(cid)
        with self.connect() as c:
            rows = c.execute('SELECT * FROM messages WHERE conversation_id=? ORDER BY rowid', (cid,)).fetchall()
        return [{**dict(r), 'result': json.loads(r['result']) if r['result'] else None} for r in rows]

    def add_message(self, cid, role, content, result=None):
        mid, stamp = uid(), now()
        with self.connect() as c:
            c.execute('INSERT INTO messages VALUES (?,?,?,?,?,?)', (
                mid, cid, role, content, json.dumps(result, ensure_ascii=False) if result else None, stamp))
            if role == 'user':
                c.execute("UPDATE conversations SET title=CASE WHEN title='新分析' THEN ? ELSE title END, updated_at=? WHERE id=?", (content[:32], stamp, cid))
            else:
                c.execute('UPDATE conversations SET updated_at=? WHERE id=?', (stamp, cid))
        return mid
