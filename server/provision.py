"""Run as the SQL Express administrator on the application host."""
import json
import re
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from server.sqlserver import initialize_schema


def provision(data, server, database, account, backup_dir):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', database):
        raise ValueError('資料庫名稱僅允許英數及底線，且以英文字母開頭')
    if not account or any(c in account for c in '\r\n\x00'):
        raise ValueError('請指定執行主機 API 的 Windows 帳號')
    data = Path(data).resolve()
    data.mkdir(parents=True, exist_ok=True)
    config_file = data / 'config.json'
    config = json.loads(config_file.read_text(encoding='utf-8-sig')) if config_file.exists() else {}
    if config.get('database_url'):
        raise RuntimeError('config.json 已有 database_url，拒絕覆寫；請核對既有設定')
    url = URL.create('mssql+pyodbc', host=server, database=database,
                     query={'driver': 'ODBC Driver 18 for SQL Server', 'Trusted_Connection': 'yes',
                            'Encrypt': 'yes', 'TrustServerCertificate': 'yes'})
    engine = create_engine(url.set(database='master'), isolation_level='AUTOCOMMIT', hide_parameters=True)
    quoted_account = '[' + account.replace(']', ']]') + ']'
    quoted_db = '[' + database + ']'
    try:
        with engine.connect() as connection:
            exists = connection.execute(text('SELECT DB_ID(:name)'), {'name': database}).scalar()
            if exists:
                raise RuntimeError('資料庫已存在，拒絕變更；請選擇新名稱或手動設定既有資料庫')
            connection.exec_driver_sql('CREATE DATABASE ' + quoted_db)
            if not connection.execute(text('SELECT SUSER_ID(:name)'), {'name': account}).scalar():
                connection.exec_driver_sql('CREATE LOGIN ' + quoted_account + ' FROM WINDOWS')
    finally:
        engine.dispose()
    engine = create_engine(url, hide_parameters=True)
    try:
        initialize_schema(engine)
        from server.sqlserver import write_transaction
        with write_transaction(engine) as connection:
            principal = connection.execute(text('SELECT name FROM sys.database_principals WHERE sid=SUSER_SID(:name)'), {'name': account}).scalar()
            if not principal:
                connection.exec_driver_sql('CREATE USER ' + quoted_account + ' FOR LOGIN ' + quoted_account)
                principal = account
            if principal != 'dbo':
                quoted_principal = '[' + principal.replace(']', ']]') + ']'
                for role in ('db_datareader', 'db_datawriter', 'db_backupoperator'):
                    connection.exec_driver_sql('ALTER ROLE [' + role + '] ADD MEMBER ' + quoted_principal)
    finally:
        engine.dispose()
    config.update(database_url=url.render_as_string(hide_password=False),
                  backup_dir=str(Path(backup_dir).resolve()), port=config.get('port', 8080))
    config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding='utf-8')
    print('SQL Express 資料庫及 schema 已建立，config.json 已寫入。')
    print('請確認 SQL Server 服務帳號與 API 執行帳號可存取備份目錄。')
