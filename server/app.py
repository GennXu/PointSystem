import csv
import hashlib
import io
import json
import logging
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

import qrcode
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from server.database import MAX_POINTS, engine_for, migrate, snapshot

ph = PasswordHasher()


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def strong_password(value):
    if len(value) < 12 or len(value) > 128 or not any(c.isalpha() for c in value) or not any(c.isdigit() for c in value):
        raise HTTPException(422, '密碼須為 12–128 字元，含字母及數字')


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Login(Model):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)


class Member(Model):
    member_code: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=100)


class Status(Model):
    status: str = Field(pattern='^(active|disabled)$')


class Operator(Login):
    role: str = Field(pattern='^(Admin|Staff)$')


class Scan(Model):
    token: str = Field(pattern=r'^[A-Za-z0-9_-]{43}$')


class Transaction(Model):
    idempotency_key: str = Field(min_length=16, max_length=128)
    user_id: str
    amount: StrictInt = Field(ge=0, le=MAX_POINTS)
    reason: str = Field(min_length=1, max_length=500)
    station_id: str = Field(min_length=1, max_length=80)
    token: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{43}$')


class Settings(Model):
    grant_presets: list[StrictInt] = Field(min_length=1, max_length=12)
    staff_limit: StrictInt = Field(ge=1, le=MAX_POINTS)
    backup_hour: StrictInt = Field(ge=0, le=23)
    backup_keep: StrictInt = Field(ge=1, le=365)


DEFAULTS = {'grant_presets': [50, 100, 200], 'staff_limit': 200, 'backup_hour': 2, 'backup_keep': 14}


def create_app(data_dir, static_dir=None, secure_cookie=False, backup_dir=None):
    data = Path(data_dir)
    data.mkdir(parents=True, exist_ok=True)
    backups = Path(backup_dir) if backup_dir else data / 'backups'
    backups.mkdir(parents=True, exist_ok=True)
    db = data / 'points.db'
    if db.exists():
        snapshot(db, backups / f'pre-start-{time.time_ns()}.db')
        for old in sorted(backups.glob('pre-start-*.db'), reverse=True)[5:]:
            old.unlink()
    migrate(db)
    key_file = data / 'secret.key'
    if not key_file.exists():
        key_file.write_bytes(Fernet.generate_key())
    cipher = Fernet(key_file.read_bytes())
    engine = engine_for(db)
    log = logging.getLogger('qrpoint.' + digest(str(data)))
    log.setLevel(logging.INFO)
    if not log.handlers:
        handler = RotatingFileHandler(data / 'audit.log', maxBytes=2_000_000, backupCount=5, encoding='utf8')
        handler.setFormatter(logging.Formatter('%(asctime)sZ %(message)s'))
        handler.formatter.converter = time.gmtime
        log.addHandler(handler)

    @contextmanager
    def write():
        with engine.connect() as c:
            c.exec_driver_sql('BEGIN IMMEDIATE')
            try:
                yield c
                c.commit()
            except BaseException:
                c.rollback()
                raise

    def row(c, sql, params=None):
        result = c.execute(text(sql), params or {}).mappings().first()
        return dict(result) if result else None

    def settings(c):
        record = row(c, "SELECT value_json FROM settings WHERE key='system'")
        return json.loads(record['value_json']) if record else DEFAULTS.copy()

    def backup():
        destination = backups / f'backup-{time.time_ns()}.db'
        snapshot(db, destination)
        with engine.connect() as c:
            keep = settings(c)['backup_keep']
        for old in sorted(backups.glob('backup-*.db'), reverse=True)[keep:]:
            old.unlink()
        return destination.name

    stop = threading.Event()

    def scheduled():
        last_day = None
        while not stop.wait(30):
            local = datetime.now(timezone(timedelta(hours=8)))
            with engine.connect() as c:
                hour = settings(c)['backup_hour']
            if local.hour >= hour and str(local.date()) != last_day:
                try:
                    backup()
                    last_day = str(local.date())
                    log.info('automatic_backup completed')
                except Exception:
                    log.error('automatic_backup failed')

    @asynccontextmanager
    async def lifespan(_):
        thread = threading.Thread(target=scheduled, daemon=True)
        thread.start()
        yield
        stop.set()
        thread.join(timeout=2)
        engine.dispose()

    app = FastAPI(title='QR Point System', version='1.0.0', lifespan=lifespan)
    app.state.engine = engine
    app.state.backup = backup
    app.state.db = db
    app.state.write = write
    app.state.before_ledger = None

    @app.exception_handler(IntegrityError)
    async def integrity_error(_, __):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409, content={'detail': '資料衝突或違反完整性約束'})

    @app.middleware('http')
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'"
        response.headers['Cache-Control'] = 'no-store'
        return response

    def current(request: Request):
        token = request.cookies.get('session', '')
        with engine.connect() as c:
            session = row(c, '''SELECT o.id,o.username,o.role,s.csrf FROM sessions s JOIN operators o ON o.id=s.operator_id
                WHERE s.token_hash=:hash AND s.expires_at>:now AND o.status='active' ''', {'hash': digest(token), 'now': now()})
        if not session:
            raise HTTPException(401, '請先登入')
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            if not secrets.compare_digest(request.headers.get('x-csrf-token', ''), session['csrf']):
                raise HTTPException(403, 'CSRF 驗證失敗')
        return session

    def admin(operator=Depends(current)):
        if operator['role'] != 'Admin':
            raise HTTPException(403, '限管理員')
        return operator

    def get_user(c, uid):
        user = row(c, 'SELECT * FROM users WHERE id=:id', {'id': uid})
        if not user:
            raise HTTPException(404, '找不到會員')
        return user

    def credential(c, token):
        qr = row(c, 'SELECT * FROM qr_credentials WHERE token_hash=:hash', {'hash': digest(token or '')})
        if not qr:
            raise HTTPException(404, '無效憑證')
        if qr['status'] != 'active':
            raise HTTPException(410, '憑證已撤銷')
        if qr['expires_at'] and qr['expires_at'] <= now():
            raise HTTPException(410, '憑證已過期')
        user = get_user(c, qr['user_id'])
        if user['status'] != 'active':
            raise HTTPException(409, '會員已停用')
        return user

    def issue(c, uid):
        token = secrets.token_urlsafe(32)
        c.execute(text("UPDATE qr_credentials SET status='revoked',revoked_at=:now WHERE user_id=:id AND status='active'"), {'id': uid, 'now': now()})
        c.execute(text('INSERT INTO qr_credentials(id,user_id,token_hash,token_cipher,status,issued_at) VALUES(:id,:uid,:hash,:cipher,\'active\',:now)'),
                  {'id': str(uuid.uuid4()), 'uid': uid, 'hash': digest(token), 'cipher': cipher.encrypt(token.encode()).decode(), 'now': now()})
        return token

    @app.get('/api/health')
    def health():
        with engine.connect() as c:
            c.execute(text('SELECT 1'))
        return {'status': 'ok'}

    @app.post('/api/auth/login')
    def login(body: Login, request: Request, response: Response):
        # Persisted rate limit, shared by all sessions from the source address.
        source = request.client.host if request.client else 'unknown'
        with write() as c:
            attempt = row(c, 'SELECT * FROM login_attempts WHERE source=:s', {'s': source})
            start = time.time()
            count = 0
            if attempt and start - attempt['window_start'] < 300:
                start, count = attempt['window_start'], attempt['count']
            if count >= 10:
                raise HTTPException(429, '登入嘗試過多，請五分鐘後再試')
            c.execute(text('INSERT OR REPLACE INTO login_attempts VALUES(:s,:n,:t)'), {'s': source, 'n': count + 1, 't': start})
        with engine.connect() as c:
            operator = row(c, 'SELECT * FROM operators WHERE username=:u', {'u': body.username})
        try:
            ph.verify(operator['password_hash'] if operator else app.state.dummy_hash, body.password)
            valid = operator and operator['status'] == 'active'
        except VerificationError:
            valid = False
        if not valid:
            raise HTTPException(401, '帳號或密碼錯誤')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with write() as c:
            c.execute(text('DELETE FROM login_attempts WHERE source=:s'), {'s': source})
            c.execute(text('DELETE FROM sessions WHERE expires_at<=:now'), {'now': now()})
            c.execute(text('INSERT INTO sessions VALUES(:hash,:id,:csrf,:expires)'), {'hash': digest(token), 'id': operator['id'], 'csrf': csrf, 'expires': (datetime.now(timezone.utc) + timedelta(hours=8)).isoformat()})
            c.execute(text('UPDATE operators SET last_login_at=:now WHERE id=:id'), {'now': now(), 'id': operator['id']})
        response.set_cookie('session', token, httponly=True, samesite='strict', secure=secure_cookie, max_age=28800)
        log.info('login operator=%s', operator['id'])
        return {'id': operator['id'], 'username': operator['username'], 'role': operator['role'], 'csrf': csrf}

    app.state.dummy_hash = ph.hash(secrets.token_urlsafe(32))

    @app.get('/api/auth/me')
    def me(operator=Depends(current)):
        return operator

    @app.post('/api/auth/logout')
    def logout(request: Request, response: Response, operator=Depends(current)):
        with write() as c:
            c.execute(text('DELETE FROM sessions WHERE token_hash=:hash'), {'hash': digest(request.cookies.get('session', ''))})
        response.delete_cookie('session')
        return {'ok': True}

    @app.post('/api/users')
    def create_member(body: Member, operator=Depends(current)):
        uid = str(uuid.uuid4())
        with write() as c:
            c.execute(text("INSERT INTO users VALUES(:id,:code,:name,'active',0,:now,:now,0)"), {'id': uid, 'code': body.member_code, 'name': body.display_name, 'now': now()})
            token = issue(c, uid)
            user = get_user(c, uid)
        log.info('member_create operator=%s user=%s', operator['id'], uid)
        return {**user, 'token': token}

    @app.get('/api/users')
    def list_members(q: str = '', offset: int = 0, limit: int = 100, operator=Depends(current)):
        with engine.connect() as c:
            return [dict(r) for r in c.execute(text('SELECT * FROM users WHERE member_code LIKE :q OR display_name LIKE :q ORDER BY created_at DESC LIMIT :n OFFSET :offset'), {'q': '%' + q[:100] + '%', 'n': min(max(limit, 1), 200), 'offset': max(offset, 0)}).mappings()]

    @app.get('/api/users/{uid}')
    def member(uid: str, operator=Depends(current)):
        with engine.connect() as c:
            return get_user(c, uid)

    @app.patch('/api/users/{uid}')
    def member_status(uid: str, body: Status, operator=Depends(admin)):
        with write() as c:
            get_user(c, uid)
            c.execute(text('UPDATE users SET status=:s,updated_at=:now,version=version+1 WHERE id=:id'), {'s': body.status, 'now': now(), 'id': uid})
        log.info('member_status operator=%s user=%s status=%s', operator['id'], uid, body.status)
        return {'ok': True}

    @app.post('/api/users/{uid}/qr/reissue')
    def reissue(uid: str, operator=Depends(current)):
        with write() as c:
            if get_user(c, uid)['status'] != 'active':
                raise HTTPException(409, '會員已停用')
            token = issue(c, uid)
        log.info('qr_reissue operator=%s user=%s', operator['id'], uid)
        return {'token': token}

    @app.get('/api/users/{uid}/qr')
    def qr_image(uid: str, operator=Depends(current)):
        with engine.connect() as c:
            get_user(c, uid)
            qr = row(c, "SELECT token_cipher FROM qr_credentials WHERE user_id=:id AND status='active'", {'id': uid})
        if not qr:
            raise HTTPException(404, '尚無有效憑證')
        output = io.BytesIO()
        qrcode.make(cipher.decrypt(qr['token_cipher'].encode()).decode()).save(output, format='PNG')
        return Response(output.getvalue(), media_type='image/png', headers={'Content-Disposition': 'inline; filename="member-qr.png"'})

    @app.post('/api/scan/lookup')
    def lookup(body: Scan, operator=Depends(current)):
        with engine.connect() as c:
            return credential(c, body.token)

    def transact(kind, body, operator):
        if kind == 'ADJUST' and operator['role'] != 'Admin':
            raise HTTPException(403, '限管理員')
        if kind != 'ADJUST' and body.amount < 1:
            raise HTTPException(422, '點數必須為正整數')
        request_hash = digest(json.dumps({'kind': kind, 'operator': operator['id'], **body.model_dump()}, sort_keys=True))
        with write() as c:
            old = row(c, 'SELECT * FROM transactions WHERE idempotency_key=:key', {'key': body.idempotency_key})
            if old:
                if old['request_hash'] != request_hash:
                    raise HTTPException(409, '同一冪等鍵的請求內容不同')
                return {k: v for k, v in old.items() if k != 'request_hash'}
            if kind == 'GRANT' and operator['role'] == 'Staff':
                config = settings(c)
                if body.amount not in config['grant_presets'] or body.amount > config['staff_limit']:
                    raise HTTPException(403, '未授權發放此額度')
            user = get_user(c, body.user_id)
            if user['status'] != 'active':
                raise HTTPException(409, '會員已停用')
            if kind == 'REDEEM':
                scanned = credential(c, body.token)
                if scanned['id'] != body.user_id:
                    raise HTTPException(409, 'QR 與會員不符')
            before = user['balance']
            delta = body.amount if kind == 'GRANT' else -body.amount if kind == 'REDEEM' else body.amount - before
            after = before + delta
            if after < 0 or after > MAX_POINTS:
                raise HTTPException(409, '餘額不足或超出安全整數上限')
            tx = {'id': str(uuid.uuid4()), 'idempotency_key': body.idempotency_key, 'request_hash': request_hash, 'user_id': body.user_id, 'operator_id': operator['id'], 'type': kind, 'delta': delta, 'balance_before': before, 'balance_after': after, 'reason': body.reason, 'station_id': body.station_id, 'created_at': now()}
            updated = c.execute(text('UPDATE users SET balance=:after,version=version+1,updated_at=:now WHERE id=:id AND balance=:before'), {'after': after, 'before': before, 'now': now(), 'id': body.user_id})
            if updated.rowcount != 1:
                raise HTTPException(409, '餘額已變更')
            if app.state.before_ledger:
                app.state.before_ledger()
            c.execute(text('INSERT INTO transactions(' + ','.join(tx) + ') VALUES(' + ','.join(':' + key for key in tx) + ')'), tx)
        log.info('transaction id=%s operator=%s user=%s type=%s', tx['id'], operator['id'], body.user_id, kind)
        return {k: v for k, v in tx.items() if k != 'request_hash'}

    @app.post('/api/transactions/grant')
    def grant(body: Transaction, operator=Depends(current)):
        return transact('GRANT', body, operator)

    @app.post('/api/transactions/redeem')
    def redeem(body: Transaction, operator=Depends(current)):
        return transact('REDEEM', body, operator)

    @app.post('/api/transactions/adjust')
    def adjust(body: Transaction, operator=Depends(admin)):
        return transact('ADJUST', body, operator)

    def query_transactions(c, operator, user_id, kind, operator_id, start, end, limit, offset):
        sql = 'SELECT id,idempotency_key,user_id,operator_id,type,delta,balance_before,balance_after,reason,station_id,created_at FROM transactions WHERE 1=1'
        params = {}
        for column, value, symbol in [('user_id', user_id, '='), ('type', kind, '='), ('operator_id', operator['id'] if operator['role'] == 'Staff' else operator_id, '='), ('created_at', start, '>='), ('created_at', end, '<=')]:
            if value:
                key = 'p' + str(len(params))
                sql += f' AND {column}{symbol}:{key}'
                params[key] = value
        params.update(n=limit, offset=offset)
        return [dict(r) for r in c.execute(text(sql + ' ORDER BY created_at DESC LIMIT :n OFFSET :offset'), params).mappings()]

    @app.get('/api/transactions')
    def transactions(user_id: str = '', kind: str = '', operator_id: str = '', start: str = '', end: str = '', limit: int = 100, offset: int = 0, operator=Depends(current)):
        with engine.connect() as c:
            return query_transactions(c, operator, user_id, kind, operator_id, start, end, min(max(limit, 1), 200), max(offset, 0))

    @app.get('/api/transactions/by-key/{key}')
    def by_key(key: str, operator=Depends(current)):
        with engine.connect() as c:
            tx = row(c, 'SELECT * FROM transactions WHERE idempotency_key=:key', {'key': key})
        if not tx or (operator['role'] == 'Staff' and tx['operator_id'] != operator['id']):
            raise HTTPException(404, '尚未找到交易；請保留原請求並稍後查證')
        return {k: v for k, v in tx.items() if k != 'request_hash'}

    @app.get('/api/transactions/export')
    def export(user_id: str = '', kind: str = '', operator_id: str = '', start: str = '', end: str = '', operator=Depends(current)):
        def safe(value):
            value = str(value)
            return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else value

        def chunks():
            yield '\ufeff'
            offset = 0
            with engine.connect() as c:
                while True:
                    rows = query_transactions(c, operator, user_id, kind, operator_id, start, end, 1000, offset)
                    if not rows:
                        break
                    stream = io.StringIO(newline='')
                    writer = csv.writer(stream)
                    if offset == 0:
                        writer.writerow(rows[0].keys())
                    writer.writerows([safe(v) for v in record.values()] for record in rows)
                    yield stream.getvalue()
                    offset += len(rows)
        return StreamingResponse(chunks(), media_type='text/csv; charset=utf-8', headers={'Content-Disposition': 'attachment; filename="transactions.csv"'})

    @app.get('/api/settings')
    def get_settings(operator=Depends(current)):
        with engine.connect() as c:
            config = settings(c)
        return config if operator['role'] == 'Admin' else {k: config[k] for k in ('grant_presets', 'staff_limit')}

    @app.put('/api/settings')
    def put_settings(body: Settings, operator=Depends(admin)):
        if any(n < 1 or n > MAX_POINTS for n in body.grant_presets) or len(set(body.grant_presets)) != len(body.grant_presets):
            raise HTTPException(422, '固定額度必須是不重複的正整數')
        with write() as c:
            c.execute(text("INSERT OR REPLACE INTO settings VALUES('system',:v,:now)"), {'v': body.model_dump_json(), 'now': now()})
        log.info('settings_update operator=%s', operator['id'])
        return body

    @app.get('/api/operators')
    def operators(operator=Depends(admin)):
        with engine.connect() as c:
            return [dict(r) for r in c.execute(text('SELECT id,username,role,status,created_at,last_login_at FROM operators')).mappings()]

    @app.post('/api/operators')
    def create_operator(body: Operator, operator=Depends(admin)):
        strong_password(body.password)
        uid = str(uuid.uuid4())
        with write() as c:
            c.execute(text("INSERT INTO operators VALUES(:id,:u,:p,:role,'active',:now,NULL)"), {'id': uid, 'u': body.username, 'p': ph.hash(body.password), 'role': body.role, 'now': now()})
        log.info('operator_create operator=%s target=%s', operator['id'], uid)
        return {'id': uid}

    @app.patch('/api/operators/{uid}')
    def operator_status(uid: str, body: Status, operator=Depends(admin)):
        if uid == operator['id']:
            raise HTTPException(409, '不可停用自己')
        with write() as c:
            result = c.execute(text('UPDATE operators SET status=:s WHERE id=:id'), {'s': body.status, 'id': uid})
            if result.rowcount != 1:
                raise HTTPException(404, '找不到操作員')
            c.execute(text('DELETE FROM sessions WHERE operator_id=:id'), {'id': uid})
        log.info('operator_status operator=%s target=%s status=%s', operator['id'], uid, body.status)
        return {'ok': True}

    @app.post('/api/backup')
    def manual_backup(operator=Depends(admin)):
        name = backup()
        log.info('manual_backup operator=%s file=%s', operator['id'], name)
        return {'filename': name}

    @app.get('/api/backups')
    def list_backups(operator=Depends(admin)):
        return [p.name for p in sorted(backups.glob('*.db'), reverse=True)]

    if static_dir and Path(static_dir).exists():
        app.mount('/assets', StaticFiles(directory=Path(static_dir) / 'assets'), name='assets')

        @app.get('/')
        def index():
            return FileResponse(Path(static_dir) / 'index.html')

    return app


def initialize(data_dir, username, password):
    strong_password(password)
    app = create_app(data_dir)
    with app.state.write() as c:
        if c.execute(text('SELECT count(*) FROM operators')).scalar():
            raise RuntimeError('已完成初始化；禁止重複初始化')
        c.execute(text("INSERT INTO operators VALUES(:id,:u,:p,'Admin','active',:now,NULL)"), {'id': str(uuid.uuid4()), 'u': username, 'p': ph.hash(password), 'now': now()})
    app.state.engine.dispose()
