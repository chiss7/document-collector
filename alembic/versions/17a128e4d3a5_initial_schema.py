"""initial_schema

Revision ID: 17a128e4d3a5
Revises:
Create Date: 2026-06-20 11:25:09.044189

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '17a128e4d3a5'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS publications (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(100) NOT NULL,
            title VARCHAR(500) NOT NULL,
            abstract TEXT,
            original_abstract TEXT,
            source_url VARCHAR(1000) UNIQUE,
            pdf_url VARCHAR(1000),
            published_date DATE,
            accessioned_date DATE,
            available_date DATE,
            extent VARCHAR(100),
            publisher VARCHAR(100),
            rights TEXT,
            rights_uri VARCHAR(1000),
            type VARCHAR(100),
            entity_type VARCHAR(100),
            journal_name VARCHAR(200)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS excluded_publication (
            id SERIAL PRIMARY KEY,
            uuid VARCHAR(100) NOT NULL,
            title VARCHAR(500),
            url VARCHAR(1000) NOT NULL UNIQUE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id SERIAL PRIMARY KEY,
            name VARCHAR(300) NOT NULL UNIQUE,
            language VARCHAR(10)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS contributors (
            id SERIAL PRIMARY KEY,
            publication_id INTEGER NOT NULL
                REFERENCES publications(id) ON DELETE CASCADE,
            name VARCHAR(300) NOT NULL,
            role VARCHAR(20) NOT NULL,
            "order" INTEGER
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS publication_subjects (
            publication_id INTEGER NOT NULL
                REFERENCES publications(id) ON DELETE CASCADE,
            subject_id INTEGER NOT NULL
                REFERENCES subjects(id) ON DELETE CASCADE,
            PRIMARY KEY (publication_id, subject_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS social_media_records (
            id VARCHAR(200) PRIMARY KEY,
            created_at TIMESTAMPTZ,
            created_dmy DATE,
            red VARCHAR(100),
            text TEXT,
            type VARCHAR(100),
            page_id VARCHAR(200),
            audiencia_interaccion INTEGER,
            audiencia INTEGER,
            comments INTEGER,
            likes INTEGER,
            reactions INTEGER,
            shares INTEGER,
            interaccion INTEGER,
            ranking INTEGER,
            views INTEGER,
            engagement DOUBLE PRECISION,
            user_id VARCHAR(200),
            username VARCHAR(200),
            name VARCHAR(300),
            user_desc TEXT,
            followers INTEGER,
            friends INTEGER,
            is_reply BOOLEAN,
            is_rt BOOLEAN,
            reply_to_id VARCHAR(200),
            location VARCHAR(300),
            pais VARCHAR(100),
            ciudad VARCHAR(100),
            normalized_city VARCHAR(200),
            sector VARCHAR(200),
            gen VARCHAR(50),
            lang VARCHAR(50),
            sentiment INTEGER,
            sent_personalized INTEGER,
            sent_prob_neu DOUBLE PRECISION,
            sent_prob_pos DOUBLE PRECISION,
            sent_prob_neg DOUBLE PRECISION,
            verbs TEXT,
            emojis TEXT,
            concepts TEXT,
            hashtags TEXT,
            mentions TEXT,
            media TEXT,
            link VARCHAR(1000),
            linkpage VARCHAR(1000),
            keywords TEXT
        )
    """)

    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contributors_publication_id
            ON contributors (publication_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_contributors_role
            ON contributors (role)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_publication_subjects_subject
            ON publication_subjects (subject_id)
    """)


def downgrade() -> None:
    pass
