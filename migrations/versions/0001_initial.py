from alembic import op
from server.database import SCHEMA

revision = '0001'
down_revision = None


def upgrade():
    import sqlite3
    statement = ''
    for line in SCHEMA.splitlines():
        statement += line + '\n'
        if sqlite3.complete_statement(statement):
            op.execute(statement)
            statement = ''


def downgrade():
    raise RuntimeError('Restore a verified backup instead of destructive downgrade')
