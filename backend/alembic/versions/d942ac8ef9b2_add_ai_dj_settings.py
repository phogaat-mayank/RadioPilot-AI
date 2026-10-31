"""Add AI DJ Voice Settings persistent table.

Revision ID: d942ac8ef9b2
Revises: c832ac8ef9a1
"""

from alembic import op
import sqlalchemy as sa

revision = "d942ac8ef9b2"
down_revision = "c832ac8ef9a1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the ai_dj_settings table and seed singleton configuration."""
    op.create_table(
        "ai_dj_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("voice_id", sa.String(100), nullable=False, server_default="hi_IN-priyamvada-medium"),
        sa.Column("language", sa.String(10), nullable=False, server_default="hi"),
        sa.Column("frequency", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("volume", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("intro_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("outro_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("greeting_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )


def downgrade() -> None:
    """Drop the ai_dj_settings table."""
    op.drop_table("ai_dj_settings")
