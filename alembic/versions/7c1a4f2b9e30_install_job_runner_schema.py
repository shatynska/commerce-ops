"""install the job runner's schema

Revision ID: 7c1a4f2b9e30
Revises: cec323b69794
Create Date: 2026-08-23 07:32:00.000000

Installs `procrastinate`'s schema through Alembic rather than through the
runner's own CLI, so that Alembic stays the single answer to "what shape is
this database, and how did it get there", the runner's schema version is
pinned to a revision, and `downgrade` has somewhere to live. See design.md,
"Install the runner's schema through Alembic, and state the mechanism".

The SQL below is **vendored verbatim** from `procrastinate` 3.9.0 rather than
read from the installed package at upgrade time. Reading it at upgrade time
would make one revision produce different schemas depending on which runner
version happened to be installed -- the opposite of the version pinning that
justified using Alembic here at all (tasks.md 1.4a). A unit test asserts this
literal still matches the installed runner, so a `uv lock --upgrade` that
moves the runner cannot silently leave the two out of step (tasks.md 1.1a).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import util

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c1a4f2b9e30"
down_revision: str | Sequence[str] | None = "cec323b69794"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RUNNER_SCHEMA = """\
-- Procrastinate Schema

DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS plpgsql WITH SCHEMA pg_catalog;
EXCEPTION
    WHEN OTHERS THEN
        -- On managed PostgreSQL services (e.g. Azure Database for PostgreSQL, Amazon RDS,
        -- Google Cloud SQL), CREATE EXTENSION may fail with various error codes:
        -- insufficient_privilege, feature_not_supported, or provider-specific errors.
        -- Before ignoring, verify the extension actually exists — if it does not exist
        -- and cannot be created, re-raise so the failure is explicit.
        IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'plpgsql') THEN
            RAISE NOTICE 'plpgsql extension already exists, skipping creation.';
        ELSE
            RAISE;
        END IF;
END;
$$;

-- Enums

CREATE TYPE procrastinate_job_status AS ENUM (
    'todo',  -- The job is queued
    'doing',  -- The job has been fetched by a worker
    'succeeded',  -- The job ended successfully
    'failed',  -- The job ended with an error
    'cancelled', -- The job was cancelled
    'aborting',  -- legacy, not used anymore since v3.0.0
    'aborted'  -- The job was aborted
);

CREATE TYPE procrastinate_job_event_type AS ENUM (
    'deferred',  -- Job created, in todo
    'started',  -- todo -> doing
    'deferred_for_retry',  -- doing -> todo
    'failed',  -- doing -> failed
    'succeeded',  -- doing -> succeeded
    'cancelled', -- todo -> cancelled
    'abort_requested', -- not a state transition, but set in a separate field
    'aborted', -- doing -> aborted (only allowed when abort_requested field is set)
    'scheduled', -- not a state transition, but recording when a task is scheduled for
    'retried' -- Manually retried failed job
);

-- Composite Types

CREATE TYPE procrastinate_job_to_defer_v1 AS (
    queue_name character varying,
    task_name character varying,
    priority integer,
    lock text,
    queueing_lock text,
    args jsonb,
    scheduled_at timestamp with time zone
);

-- Tables

CREATE TABLE procrastinate_workers(
    id bigint PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    last_heartbeat timestamp with time zone NOT NULL DEFAULT NOW()
);

CREATE TABLE procrastinate_jobs (
    id bigserial PRIMARY KEY,
    queue_name character varying(128) NOT NULL,
    task_name character varying(128) NOT NULL,
    priority integer DEFAULT 0 NOT NULL,
    lock text,
    queueing_lock text,
    args jsonb DEFAULT '{}' NOT NULL,
    status procrastinate_job_status DEFAULT 'todo'::procrastinate_job_status NOT NULL,
    scheduled_at timestamp with time zone NULL,
    attempts integer DEFAULT 0 NOT NULL,
    abort_requested boolean DEFAULT false NOT NULL,
    worker_id bigint REFERENCES procrastinate_workers(id) ON DELETE SET NULL,
    CONSTRAINT check_not_todo_abort_requested CHECK (NOT (status = 'todo' AND abort_requested = true))
);

CREATE TABLE procrastinate_periodic_defers (
    id bigserial PRIMARY KEY,
    task_name character varying(128) NOT NULL,
    defer_timestamp bigint,
    job_id bigint REFERENCES procrastinate_jobs(id) NULL,
    periodic_id character varying(128) NOT NULL DEFAULT '',
    CONSTRAINT procrastinate_periodic_defers_unique UNIQUE (task_name, periodic_id, defer_timestamp)
);

CREATE TABLE procrastinate_events (
    id bigserial PRIMARY KEY,
    job_id bigint NOT NULL REFERENCES procrastinate_jobs ON DELETE CASCADE,
    type procrastinate_job_event_type,
    at timestamp with time zone DEFAULT NOW() NULL
);

-- Constraints & Indices

-- this prevents from having several jobs with the same queueing lock in the "todo" state
CREATE UNIQUE INDEX procrastinate_jobs_queueing_lock_idx_v1 ON procrastinate_jobs (queueing_lock) WHERE status = 'todo';
-- this prevents from having several jobs with the same lock in the "doing" state
CREATE UNIQUE INDEX procrastinate_jobs_lock_idx_v1 ON procrastinate_jobs (lock) WHERE status = 'doing';

-- Index for select_stalled_jobs_by_heartbeat query
CREATE INDEX idx_procrastinate_jobs_worker_not_null ON procrastinate_jobs(worker_id) WHERE worker_id IS NOT NULL AND status = 'doing'::procrastinate_job_status;

CREATE INDEX procrastinate_jobs_queue_name_idx_v1 ON procrastinate_jobs(queue_name);
CREATE INDEX procrastinate_jobs_id_lock_idx_v1 ON procrastinate_jobs (id, lock) WHERE status = ANY (ARRAY['todo'::procrastinate_job_status, 'doing'::procrastinate_job_status]);
CREATE INDEX procrastinate_jobs_priority_idx_v1 ON procrastinate_jobs(priority desc, id asc) WHERE (status = 'todo'::procrastinate_job_status);

CREATE INDEX procrastinate_events_job_id_fkey_v1 ON procrastinate_events(job_id);

CREATE INDEX procrastinate_periodic_defers_job_id_fkey_v1 ON procrastinate_periodic_defers(job_id);

CREATE INDEX idx_procrastinate_workers_last_heartbeat ON procrastinate_workers(last_heartbeat);

-- Functions
CREATE FUNCTION procrastinate_defer_jobs_v1(
    jobs procrastinate_job_to_defer_v1[]
)
    RETURNS bigint[]
    LANGUAGE plpgsql
AS $$
DECLARE
    job_ids bigint[];
BEGIN
    WITH inserted_jobs AS (
        INSERT INTO procrastinate_jobs (queue_name, task_name, priority, lock, queueing_lock, args, scheduled_at)
        SELECT (job).queue_name,
               (job).task_name,
               (job).priority,
               (job).lock,
               (job).queueing_lock,
               (job).args,
               (job).scheduled_at
        FROM unnest(jobs) AS job
        RETURNING id
    )
    SELECT array_agg(id) FROM inserted_jobs INTO job_ids;

    RETURN job_ids;
END;
$$;

CREATE FUNCTION procrastinate_defer_periodic_job_v2(
    _queue_name character varying,
    _lock character varying,
    _queueing_lock character varying,
    _task_name character varying,
    _priority integer,
    _periodic_id character varying,
    _defer_timestamp bigint,
    _args jsonb
)
    RETURNS bigint
    LANGUAGE plpgsql
AS $$
DECLARE
	_job_id bigint;
	_defer_id bigint;
BEGIN
    INSERT
        INTO procrastinate_periodic_defers (task_name, periodic_id, defer_timestamp)
        VALUES (_task_name, _periodic_id, _defer_timestamp)
        ON CONFLICT DO NOTHING
        RETURNING id into _defer_id;

    IF _defer_id IS NULL THEN
        RETURN NULL;
    END IF;

    UPDATE procrastinate_periodic_defers
        SET job_id = (
            SELECT COALESCE((
                SELECT unnest(procrastinate_defer_jobs_v1(
                    ARRAY[
                        ROW(
                            _queue_name,
                            _task_name,
                            _priority,
                            _lock,
                            _queueing_lock,
                            _args,
                            NULL::timestamptz
                        )
                    ]::procrastinate_job_to_defer_v1[]
                ))
            ), NULL)
        )
        WHERE id = _defer_id
        RETURNING job_id INTO _job_id;

    DELETE
        FROM procrastinate_periodic_defers
        USING (
            SELECT id
            FROM procrastinate_periodic_defers
            WHERE procrastinate_periodic_defers.task_name = _task_name
            AND procrastinate_periodic_defers.periodic_id = _periodic_id
            AND procrastinate_periodic_defers.defer_timestamp < _defer_timestamp
            ORDER BY id
            FOR UPDATE
        ) to_delete
        WHERE procrastinate_periodic_defers.id = to_delete.id;

    RETURN _job_id;
END;
$$;

CREATE FUNCTION procrastinate_fetch_job_v2(
    target_queue_names character varying[],
    p_worker_id bigint
)
    RETURNS procrastinate_jobs
    LANGUAGE plpgsql
AS $$
DECLARE
	found_jobs procrastinate_jobs;
BEGIN
    WITH candidate AS (
        SELECT jobs.*
            FROM procrastinate_jobs AS jobs
            WHERE
                -- reject the job if its lock has earlier or higher priority jobs
                NOT EXISTS (
                    SELECT 1
                        FROM procrastinate_jobs AS other_jobs
                        WHERE
                            jobs.lock IS NOT NULL
                            AND other_jobs.lock = jobs.lock
                            AND (
                                -- job with same lock is already running
                                other_jobs.status = 'doing'
                                OR
                                -- job with same lock is waiting and has higher priority (or same priority but was queued first)
                                (
                                    other_jobs.status = 'todo'
                                    AND (
                                        other_jobs.priority > jobs.priority
                                        OR (
                                        other_jobs.priority = jobs.priority
                                        AND other_jobs.id < jobs.id
                                        )
                                    )
                                )
                            )
                )
                AND jobs.status = 'todo'
                AND (target_queue_names IS NULL OR jobs.queue_name = ANY( target_queue_names ))
                AND (jobs.scheduled_at IS NULL OR jobs.scheduled_at <= now())
            ORDER BY jobs.priority DESC, jobs.id ASC LIMIT 1
            FOR UPDATE OF jobs SKIP LOCKED
    )
    UPDATE procrastinate_jobs
        SET status = 'doing', worker_id = p_worker_id
        FROM candidate
        WHERE procrastinate_jobs.id = candidate.id
        RETURNING procrastinate_jobs.* INTO found_jobs;

 RETURN found_jobs;
END;
$$;

CREATE FUNCTION procrastinate_finish_job_v1(job_id bigint, end_status procrastinate_job_status, delete_job boolean)
    RETURNS void
    LANGUAGE plpgsql
AS $$
DECLARE
    _job_id bigint;
BEGIN
    IF end_status NOT IN ('succeeded', 'failed', 'aborted') THEN
        RAISE 'End status should be either "succeeded", "failed" or "aborted" (job id: %)', job_id;
    END IF;
    IF delete_job THEN
        DELETE FROM procrastinate_jobs
        WHERE id = job_id AND status IN ('todo', 'doing')
        RETURNING id INTO _job_id;
    ELSE
        UPDATE procrastinate_jobs
        SET status = end_status,
            abort_requested = false,
            attempts = CASE status
                WHEN 'doing' THEN attempts + 1 ELSE attempts
            END
        WHERE id = job_id AND status IN ('todo', 'doing')
        RETURNING id INTO _job_id;
    END IF;
    IF _job_id IS NULL THEN
        RAISE 'Job was not found or not in "doing" or "todo" status (job id: %)', job_id;
    END IF;
END;
$$;

CREATE FUNCTION procrastinate_cancel_job_v1(job_id bigint, abort boolean, delete_job boolean)
    RETURNS bigint
    LANGUAGE plpgsql
AS $$
DECLARE
    _job_id bigint;
BEGIN
    IF delete_job THEN
        DELETE FROM procrastinate_jobs
        WHERE id = job_id AND status = 'todo'
        RETURNING id INTO _job_id;
    END IF;
    IF _job_id IS NULL THEN
        IF abort THEN
            UPDATE procrastinate_jobs
            SET abort_requested = true,
                status = CASE status
                    WHEN 'todo' THEN 'cancelled'::procrastinate_job_status ELSE status
                END
            WHERE id = job_id AND status IN ('todo', 'doing')
            RETURNING id INTO _job_id;
        ELSE
            UPDATE procrastinate_jobs
            SET status = 'cancelled'::procrastinate_job_status
            WHERE id = job_id AND status = 'todo'
            RETURNING id INTO _job_id;
        END IF;
    END IF;
    RETURN _job_id;
END;
$$;

CREATE FUNCTION procrastinate_retry_job_v1(
    job_id bigint,
    retry_at timestamp with time zone,
    new_priority integer,
    new_queue_name character varying,
    new_lock character varying
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    _job_id bigint;
    _abort_requested boolean;
BEGIN
    SELECT abort_requested FROM procrastinate_jobs
    WHERE id = job_id AND status = 'doing'
    FOR UPDATE
    INTO _abort_requested;
    IF _abort_requested THEN
        UPDATE procrastinate_jobs
        SET status = 'failed'::procrastinate_job_status
        WHERE id = job_id AND status = 'doing'
        RETURNING id INTO _job_id;
    ELSE
        UPDATE procrastinate_jobs
        SET status = 'todo'::procrastinate_job_status,
            attempts = attempts + 1,
            scheduled_at = retry_at,
            priority = COALESCE(new_priority, priority),
            queue_name = COALESCE(new_queue_name, queue_name),
            lock = COALESCE(new_lock, lock)
        WHERE id = job_id AND status = 'doing'
        RETURNING id INTO _job_id;
    END IF;

    IF _job_id IS NULL THEN
        RAISE 'Job was not found or not in "doing" status (job id: %)', job_id;
    END IF;
END;
$$;

CREATE FUNCTION procrastinate_retry_job_v2(
    job_id bigint,
    retry_at timestamp with time zone,
    new_priority integer,
    new_queue_name character varying,
    new_lock character varying
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    _job_id bigint;
    _abort_requested boolean;
    _current_status procrastinate_job_status;
BEGIN
    SELECT status, abort_requested FROM procrastinate_jobs
    WHERE id = job_id AND status IN ('doing', 'failed')
    FOR UPDATE
    INTO _current_status, _abort_requested;
    IF _current_status = 'doing' AND _abort_requested THEN
        UPDATE procrastinate_jobs
        SET status = 'failed'::procrastinate_job_status
        WHERE id = job_id AND status = 'doing'
        RETURNING id INTO _job_id;
    ELSE
        UPDATE procrastinate_jobs
        SET status = 'todo'::procrastinate_job_status,
            attempts = attempts + 1,
            scheduled_at = retry_at,
            priority = COALESCE(new_priority, priority),
            queue_name = COALESCE(new_queue_name, queue_name),
            lock = COALESCE(new_lock, lock)
        WHERE id = job_id AND status IN ('doing', 'failed')
        RETURNING id INTO _job_id;
    END IF;

    IF _job_id IS NULL THEN
        RAISE 'Job was not found or has an invalid status to retry (job id: %)', job_id;
    END IF;

END;
$$;

CREATE FUNCTION procrastinate_notify_queue_job_inserted_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
DECLARE
    payload TEXT;
BEGIN
    SELECT json_build_object('type', 'job_inserted', 'job_id', NEW.id)::text INTO payload;
	PERFORM pg_notify('procrastinate_queue_v1#' || NEW.queue_name, payload);
	PERFORM pg_notify('procrastinate_any_queue_v1', payload);
	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_notify_queue_abort_job_v1()
RETURNS trigger
    LANGUAGE plpgsql
AS $$
DECLARE
    payload TEXT;
BEGIN
    SELECT json_build_object('type', 'abort_job_requested', 'job_id', NEW.id)::text INTO payload;
	PERFORM pg_notify('procrastinate_queue_v1#' || NEW.queue_name, payload);
	PERFORM pg_notify('procrastinate_any_queue_v1', payload);
	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_trigger_function_status_events_insert_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO procrastinate_events(job_id, type)
        VALUES (NEW.id, 'deferred'::procrastinate_job_event_type);
	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_trigger_function_status_events_update_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    WITH t AS (
        SELECT CASE
            WHEN OLD.status = 'todo'::procrastinate_job_status
                AND NEW.status = 'doing'::procrastinate_job_status
                THEN 'started'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'todo'::procrastinate_job_status
                THEN 'deferred_for_retry'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'failed'::procrastinate_job_status
                THEN 'failed'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'succeeded'::procrastinate_job_status
                THEN 'succeeded'::procrastinate_job_event_type
            WHEN OLD.status = 'todo'::procrastinate_job_status
                AND (
                    NEW.status = 'cancelled'::procrastinate_job_status
                    OR NEW.status = 'failed'::procrastinate_job_status
                    OR NEW.status = 'succeeded'::procrastinate_job_status
                )
                THEN 'cancelled'::procrastinate_job_event_type
            WHEN OLD.status = 'doing'::procrastinate_job_status
                AND NEW.status = 'aborted'::procrastinate_job_status
                THEN 'aborted'::procrastinate_job_event_type
            WHEN OLD.status = 'failed'::procrastinate_job_status
                AND NEW.status = 'todo'::procrastinate_job_status
                THEN 'retried'::procrastinate_job_event_type
            ELSE NULL
        END as event_type
    )
    INSERT INTO procrastinate_events(job_id, type)
        SELECT NEW.id, t.event_type
        FROM t
        WHERE t.event_type IS NOT NULL;
	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_trigger_function_scheduled_events_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO procrastinate_events(job_id, type, at)
        VALUES (NEW.id, 'scheduled'::procrastinate_job_event_type, NEW.scheduled_at);

	RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_trigger_abort_requested_events_procedure_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO procrastinate_events(job_id, type)
        VALUES (NEW.id, 'abort_requested'::procrastinate_job_event_type);
    RETURN NEW;
END;
$$;

CREATE FUNCTION procrastinate_unlink_periodic_defers_v1()
    RETURNS trigger
    LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE procrastinate_periodic_defers
    SET job_id = NULL
    WHERE job_id = OLD.id;
    RETURN OLD;
END;
$$;

CREATE FUNCTION procrastinate_register_worker_v1()
    RETURNS TABLE(worker_id bigint)
    LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    INSERT INTO procrastinate_workers DEFAULT VALUES
    RETURNING procrastinate_workers.id;
END;
$$;

CREATE FUNCTION procrastinate_unregister_worker_v1(worker_id bigint)
    RETURNS void
    LANGUAGE plpgsql
AS $$
BEGIN
    DELETE FROM procrastinate_workers
    WHERE id = worker_id;
END;
$$;

CREATE FUNCTION procrastinate_update_heartbeat_v1(worker_id bigint)
    RETURNS void
    LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE procrastinate_workers
    SET last_heartbeat = NOW()
    WHERE id = worker_id;
END;
$$;

CREATE FUNCTION procrastinate_prune_stalled_workers_v1(seconds_since_heartbeat float)
    RETURNS TABLE(worker_id bigint)
    LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    DELETE FROM procrastinate_workers
    WHERE last_heartbeat < NOW() - (seconds_since_heartbeat || 'SECOND')::INTERVAL
    RETURNING procrastinate_workers.id;
END;
$$;

-- Triggers

CREATE TRIGGER procrastinate_jobs_notify_queue_job_inserted_v1
    AFTER INSERT ON procrastinate_jobs
    FOR EACH ROW WHEN ((new.status = 'todo'::procrastinate_job_status))
    EXECUTE PROCEDURE procrastinate_notify_queue_job_inserted_v1();

CREATE TRIGGER procrastinate_jobs_notify_queue_job_aborted_v1
    AFTER UPDATE OF abort_requested ON procrastinate_jobs
    FOR EACH ROW WHEN ((old.abort_requested = false AND new.abort_requested = true AND new.status = 'doing'::procrastinate_job_status))
    EXECUTE PROCEDURE procrastinate_notify_queue_abort_job_v1();

CREATE TRIGGER procrastinate_trigger_status_events_update_v1
    AFTER UPDATE OF status ON procrastinate_jobs
    FOR EACH ROW
    EXECUTE PROCEDURE procrastinate_trigger_function_status_events_update_v1();

CREATE TRIGGER procrastinate_trigger_status_events_insert_v1
    AFTER INSERT ON procrastinate_jobs
    FOR EACH ROW WHEN ((new.status = 'todo'::procrastinate_job_status))
    EXECUTE PROCEDURE procrastinate_trigger_function_status_events_insert_v1();

CREATE TRIGGER procrastinate_trigger_scheduled_events_v1
    AFTER UPDATE OR INSERT ON procrastinate_jobs
    FOR EACH ROW WHEN ((new.scheduled_at IS NOT NULL AND new.status = 'todo'::procrastinate_job_status))
    EXECUTE PROCEDURE procrastinate_trigger_function_scheduled_events_v1();

CREATE TRIGGER procrastinate_trigger_abort_requested_events_v1
    AFTER UPDATE OF abort_requested ON procrastinate_jobs
    FOR EACH ROW WHEN ((new.abort_requested = true))
    EXECUTE PROCEDURE procrastinate_trigger_abort_requested_events_procedure_v1();

CREATE TRIGGER procrastinate_trigger_delete_jobs_v1
    BEFORE DELETE ON procrastinate_jobs
    FOR EACH ROW EXECUTE PROCEDURE procrastinate_unlink_periodic_defers_v1();
"""


RUNNER_TEARDOWN = """\
-- Tables first: dropping a table takes its triggers, indexes and
-- the implicit sequences behind its bigserial columns with it.
DROP TABLE IF EXISTS procrastinate_events CASCADE;
DROP TABLE IF EXISTS procrastinate_jobs CASCADE;
DROP TABLE IF EXISTS procrastinate_periodic_defers CASCADE;
DROP TABLE IF EXISTS procrastinate_workers CASCADE;

-- Then the functions the triggers called.
DROP FUNCTION IF EXISTS procrastinate_cancel_job_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_defer_jobs_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_defer_periodic_job_v2 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_fetch_job_v2 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_finish_job_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_notify_queue_abort_job_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_notify_queue_job_inserted_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_prune_stalled_workers_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_register_worker_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_retry_job_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_retry_job_v2 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_trigger_abort_requested_events_procedure_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_trigger_function_scheduled_events_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_trigger_function_status_events_insert_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_trigger_function_status_events_update_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_unlink_periodic_defers_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_unregister_worker_v1 CASCADE;
DROP FUNCTION IF EXISTS procrastinate_update_heartbeat_v1 CASCADE;

-- Then the enum and composite types the tables and functions used.
DROP TYPE IF EXISTS procrastinate_job_event_type CASCADE;
DROP TYPE IF EXISTS procrastinate_job_status CASCADE;
DROP TYPE IF EXISTS procrastinate_job_to_defer_v1 CASCADE;
"""


def _execute_script(script: str) -> None:
    """Run a multi-statement script, including `$$`-quoted function bodies.

    Not `op.execute` and not `exec_driver_sql`: both are SQLAlchemy
    `Connection` methods that route through dialect execution and therefore
    through asyncpg's prepared-statement path, which rejects multi-statement
    SQL. The escape is asyncpg's own `Connection.execute`, reached from the
    raw driver connection beneath the bind -- and because a migration body
    runs synchronously inside `connection.run_sync(...)`, awaiting it needs
    the greenlet bridge. See design.md for why the alternative -- splitting
    the script on `$$`-aware boundaries -- is the fragile branch and not the
    first attempt.
    """
    bind = op.get_bind()
    driver_connection = bind.connection.driver_connection
    if driver_connection is None:  # pragma: no cover -- offline/--sql mode
        op.execute(sa.text(script))
        return
    util.await_only(driver_connection.execute(script))


def upgrade() -> None:
    _execute_script(RUNNER_SCHEMA)


def downgrade() -> None:
    # The runner ships no teardown script, so every object class it creates is
    # enumerated by hand: four tables, eighteen functions and three types.
    # Triggers and indexes fall with their tables; the bigserial sequences are
    # owned by their columns and fall with them too. tasks.md 1.5 checks this
    # against `pg_class`, `pg_type` and `pg_proc` rather than a table listing,
    # because a missed function or enum type is invisible to `\dt`.
    _execute_script(RUNNER_TEARDOWN)
