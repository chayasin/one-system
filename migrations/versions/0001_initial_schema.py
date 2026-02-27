"""Initial schema — all tables, indexes, and constraints for one-system.

Revision ID: 0001
Revises:     (none)
Create Date: 2026-02-27
"""

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

from alembic import op


def upgrade() -> None:
    # ---------------------------------------------------------------------- #
    # Enable pgcrypto for gen_random_uuid()                                   #
    # ---------------------------------------------------------------------- #
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # ---------------------------------------------------------------------- #
    # ENUM-like CHECK constraints are expressed as VARCHAR + CHECK            #
    # so that values can be added without a schema migration.                  #
    # ---------------------------------------------------------------------- #

    # ------------------------------------------------------------------ #
    # ref_service_type                                                      #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE ref_service_type (
            code    VARCHAR(5)    NOT NULL,
            label   VARCHAR(200)  NOT NULL,
            channel VARCHAR(20),            -- LINE | CALL_1146 | NULL = all
            CONSTRAINT pk_ref_service_type PRIMARY KEY (code)
        )
    """)

    # ------------------------------------------------------------------ #
    # ref_complaint_type                                                   #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE ref_complaint_type (
            code  VARCHAR(10)  NOT NULL,
            label VARCHAR(200) NOT NULL,
            CONSTRAINT pk_ref_complaint_type PRIMARY KEY (code)
        )
    """)

    # ------------------------------------------------------------------ #
    # ref_closure_reason                                                   #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE ref_closure_reason (
            code          VARCHAR(50)  NOT NULL,
            label         VARCHAR(200) NOT NULL,
            label_th      VARCHAR(200) NOT NULL,
            requires_note BOOLEAN      NOT NULL DEFAULT FALSE,
            CONSTRAINT pk_ref_closure_reason PRIMARY KEY (code)
        )
    """)

    # ------------------------------------------------------------------ #
    # sla_config                                                           #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE sla_config (
            id                 UUID         NOT NULL DEFAULT gen_random_uuid(),
            priority           VARCHAR(10)  NOT NULL,
            temp_fix_hours     INT          NOT NULL,
            permanent_fix_days INT          NOT NULL,
            overdue_t1_days    INT          NOT NULL DEFAULT 3,
            overdue_t2_days    INT          NOT NULL DEFAULT 7,
            overdue_t3_days    INT          NOT NULL DEFAULT 30,
            overdue_t4_days    INT          NOT NULL DEFAULT 365,
            updated_by         UUID,
            updated_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_sla_config PRIMARY KEY (id),
            CONSTRAINT uq_sla_config_priority UNIQUE (priority),
            CONSTRAINT chk_sla_priority CHECK (
                priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')
            )
        )
    """)

    # ------------------------------------------------------------------ #
    # users                                                                #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE users (
            id                   UUID         NOT NULL DEFAULT gen_random_uuid(),
            cognito_user_id      VARCHAR(200) NOT NULL,
            full_name            VARCHAR(200) NOT NULL,
            email                VARCHAR(200),
            role                 VARCHAR(20)  NOT NULL,
            responsible_province VARCHAR(100),
            is_active            BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at           TIMESTAMP    NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_users PRIMARY KEY (id),
            CONSTRAINT uq_users_cognito UNIQUE (cognito_user_id),
            CONSTRAINT chk_users_role CHECK (
                role IN ('ADMIN', 'DISPATCHER', 'OFFICER', 'EXECUTIVE')
            )
        )
    """)

    # ------------------------------------------------------------------ #
    # ref_handler  (LINE source handler names → IMS users)                #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE ref_handler (
            id           UUID         NOT NULL DEFAULT gen_random_uuid(),
            display_name VARCHAR(200) NOT NULL,
            user_id      UUID,
            is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at   TIMESTAMP    NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_ref_handler PRIMARY KEY (id),
            CONSTRAINT uq_ref_handler_display_name UNIQUE (display_name),
            CONSTRAINT fk_ref_handler_user FOREIGN KEY (user_id)
                REFERENCES users (id) ON DELETE SET NULL
        )
    """)

    # ------------------------------------------------------------------ #
    # case_sequence  (yearly auto-increment counter)                       #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE case_sequence (
            year     SMALLINT NOT NULL,
            last_seq INT      NOT NULL DEFAULT 0,
            CONSTRAINT pk_case_sequence PRIMARY KEY (year)
        )
    """)

    # ------------------------------------------------------------------ #
    # cases                                                                #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE cases (
            case_id               VARCHAR(20)    NOT NULL,
            source_channel        VARCHAR(20)    NOT NULL,
            source_seq_no         INT,
            source_schema_version VARCHAR(20)    NOT NULL,
            status                VARCHAR(30)    NOT NULL,
            priority              VARCHAR(10)    NOT NULL,
            service_type_code     VARCHAR(5)     NOT NULL,
            complaint_type_code   VARCHAR(10),
            reporter_name         VARCHAR(200),
            contact_number        VARCHAR(50),
            line_user_id          VARCHAR(100),
            handler_name          VARCHAR(200),
            description           TEXT           NOT NULL,
            province              VARCHAR(100),
            district_office       VARCHAR(200),
            road_number           VARCHAR(50),
            gps_lat               DECIMAL(10,7),
            gps_lng               DECIMAL(10,7),
            reported_at           TIMESTAMP      NOT NULL,
            received_at           TIMESTAMP,
            closed_at             TIMESTAMP,
            expected_fix_date     DATE,
            assigned_officer_id   UUID,
            overdue_tier          SMALLINT,
            closure_reason_code   VARCHAR(50),
            notes                 TEXT,
            duplicate_of_case_id  VARCHAR(20),
            raw_extra             JSONB,
            created_at            TIMESTAMP      NOT NULL DEFAULT NOW(),
            updated_at            TIMESTAMP      NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_cases PRIMARY KEY (case_id),
            CONSTRAINT fk_cases_service_type FOREIGN KEY (service_type_code)
                REFERENCES ref_service_type (code),
            CONSTRAINT fk_cases_complaint_type FOREIGN KEY (complaint_type_code)
                REFERENCES ref_complaint_type (code),
            CONSTRAINT fk_cases_assigned_officer FOREIGN KEY (assigned_officer_id)
                REFERENCES users (id),
            CONSTRAINT fk_cases_closure_reason FOREIGN KEY (closure_reason_code)
                REFERENCES ref_closure_reason (code),
            CONSTRAINT fk_cases_duplicate_of FOREIGN KEY (duplicate_of_case_id)
                REFERENCES cases (case_id),
            CONSTRAINT chk_cases_source_channel CHECK (
                source_channel IN ('LINE', 'CALL_1146', 'IMS_DIRECT')
            ),
            CONSTRAINT chk_cases_status CHECK (
                status IN (
                    'WAITING_VERIFY', 'IN_PROGRESS', 'FOLLOWING_UP',
                    'DUPLICATE', 'DONE', 'PENDING', 'REJECTED',
                    'CANCELLED', 'CLOSE'
                )
            ),
            CONSTRAINT chk_cases_priority CHECK (
                priority IN ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW')
            ),
            CONSTRAINT chk_cases_overdue_tier CHECK (
                overdue_tier IS NULL OR overdue_tier BETWEEN 1 AND 4
            )
        )
    """)

    # ------------------------------------------------------------------ #
    # case_history  (append-only audit trail)                              #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE case_history (
            id                    UUID         NOT NULL DEFAULT gen_random_uuid(),
            case_id               VARCHAR(20)  NOT NULL,
            changed_by_user_id    UUID,
            changed_at            TIMESTAMP    NOT NULL DEFAULT NOW(),
            prev_status           VARCHAR(30),
            new_status            VARCHAR(30),
            prev_assigned_officer UUID,
            new_assigned_officer  UUID,
            change_notes          TEXT,
            CONSTRAINT pk_case_history PRIMARY KEY (id),
            CONSTRAINT fk_case_history_case FOREIGN KEY (case_id)
                REFERENCES cases (case_id) ON DELETE CASCADE,
            CONSTRAINT fk_case_history_changed_by FOREIGN KEY (changed_by_user_id)
                REFERENCES users (id) ON DELETE SET NULL
        )
    """)

    # ------------------------------------------------------------------ #
    # case_attachments                                                     #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE case_attachments (
            id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
            case_id             VARCHAR(20)  NOT NULL,
            s3_key              VARCHAR(500) NOT NULL,
            file_name           VARCHAR(255),
            file_size_bytes     INT,
            uploaded_by_user_id UUID,
            uploaded_at         TIMESTAMP    NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_case_attachments PRIMARY KEY (id),
            CONSTRAINT fk_case_attachments_case FOREIGN KEY (case_id)
                REFERENCES cases (case_id) ON DELETE CASCADE,
            CONSTRAINT fk_case_attachments_user FOREIGN KEY (uploaded_by_user_id)
                REFERENCES users (id) ON DELETE SET NULL,
            CONSTRAINT chk_case_attachments_size CHECK (
                file_size_bytes IS NULL OR file_size_bytes <= 1048576
            )
        )
    """)

    # ------------------------------------------------------------------ #
    # notifications                                                        #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE notifications (
            id         UUID        NOT NULL DEFAULT gen_random_uuid(),
            user_id    UUID        NOT NULL,
            case_id    VARCHAR(20),
            type       VARCHAR(50) NOT NULL,
            message    TEXT,
            is_read    BOOLEAN     NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP   NOT NULL DEFAULT NOW(),
            CONSTRAINT pk_notifications PRIMARY KEY (id),
            CONSTRAINT fk_notifications_user FOREIGN KEY (user_id)
                REFERENCES users (id) ON DELETE CASCADE,
            CONSTRAINT fk_notifications_case FOREIGN KEY (case_id)
                REFERENCES cases (case_id) ON DELETE SET NULL
        )
    """)

    # ------------------------------------------------------------------ #
    # summary_cases_daily  (mini DWH — refreshed by Airflow)               #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE TABLE summary_cases_daily (
            summary_date        DATE          NOT NULL,
            source_channel      VARCHAR(20)   NOT NULL,
            province            VARCHAR(100)  NOT NULL DEFAULT '',
            district_office     VARCHAR(200)  NOT NULL DEFAULT '',
            service_type_code   VARCHAR(5)    NOT NULL,
            complaint_type_code VARCHAR(10)   NOT NULL DEFAULT '',
            priority            VARCHAR(10)   NOT NULL,
            status              VARCHAR(30)   NOT NULL,
            case_count          INT           NOT NULL DEFAULT 0,
            overdue_count       INT           NOT NULL DEFAULT 0,
            closed_within_sla   INT           NOT NULL DEFAULT 0,
            avg_close_hours     DECIMAL(10,2),
            CONSTRAINT pk_summary_cases_daily PRIMARY KEY (
                summary_date,
                source_channel,
                province,
                service_type_code,
                complaint_type_code,
                priority,
                status
            )
        )
    """)

    # ------------------------------------------------------------------ #
    # Indexes                                                              #
    # ------------------------------------------------------------------ #

    # cases — individual column indexes for filtering
    op.execute("CREATE INDEX idx_cases_status ON cases (status)")
    op.execute("CREATE INDEX idx_cases_priority ON cases (priority)")
    op.execute("CREATE INDEX idx_cases_reported_at ON cases (reported_at)")
    op.execute("CREATE INDEX idx_cases_province ON cases (province)")
    op.execute("CREATE INDEX idx_cases_district_office ON cases (district_office)")
    op.execute("CREATE INDEX idx_cases_assigned_officer ON cases (assigned_officer_id)")
    op.execute("CREATE INDEX idx_cases_overdue_tier ON cases (overdue_tier)")
    op.execute("CREATE INDEX idx_cases_service_type ON cases (service_type_code)")
    op.execute("CREATE INDEX idx_cases_complaint_type ON cases (complaint_type_code)")
    op.execute("CREATE INDEX idx_cases_source_channel ON cases (source_channel)")

    # cases — deduplication index: unique per (source_channel, source_seq_no, reported_at)
    op.execute("""
        CREATE UNIQUE INDEX uq_cases_source_dedup
        ON cases (source_channel, source_seq_no, reported_at)
        WHERE source_seq_no IS NOT NULL
    """)

    # case_history
    op.execute("CREATE INDEX idx_case_history_case_id ON case_history (case_id)")
    op.execute("CREATE INDEX idx_case_history_changed_at ON case_history (changed_at)")

    # notifications — unread lookups
    op.execute("CREATE INDEX idx_notifications_user_read ON notifications (user_id, is_read)")

    # summary_cases_daily — date range queries
    op.execute("CREATE INDEX idx_summary_date ON summary_cases_daily (summary_date)")

    # ------------------------------------------------------------------ #
    # updated_at auto-refresh trigger on cases                            #
    # ------------------------------------------------------------------ #
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_cases_updated_at
        BEFORE UPDATE ON cases
        FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_cases_updated_at ON cases")
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column")
    op.execute("DROP TABLE IF EXISTS summary_cases_daily CASCADE")
    op.execute("DROP TABLE IF EXISTS notifications CASCADE")
    op.execute("DROP TABLE IF EXISTS case_attachments CASCADE")
    op.execute("DROP TABLE IF EXISTS case_history CASCADE")
    op.execute("DROP TABLE IF EXISTS cases CASCADE")
    op.execute("DROP TABLE IF EXISTS case_sequence CASCADE")
    op.execute("DROP TABLE IF EXISTS ref_handler CASCADE")
    op.execute("DROP TABLE IF EXISTS users CASCADE")
    op.execute("DROP TABLE IF EXISTS sla_config CASCADE")
    op.execute("DROP TABLE IF EXISTS ref_closure_reason CASCADE")
    op.execute("DROP TABLE IF EXISTS ref_complaint_type CASCADE")
    op.execute("DROP TABLE IF EXISTS ref_service_type CASCADE")
