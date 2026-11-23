"""SQLite records for the local PointCommun prototype."""
from contextlib import contextmanager
from pathlib import Path
import os,sqlite3,hashlib,hmac,secrets
ROOT=Path(__file__).resolve().parents[1]
SCHEMA='''
CREATE TABLE IF NOT EXISTS journey_states(meeting_id TEXT NOT NULL,user_id TEXT NOT NULL,state TEXT NOT NULL,updated_at TEXT NOT NULL,PRIMARY KEY(meeting_id,user_id));
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profiles(user_id TEXT PRIMARY KEY,avatar TEXT);
CREATE TABLE IF NOT EXISTS venue_overrides(id TEXT PRIMARY KEY,owner_id TEXT,payload TEXT NOT NULL,is_default INTEGER NOT NULL DEFAULT 0,deleted INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,sender_id TEXT NOT NULL,kind TEXT NOT NULL,meeting_id TEXT NOT NULL,created_at TEXT NOT NULL,read_at TEXT);
CREATE INDEX IF NOT EXISTS notifications_recipient_created ON notifications(user_id,created_at DESC);
CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS meetings(id TEXT PRIMARY KEY,organiser_id TEXT NOT NULL,title TEXT NOT NULL,date TEXT NOT NULL,duration_minutes INTEGER NOT NULL,objective TEXT NOT NULL,venue_ids TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,result TEXT NOT NULL DEFAULT '{}',selected_proposal_id TEXT);
CREATE TABLE IF NOT EXISTS members(meeting_id TEXT NOT NULL,user_id TEXT NOT NULL,status TEXT NOT NULL,input TEXT,PRIMARY KEY(meeting_id,user_id));
CREATE TABLE IF NOT EXISTS approvals(meeting_id TEXT NOT NULL,proposal_id TEXT NOT NULL,user_id TEXT NOT NULL,accepted INTEGER NOT NULL,PRIMARY KEY(meeting_id,proposal_id,user_id));
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,meeting_id TEXT NOT NULL,user_id TEXT NOT NULL,text TEXT NOT NULL,timestamp TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS locations(meeting_id TEXT NOT NULL,user_id TEXT NOT NULL,lat REAL NOT NULL,lon REAL NOT NULL,accuracy REAL,timestamp TEXT NOT NULL,PRIMARY KEY(meeting_id,user_id));
'''
@contextmanager
def connection():
    path=Path(os.environ.get('DB_PATH',ROOT/'data'/'meetings.sqlite3'));path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=30);db.row_factory=sqlite3.Row
    try:
        db.executescript(SCHEMA)
        yield db
        db.commit()
    except BaseException:
        db.rollback();raise
    finally:db.close()
def password_hash(password):
    salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),310000).hex()
    return 'pbkdf2_sha256$310000$'+salt+'$'+digest
def check_password(password,stored):
    try:
        algo,n,salt,digest=stored.split('$');return algo=='pbkdf2_sha256' and hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),int(n)).hex(),digest)
    except (ValueError,TypeError):return False
def token_hash(token):return hashlib.sha256(token.encode()).hexdigest()
