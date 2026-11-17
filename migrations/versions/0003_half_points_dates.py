from alembic import op
from datetime import datetime, timezone

revision = '0003'
down_revision = '0002'


def upgrade():
    # Preserve legacy values, including large integers. New requests use a smaller
    # bound so half-points remain exactly representable in the browser.
    connection = op.get_bind()
    for name in ('users', 'transactions'):
        schema = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).scalar_one()
        schema = schema.replace('CREATE TABLE ' + name, 'CREATE TABLE ' + name + '_new', 1)
        schema = schema.replace(f'CREATE TABLE "{name}"', 'CREATE TABLE ' + name + '_new', 1)
        for column in ('balance', 'delta', 'balance_before', 'balance_after'):
            schema = schema.replace(f"typeof({column})='integer'", f"typeof({column}) IN ('integer','real') AND {column}*2=CAST({column}*2 AS INTEGER)")
        op.execute(schema)
        op.execute(f'INSERT INTO {name}_new SELECT * FROM {name}')
        op.execute(f'DROP TABLE {name}')
        op.execute(f'ALTER TABLE {name}_new RENAME TO {name}')
    op.execute('ALTER TABLE transactions ADD COLUMN occurred_at TEXT')
    for record in connection.exec_driver_sql('SELECT id,created_at FROM transactions').fetchall():
        date = datetime.fromisoformat(record[1]).astimezone(timezone.utc)
        connection.exec_driver_sql('UPDATE transactions SET occurred_at=? WHERE id=?',
                                   (date.isoformat(timespec='microseconds'), record[0]))
    for column in ('user_id', 'operator_id', 'type'):
        op.execute(f'CREATE INDEX tx_{column}_occurred ON transactions({column},occurred_at)')
    op.execute("CREATE TRIGGER tx_no_update BEFORE UPDATE ON transactions BEGIN SELECT RAISE(ABORT,'ledger is immutable'); END")
    op.execute("CREATE TRIGGER tx_no_delete BEFORE DELETE ON transactions BEGIN SELECT RAISE(ABORT,'ledger is immutable'); END")


def downgrade():
    raise RuntimeError('含半點與補登資料，請使用升級前備份復原')
