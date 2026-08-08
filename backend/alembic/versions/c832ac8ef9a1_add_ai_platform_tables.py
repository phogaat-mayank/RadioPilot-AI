"""Add durable multi-agent platform records.

Revision ID: c832ac8ef9a1
Revises: 8fba2e97ca79
"""

from alembic import op
import sqlalchemy as sa

revision = "c832ac8ef9a1"
down_revision = "8fba2e97ca79"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create additive AI records without changing existing radio tables."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'PRODUCER'")
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'GUEST'")
    op.create_table("ai_tasks", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("task_type", sa.String(80), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("agent_name", sa.String(80), nullable=False), sa.Column("requested_by", sa.String(255), nullable=False), sa.Column("input_json", sa.JSON(), nullable=False), sa.Column("output_json", sa.JSON(), nullable=False), sa.Column("model", sa.String(120), nullable=False), sa.Column("execution_ms", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ai_tasks_task_type", "ai_tasks", ["task_type"])
    op.create_index("ix_ai_tasks_status", "ai_tasks", ["status"])
    op.create_table("ai_logs", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("task_id", sa.Integer(), sa.ForeignKey("ai_tasks.id"), nullable=True), sa.Column("level", sa.String(20), nullable=False), sa.Column("message", sa.Text(), nullable=False), sa.Column("agent_name", sa.String(80), nullable=False), sa.Column("metadata_json", sa.JSON(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_ai_logs_task_id", "ai_logs", ["task_id"])
    op.create_table("ai_memory", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("namespace", sa.String(80), nullable=False), sa.Column("memory_key", sa.String(255), nullable=False), sa.Column("value_json", sa.JSON(), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False), sa.UniqueConstraint("namespace", "memory_key", name="uq_ai_memory_key"))
    op.create_index("ix_ai_memory_namespace", "ai_memory", ["namespace"])
    op.create_table("ai_conversations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("session_id", sa.String(80), nullable=False), sa.Column("role", sa.String(20), nullable=False), sa.Column("content", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_ai_conversations_session_id", "ai_conversations", ["session_id"])
    op.create_table("ai_decisions", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("task_id", sa.Integer(), sa.ForeignKey("ai_tasks.id"), nullable=True), sa.Column("decision_type", sa.String(80), nullable=False), sa.Column("decision_json", sa.JSON(), nullable=False), sa.Column("status", sa.String(30), nullable=False), sa.Column("approved_by", sa.String(255), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False))
    op.create_index("ix_ai_decisions_task_id", "ai_decisions", ["task_id"])
    op.create_index("ix_ai_decisions_status", "ai_decisions", ["status"])


def downgrade() -> None:
    """Remove only the additive AI tables."""
    op.drop_index("ix_ai_decisions_status", table_name="ai_decisions")
    op.drop_index("ix_ai_decisions_task_id", table_name="ai_decisions")
    op.drop_table("ai_decisions")
    op.drop_index("ix_ai_conversations_session_id", table_name="ai_conversations")
    op.drop_table("ai_conversations")
    op.drop_index("ix_ai_memory_namespace", table_name="ai_memory")
    op.drop_table("ai_memory")
    op.drop_index("ix_ai_logs_task_id", table_name="ai_logs")
    op.drop_table("ai_logs")
    op.drop_index("ix_ai_tasks_status", table_name="ai_tasks")
    op.drop_index("ix_ai_tasks_task_type", table_name="ai_tasks")
    op.drop_table("ai_tasks")
