from alembic import op
from server.database import SCHEMA

revision = '0001'
down_revision = None


def upgrade():
    # sqlite3 executescript understands trigger bodies containing semicolons.
    op.get_bind().connection.driver_connection.executescript(SCHEMA)


def downgrade():
    raise RuntimeError('Restore a verified backup instead of destructive downgrade')
