"""add firebase_key, track_changes, user_answer_histories

Revision ID: f4c5d6e7f890
Revises: e3b4c5d6f789
Create Date: 2026-02-03 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4c5d6e7f890'
down_revision: Union[str, None] = 'e3b4c5d6f789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # service_settings: Firebase Key JSON (暗号化) + client_email (表示用)
    op.add_column('service_settings', sa.Column(
        'firebase_key_json_enc', sa.Text(), nullable=True,
        comment='Firebase SA JSON (暗号化)',
    ))
    op.add_column('service_settings', sa.Column(
        'firebase_client_email', sa.String(255), nullable=True,
        comment='Firebase client_email (表示用)',
    ))

    # plan_questions: 変更履歴記録フラグ
    op.add_column('plan_questions', sa.Column(
        'track_changes', sa.Boolean(), nullable=False,
        server_default=sa.text('0'),
        comment='回答変更履歴を記録するか',
    ))

    # user_answer_histories: 回答変更履歴テーブル
    op.create_table(
        'user_answer_histories',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(),
                  sa.ForeignKey('users.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('question_id', sa.Integer(),
                  sa.ForeignKey('plan_questions.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('var_name', sa.String(100), nullable=False,
                  comment='変数名スナップショット'),
        sa.Column('plan_id', sa.Integer(),
                  sa.ForeignKey('plans.id', ondelete='CASCADE'),
                  nullable=False, index=True),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('changed_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('user_answer_histories')
    op.drop_column('plan_questions', 'track_changes')
    op.drop_column('service_settings', 'firebase_client_email')
    op.drop_column('service_settings', 'firebase_key_json_enc')
