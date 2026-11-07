from alembic import op

revision = '0002'
down_revision = '0001'


def upgrade():
    statements = [
        """CREATE TABLE users_new(id TEXT PRIMARY KEY, member_code TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','disabled')), balance INTEGER NOT NULL DEFAULT 0 CHECK(typeof(balance)='integer' AND balance BETWEEN -9007199254740991 AND 9007199254740991), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 0)""",
        'INSERT INTO users_new SELECT * FROM users',
        'DROP TABLE users',
        'ALTER TABLE users_new RENAME TO users',
        """CREATE TABLE transactions_new(id TEXT PRIMARY KEY, idempotency_key TEXT UNIQUE NOT NULL, request_hash TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id), operator_id TEXT NOT NULL REFERENCES operators(id), type TEXT NOT NULL CHECK(type IN ('GRANT','REDEEM','ADJUST')), delta INTEGER NOT NULL CHECK(typeof(delta)='integer' AND delta BETWEEN -9007199254740991 AND 9007199254740991), balance_before INTEGER NOT NULL CHECK(typeof(balance_before)='integer' AND balance_before BETWEEN -9007199254740991 AND 9007199254740991), balance_after INTEGER NOT NULL CHECK(typeof(balance_after)='integer' AND balance_after BETWEEN -9007199254740991 AND 9007199254740991), reason TEXT NOT NULL, station_id TEXT NOT NULL, created_at TEXT NOT NULL, CHECK(balance_after=balance_before+delta))""",
        'INSERT INTO transactions_new SELECT * FROM transactions',
        'DROP TABLE transactions',
        'ALTER TABLE transactions_new RENAME TO transactions',
        'CREATE INDEX tx_user_time ON transactions(user_id,created_at)',
        'CREATE INDEX tx_operator_time ON transactions(operator_id,created_at)',
        'CREATE INDEX tx_type_time ON transactions(type,created_at)',
        "CREATE TRIGGER tx_no_update BEFORE UPDATE ON transactions BEGIN SELECT RAISE(ABORT,'ledger is immutable'); END",
        "CREATE TRIGGER tx_no_delete BEFORE DELETE ON transactions BEGIN SELECT RAISE(ABORT,'ledger is immutable'); END",
        'CREATE TABLE portal_sessions(token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), credential_id TEXT NOT NULL REFERENCES qr_credentials(id), expires_at TEXT NOT NULL)',
        'CREATE INDEX portal_expiry ON portal_sessions(expires_at)',
    ]
    for statement in statements:
        op.execute(statement)


def downgrade():
    raise RuntimeError('負餘額資料不能直接降版，請使用升級前備份與舊版程式復原')
