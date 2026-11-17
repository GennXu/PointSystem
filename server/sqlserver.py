"""SQL Express schema, serialized write transactions, backup and data transfer."""
import json
import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (BigInteger, CheckConstraint, Column, ForeignKey, Index,
                        Integer, MetaData, Numeric, String, Table, Unicode, UnicodeText,
                        create_engine, text)

VERSION = '0003'
metadata = MetaData()


def col(name, size=80, **kwargs):
    return Column(name, Unicode(size, collation='Latin1_General_100_BIN2'), **kwargs)


operators = Table('operators', metadata,
    col('id', primary_key=True), col('username', unique=True, nullable=False),
    col('password_hash', 512, nullable=False), col('role', nullable=False),
    col('status', nullable=False), col('created_at', nullable=False), col('last_login_at'),
    CheckConstraint("role IN ('Admin','Staff')"), CheckConstraint("status IN ('active','disabled')"))
users = Table('users', metadata,
    col('id', primary_key=True),
    Column('member_code', Unicode(80, collation='Latin1_General_100_BIN2'), unique=True, nullable=False),
    col('display_name', 100, nullable=False), col('status', nullable=False),
    Column('balance', Numeric(17, 1), nullable=False, server_default='0'),
    col('created_at', nullable=False), col('updated_at', nullable=False),
    Column('version', BigInteger, nullable=False, server_default='0'),
    CheckConstraint("status IN ('active','disabled')"),
    CheckConstraint('balance*2=FLOOR(balance*2) AND ABS(balance)<=9007199254740991'))
qr = Table('qr_credentials', metadata,
    col('id', primary_key=True), Column('user_id', Unicode(80, collation='Latin1_General_100_BIN2'), ForeignKey('users.id'), nullable=False),
    col('token_hash', 64, unique=True, nullable=False), col('token_cipher', 512, nullable=False),
    col('status', nullable=False), col('issued_at', nullable=False), col('revoked_at'), col('expires_at'),
    CheckConstraint("status IN ('active','revoked')"))
Index('one_active_qr', qr.c.user_id, unique=True, mssql_where=text("status='active'"))
transactions = Table('transactions', metadata,
    col('id', primary_key=True), col('idempotency_key', 128, unique=True, nullable=False),
    col('request_hash', 64, nullable=False),
    Column('user_id', Unicode(80, collation='Latin1_General_100_BIN2'), ForeignKey('users.id'), nullable=False),
    Column('operator_id', Unicode(80, collation='Latin1_General_100_BIN2'), ForeignKey('operators.id'), nullable=False),
    col('type', nullable=False),
    *[Column(name, Numeric(17, 1), nullable=False) for name in ('delta', 'balance_before', 'balance_after')],
    col('reason', 500, nullable=False), col('station_id', nullable=False),
    col('created_at', nullable=False), col('occurred_at', nullable=False),
    CheckConstraint("type IN ('GRANT','REDEEM','ADJUST')"),
    CheckConstraint('balance_after=balance_before+delta'),
    *[CheckConstraint(f'{name}*2=FLOOR({name}*2) AND ABS({name})<=9007199254740991')
      for name in ('delta', 'balance_before', 'balance_after')])
for name in ('user_id', 'operator_id', 'type'):
    Index('tx_' + name + '_occurred', transactions.c[name], transactions.c.occurred_at)
Table('settings', metadata, col('key', primary_key=True), Column('value_json', UnicodeText, nullable=False), col('updated_at', nullable=False))
Table('sessions', metadata, col('token_hash', 64, primary_key=True),
      Column('operator_id', Unicode(80, collation='Latin1_General_100_BIN2'), ForeignKey('operators.id'), nullable=False),
      col('csrf', nullable=False), col('expires_at', nullable=False))
Table('portal_sessions', metadata, col('token_hash', 64, primary_key=True),
      Column('user_id', Unicode(80, collation='Latin1_General_100_BIN2'), ForeignKey('users.id'), nullable=False),
      Column('credential_id', Unicode(80, collation='Latin1_General_100_BIN2'), ForeignKey('qr_credentials.id'), nullable=False),
      col('expires_at', nullable=False))
Table('login_attempts', metadata, col('source', 120, primary_key=True),
      Column('count', Integer, nullable=False), Column('window_start', Numeric(20, 6), nullable=False))
Table('alembic_version', metadata, Column('version_num', String(32), primary_key=True))


def configured_url(data):
    config_file = Path(data) / 'config.json'
    config = json.loads(config_file.read_text(encoding='utf-8-sig')) if config_file.exists() else {}
    value = os.environ.get('QRPOINT_DATABASE_URL') or config.get('database_url')
    if value and not value.startswith('mssql+pyodbc://'):
        raise RuntimeError('database_url 必須使用 mssql+pyodbc SQL Server 連線')
    return value


def engine_for_url(url):
    return create_engine(url, pool_pre_ping=True, hide_parameters=True, connect_args={'timeout': 15})


@contextmanager
def write_transaction(engine):
    with engine.connect() as connection:
        mssql = connection.dialect.name == 'mssql'
        try:
            if mssql:
                # Exactly one server transaction, regardless of ODBC implicit mode.
                connection.exec_driver_sql('SET XACT_ABORT ON; SET IMPLICIT_TRANSACTIONS OFF; BEGIN TRANSACTION')
                connection.exec_driver_sql("""DECLARE @result int;
                    EXEC @result=sys.sp_getapplock @Resource=N'QRPointSystem.write',
                        @LockMode='Exclusive', @LockOwner='Transaction', @LockTimeout=15000;
                    IF @result < 0 THROW 51000, N'資料庫忙碌，請稍後重試原請求', 1;""")
            else:
                connection.exec_driver_sql('BEGIN IMMEDIATE')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            if mssql:
                connection.exec_driver_sql('SET IMPLICIT_TRANSACTIONS ON')
                connection.rollback()


def initialize_schema(engine):
    from sqlalchemy import inspect
    if inspect(engine).has_table('alembic_version'):
        with engine.connect() as connection:
            version = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
            if version != VERSION:
                raise RuntimeError('SQL Server schema 版本不相容，請先執行 schema 指令')
        return
    with write_transaction(engine) as connection:
        metadata.create_all(connection)
        version = connection.execute(text('SELECT version_num FROM alembic_version')).scalar()
        if version not in (None, VERSION):
            raise RuntimeError('SQL Server schema 版本不相容')
        if version is None:
            connection.execute(text('INSERT INTO alembic_version VALUES(:v)'), {'v': VERSION})
        connection.exec_driver_sql("""CREATE OR ALTER TRIGGER tx_immutable ON transactions
            AFTER UPDATE, DELETE AS BEGIN
            SET NOCOUNT ON;
            THROW 51001, N'ledger is immutable', 1;
            END""")


def paged(connection, sql):
    if connection.dialect.name == 'mssql':
        return sql.replace('LIMIT :n OFFSET :offset', 'OFFSET :offset ROWS FETCH NEXT :n ROWS ONLY')
    return sql


def backup(engine, destination):
    # Destination is on the SQL Server host and must be writable by its service.
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        name = connection.execute(text('SELECT DB_NAME()')).scalar_one()
        connection.execute(text('BACKUP DATABASE [' + name.replace(']', ']]') + '] TO DISK=:path WITH COPY_ONLY, CHECKSUM'), {'path': str(destination)})
    return str(destination)


def verify_backup(engine, source):
    # VERIFYONLY requires CREATE DATABASE permission; keep it out of runtime backup.
    with engine.connect().execution_options(isolation_level='AUTOCOMMIT') as connection:
        connection.execute(text('RESTORE VERIFYONLY FROM DISK=:path WITH CHECKSUM'), {'path': str(source)})


def restore_database(engine, source):
    """Local maintenance only. Caller must stop the service and authenticate."""
    with engine.connect() as connection:
        name = connection.execute(text('SELECT DB_NAME()')).scalar_one()
    quoted = '[' + name.replace(']', ']]') + ']'
    admin_url = engine.url.set(database='master')
    # URLs generated with odbc_connect must not silently keep their old database.
    if 'odbc_connect' in engine.url.query:
        raise RuntimeError('還原請使用標準 mssql+pyodbc URL（不要使用 odbc_connect）')
    maintenance = create_engine(admin_url, isolation_level='AUTOCOMMIT', hide_parameters=True)
    engine.dispose()
    try:
        with maintenance.connect() as connection:
            connection.execute(text('RESTORE VERIFYONLY FROM DISK=:path WITH CHECKSUM'), {'path': str(source)})
            header = connection.execute(text('RESTORE HEADERONLY FROM DISK=:path'), {'path': str(source)}).mappings().one()
            if header['DatabaseName'] != name:
                raise RuntimeError('備份的資料庫名稱不符')
            connection.exec_driver_sql('ALTER DATABASE ' + quoted + ' SET SINGLE_USER WITH ROLLBACK IMMEDIATE')
            try:
                connection.execute(text('RESTORE DATABASE ' + quoted + ' FROM DISK=:path WITH REPLACE, CHECKSUM'), {'path': str(source)})
            finally:
                connection.exec_driver_sql('ALTER DATABASE ' + quoted + ' SET MULTI_USER')
    finally:
        maintenance.dispose()
