"""add firebase_credentials table and update plan_external_data_settings

Revision ID: c3d4e5f6g789
Revises: b2c3d4e5f678
Create Date: 2026-02-05 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6g789'
down_revision: Union[str, None] = 'b2c3d4e5f678'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # firebase_credentials テーブル作成
    op.create_table(
        'firebase_credentials',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(255), nullable=False, unique=True, comment='認証情報の識別名'),
        sa.Column('encrypted_json', sa.Text(), nullable=False, comment='暗号化されたサービスアカウントJSON'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    # plan_external_data_settings に新カラム追加
    op.add_column('plan_external_data_settings',
        sa.Column('firebase_credential_id', sa.Integer(), nullable=True, comment='Firebase認証情報ID'))
    op.add_column('plan_external_data_settings',
        sa.Column('delete_after_process', sa.Boolean(), nullable=False, server_default='0', comment='処理後にFirestoreデータを削除'))

    # 外部キー制約
    op.create_foreign_key(
        'fk_plan_external_data_settings_firebase_credential',
        'plan_external_data_settings', 'firebase_credentials',
        ['firebase_credential_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_plan_external_data_settings_firebase_credential', 'plan_external_data_settings', type_='foreignkey')
    op.drop_column('plan_external_data_settings', 'delete_after_process')
    op.drop_column('plan_external_data_settings', 'firebase_credential_id')
    op.drop_table('firebase_credentials')
