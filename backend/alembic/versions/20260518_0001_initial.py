"""initial: api_keys + requests

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-18 00:00:00
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("label", sa.String(128), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_api_keys_key_hash", "api_keys", ["key_hash"])

    op.create_table(
        "requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("api_key_hash", sa.String(64), nullable=False),
        sa.Column("requested_model", sa.String(64), nullable=False),
        sa.Column("chosen_provider", sa.String(32), nullable=False),
        sa.Column("chosen_model", sa.String(64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Float(), nullable=False, server_default="0"),
        sa.Column("latency_ms", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cache_hit", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False, server_default="ok"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("fallback_chain", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_requests_api_key_hash", "requests", ["api_key_hash"])
    op.create_index("ix_requests_requested_model", "requests", ["requested_model"])
    op.create_index("ix_requests_chosen_provider", "requests", ["chosen_provider"])
    op.create_index("ix_requests_created_at", "requests", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_requests_created_at", table_name="requests")
    op.drop_index("ix_requests_chosen_provider", table_name="requests")
    op.drop_index("ix_requests_requested_model", table_name="requests")
    op.drop_index("ix_requests_api_key_hash", table_name="requests")
    op.drop_table("requests")
    op.drop_index("ix_api_keys_key_hash", table_name="api_keys")
    op.drop_table("api_keys")
