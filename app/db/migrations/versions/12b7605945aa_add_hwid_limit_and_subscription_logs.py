"""add hwid limit, user hwids and subscription logs

Revision ID: 12b7605945aa
Revises: cd67ec7ef92f
Create Date: 2026-11-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '12b7605945aa'
down_revision = 'cd67ec7ef92f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('hwid_limit', sa.Integer(), nullable=False, server_default=sa.text('0')))

    op.create_table(
        'user_hwids',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('hwid', sa.String(128), nullable=False),
        sa.Column('device_os', sa.String(64), nullable=True),
        sa.Column('os_version', sa.String(64), nullable=True),
        sa.Column('device_model', sa.String(128), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('host', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('last_seen_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'hwid'),
    )
    op.create_index(op.f('ix_user_hwids_user_id'), 'user_hwids', ['user_id'], unique=False)

    op.create_table(
        'subscription_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key_hash', sa.String(64), nullable=False),
        sa.Column('status', sa.String(32), nullable=False),
        sa.Column('hwid', sa.String(128), nullable=True),
        sa.Column('device_os', sa.String(64), nullable=True),
        sa.Column('os_version', sa.String(64), nullable=True),
        sa.Column('device_model', sa.String(128), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('ip', sa.String(64), nullable=True),
        sa.Column('host', sa.String(255), nullable=True),
        sa.Column('request_path', sa.String(512), nullable=True),
        sa.Column('count', sa.Integer(), nullable=False, server_default=sa.text('1')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key_hash'),
    )
    op.create_index(op.f('ix_subscription_logs_user_id'), 'subscription_logs', ['user_id'], unique=False)
    op.create_index(op.f('ix_subscription_logs_status'), 'subscription_logs', ['status'], unique=False)
    op.create_index(op.f('ix_subscription_logs_hwid'), 'subscription_logs', ['hwid'], unique=False)
    op.create_index(op.f('ix_subscription_logs_updated_at'), 'subscription_logs', ['updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_subscription_logs_updated_at'), table_name='subscription_logs')
    op.drop_index(op.f('ix_subscription_logs_hwid'), table_name='subscription_logs')
    op.drop_index(op.f('ix_subscription_logs_status'), table_name='subscription_logs')
    op.drop_index(op.f('ix_subscription_logs_user_id'), table_name='subscription_logs')
    op.drop_table('subscription_logs')
    op.drop_index(op.f('ix_user_hwids_user_id'), table_name='user_hwids')
    op.drop_table('user_hwids')
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('hwid_limit')
