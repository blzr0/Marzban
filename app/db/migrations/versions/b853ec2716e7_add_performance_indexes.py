"""add performance indexes

Adds indexes on columns filtered on every periodic job and in per-user
usage lookups, but previously unindexed:

- users.status      (review_users, reset_user_data_usage, autodelete)
- users.expire       (expiry checks)
- users.admin_id     (filtering users by admin)
- node_user_usages.user_id       (per-user traffic aggregation)
- notification_reminders.user_id (per-user reminder lookups)

Revision ID: b853ec2716e7
Revises: 2b231de97dc3
Create Date: 2026-07-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b853ec2716e7'
down_revision = '2b231de97dc3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index('ix_users_status', 'users', ['status'], unique=False)
    op.create_index('ix_users_expire', 'users', ['expire'], unique=False)
    op.create_index('ix_users_admin_id', 'users', ['admin_id'], unique=False)
    op.create_index('ix_node_user_usages_user_id', 'node_user_usages', ['user_id'], unique=False)
    op.create_index('ix_notification_reminders_user_id', 'notification_reminders', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_notification_reminders_user_id', table_name='notification_reminders')
    op.drop_index('ix_node_user_usages_user_id', table_name='node_user_usages')
    op.drop_index('ix_users_admin_id', table_name='users')
    op.drop_index('ix_users_expire', table_name='users')
    op.drop_index('ix_users_status', table_name='users')
