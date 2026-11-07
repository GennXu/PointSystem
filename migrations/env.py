from alembic import context
from sqlalchemy import create_engine

with create_engine(context.config.get_main_option('sqlalchemy.url')).connect() as connection:
    # SQLite table rebuilds need FK checks suspended before BEGIN; validate before commit.
    connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
    connection.commit()
    connection.exec_driver_sql('BEGIN IMMEDIATE')
    try:
        context.configure(connection=connection, transactional_ddl=True)
        context.run_migrations()
        if connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall():
            raise RuntimeError('資料庫升級外鍵驗證失敗')
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    finally:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
