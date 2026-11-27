\set ON_ERROR_STOP on
-- PREPARED ONLY. Do not execute without separate database-grant approval.
-- This is an additive, transactional grant set for the verified d2a8f4c1b790
-- restore-check schema. It never changes PUBLIC or baseline employee/identity ACLs.
-- If execution is interrupted, PostgreSQL rolls back this transaction; verify
-- the identity/revision and rerun this idempotent grant script. To undo a
-- committed grant set, use 10_revoke_operational_runtime_grants.sql.
BEGIN;
SET LOCAL ROLE inventory_aios_owner;

DO $guard$
BEGIN
    IF current_database() <> 'inventory_aios_restore_check'
       OR session_user <> 'inventory_aios_migrator'
       OR current_user <> 'inventory_aios_owner'
       OR (SELECT version_num FROM public.alembic_version) <> 'd2a8f4c1b790' THEN
        RAISE EXCEPTION 'Unexpected database, migration identity, or schema revision';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='inventory_aios_owner' AND NOT rolcanlogin)
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='inventory_aios_migrator' AND rolcanlogin AND NOT rolsuper)
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='inventory_aios_app' AND rolcanlogin AND NOT rolsuper)
       OR (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()) <> 'inventory_aios_owner'
       OR NOT EXISTS (
            SELECT 1 FROM pg_auth_members m
            WHERE m.roleid=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_owner')
              AND m.member=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_migrator')
              AND m.set_option AND NOT m.inherit_option AND NOT m.admin_option
       )
       OR EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_app'))
       OR pg_has_role('inventory_aios_app','inventory_aios_owner','MEMBER')
       OR pg_has_role('inventory_aios_app','inventory_aios_migrator','MEMBER')
       OR NOT has_database_privilege('inventory_aios_app',current_database(),'CONNECT')
       OR NOT has_schema_privilege('inventory_aios_app','public','USAGE')
       OR NOT has_table_privilege('inventory_aios_app','public.users','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.roles','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.user_roles','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.employees','SELECT')
       OR has_database_privilege('inventory_aios_app',current_database(),'CREATE')
       OR has_schema_privilege('inventory_aios_app','public','CREATE') THEN
        RAISE EXCEPTION 'Runtime role separation is invalid';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_app')
    ) OR EXISTS (
        SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
        WHERE n.nspname='public' AND p.proowner=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_app')
    ) THEN
        RAISE EXCEPTION 'Runtime role owns application objects';
    END IF;
    IF EXISTS (
        SELECT 1 FROM unnest(ARRAY[
            'inventory_products','receipts','receipt_lines','tracked_assets',
            'quantity_inventory_lots','inventory_balances','inventory_movements',
            'asset_registration_events','asset_registration_requests',
            'quantity_registration_requests','allocations','allocation_lines',
            'inventory_returns','asset_repairs','disposal_requests',
            'employee_exit_clearances','workflow_approvals',
            'quantity_disposition_requests','idempotency_requests',
            'user_password_credentials','auth_sessions','auth_login_attempt_buckets','audit_events'
        ]) AS required(table_name)
        WHERE to_regclass('public.' || required.table_name) IS NULL
    ) THEN
        RAISE EXCEPTION 'A required application table is missing';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_class c
        JOIN pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN LATERAL aclexplode(COALESCE(c.relacl, acldefault('r', c.relowner))) acl
        WHERE n.nspname='public'
          AND c.relname = ANY (ARRAY[
            'asset_categories','suppliers','locations','inventory_products','receipts',
            'receipt_lines','tracked_assets','quantity_inventory_lots','inventory_balances',
            'inventory_movements','asset_registration_events','asset_registration_requests',
            'quantity_registration_requests','allocations','allocation_lines','inventory_returns',
            'asset_repairs','disposal_requests','employee_exit_clearances','workflow_approvals',
            'quantity_disposition_requests','idempotency_requests','user_password_credentials',
            'auth_sessions','auth_login_attempt_buckets','audit_events'
          ])
          AND acl.grantee=0
    ) THEN
        RAISE EXCEPTION 'PUBLIC has grants on operational tables; review ACLs before rehearsal';
    END IF;
END
$guard$;

-- Existing CONNECT and schema USAGE are verified prerequisites. This script
-- intentionally does not re-grant them, so revocation preserves the baseline.

-- Preserve existing identity/employee read permissions; the guard above
-- requires them and neither this script nor its revocation changes them.

-- Only the inventory records required by protected operational APIs.
GRANT SELECT ON TABLE public.asset_categories, public.suppliers, public.locations
    TO inventory_aios_app;
DO $inventory_grants$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'inventory_products','receipts',
        'receipt_lines','tracked_assets','quantity_inventory_lots',
        'inventory_balances',
        'asset_registration_requests','quantity_registration_requests',
        'allocations','allocation_lines','inventory_returns','asset_repairs',
        'disposal_requests','employee_exit_clearances','workflow_approvals',
        'quantity_disposition_requests','idempotency_requests'
    ] LOOP
        EXECUTE format('GRANT SELECT, INSERT, UPDATE ON TABLE public.%I TO inventory_aios_app', table_name);
    END LOOP;
    EXECUTE 'GRANT SELECT, INSERT ON TABLE public.inventory_movements, public.asset_registration_events TO inventory_aios_app';
END
$inventory_grants$;

-- Password credentials are read-only to the app. Sessions may be inserted,
-- validated, activity-updated, and individually revoked; never deleted.
-- Runtime authentication is column-scoped. Credential rows are read-only;
-- session updates are limited to activity/revocation; attempt keys cannot change.
GRANT SELECT (user_id, password_hash, credential_version)
    ON TABLE public.user_password_credentials TO inventory_aios_app;
GRANT SELECT (id, user_id, token_hash, credential_version, created_at, last_seen_at, expires_at, revoked_at)
    ON TABLE public.auth_sessions TO inventory_aios_app;
GRANT INSERT (id, user_id, token_hash, credential_version, created_at, last_seen_at, expires_at)
    ON TABLE public.auth_sessions TO inventory_aios_app;
GRANT UPDATE (last_seen_at, revoked_at)
    ON TABLE public.auth_sessions TO inventory_aios_app;
GRANT SELECT ON TABLE public.auth_login_attempt_buckets TO inventory_aios_app;
GRANT INSERT (scope, key_digest, window_started_at, failures, in_flight, updated_at)
    ON TABLE public.auth_login_attempt_buckets TO inventory_aios_app;
GRANT UPDATE (window_started_at, failures, in_flight, blocked_until, updated_at)
    ON TABLE public.auth_login_attempt_buckets TO inventory_aios_app;
GRANT EXECUTE ON FUNCTION public.inventory_aios_cleanup_login_attempts(integer, integer) TO inventory_aios_app;

-- Audit is append-only from the runtime. No audit reads or mutation rights.
GRANT INSERT (id, actor_user_id, action, entity_type, entity_id, change_source,
    metadata, previous_values, updated_values) ON TABLE public.audit_events TO inventory_aios_app;
GRANT SELECT (id, occurred_at) ON TABLE public.audit_events TO inventory_aios_app;
GRANT EXECUTE ON FUNCTION public.inventory_aios_audit_metadata_is_valid(jsonb) TO inventory_aios_app;
GRANT EXECUTE ON FUNCTION public.inventory_aios_audit_values_are_valid(jsonb) TO inventory_aios_app;

DO $verify$
BEGIN
    IF current_database() <> 'inventory_aios_restore_check'
       OR session_user <> 'inventory_aios_migrator'
       OR current_user <> 'inventory_aios_owner'
       OR (SELECT version_num FROM public.alembic_version) <> 'd2a8f4c1b790'
       OR (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()) <> 'inventory_aios_owner'
       OR EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_app'))
       OR EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relowner=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_app'))
       OR has_database_privilege('inventory_aios_app', current_database(), 'CREATE')
       OR has_schema_privilege('inventory_aios_app', 'public', 'CREATE')
       OR NOT has_database_privilege('inventory_aios_app',current_database(),'CONNECT')
       OR NOT has_schema_privilege('inventory_aios_app','public','USAGE')
       OR pg_has_role('inventory_aios_app','inventory_aios_owner','MEMBER')
       OR pg_has_role('inventory_aios_app','inventory_aios_migrator','MEMBER') THEN
        RAISE EXCEPTION 'Operational runtime privilege verification failed';
    END IF;
    IF has_table_privilege('inventory_aios_app','public.audit_events','SELECT')
       OR has_table_privilege('inventory_aios_app','public.audit_events','UPDATE')
       OR has_table_privilege('inventory_aios_app','public.audit_events','DELETE')
       OR has_table_privilege('inventory_aios_app','public.audit_events','TRUNCATE')
       OR has_table_privilege('inventory_aios_app','public.employee_history','UPDATE')
       OR has_table_privilege('inventory_aios_app','public.employee_history','DELETE')
       OR has_table_privilege('inventory_aios_app','public.employee_history','TRUNCATE')
       OR has_table_privilege('inventory_aios_app','public.auth_sessions','DELETE')
       OR has_table_privilege('inventory_aios_app','public.auth_login_attempt_buckets','DELETE')
       OR has_table_privilege('inventory_aios_app','public.auth_login_attempt_buckets','TRUNCATE')
       OR has_table_privilege('inventory_aios_app','public.user_password_credentials','UPDATE') THEN
        RAISE EXCEPTION 'Runtime received a prohibited mutation privilege';
    END IF;
    IF has_table_privilege('inventory_aios_app','public.inventory_movements','UPDATE')
       OR has_table_privilege('inventory_aios_app','public.inventory_movements','DELETE')
       OR has_table_privilege('inventory_aios_app','public.asset_registration_events','UPDATE')
       OR has_table_privilege('inventory_aios_app','public.asset_registration_events','DELETE')
       OR has_table_privilege('inventory_aios_app','public.allocation_lines','DELETE')
       OR has_table_privilege('inventory_aios_app','public.workflow_approvals','DELETE')
       OR has_table_privilege('inventory_aios_app','public.asset_categories','INSERT')
       OR has_table_privilege('inventory_aios_app','public.asset_categories','UPDATE')
       OR has_table_privilege('inventory_aios_app','public.suppliers','INSERT')
       OR has_table_privilege('inventory_aios_app','public.suppliers','UPDATE')
       OR has_table_privilege('inventory_aios_app','public.locations','INSERT')
       OR has_table_privilege('inventory_aios_app','public.locations','UPDATE') THEN
        RAISE EXCEPTION 'Append-only or historical workflow records are mutable';
    END IF;
    IF NOT has_table_privilege('inventory_aios_app','public.auth_login_attempt_buckets','SELECT')
       OR NOT has_column_privilege('inventory_aios_app','public.user_password_credentials','user_id','SELECT')
       OR NOT has_column_privilege('inventory_aios_app','public.user_password_credentials','password_hash','SELECT')
       OR NOT has_column_privilege('inventory_aios_app','public.user_password_credentials','credential_version','SELECT')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_sessions','token_hash','SELECT')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_sessions','expires_at','SELECT')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_sessions','id','INSERT')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_sessions','user_id','INSERT')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_sessions','token_hash','INSERT')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','scope','INSERT')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','key_digest','INSERT')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','failures','UPDATE')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','in_flight','UPDATE')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','blocked_until','UPDATE')
       OR has_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','key_digest','UPDATE')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_sessions','last_seen_at','UPDATE')
       OR NOT has_column_privilege('inventory_aios_app','public.auth_sessions','revoked_at','UPDATE')
       OR has_column_privilege('inventory_aios_app','public.auth_sessions','token_hash','UPDATE')
       OR has_column_privilege('inventory_aios_app','public.user_password_credentials','password_hash','UPDATE')
       OR NOT has_column_privilege('inventory_aios_app','public.audit_events','id','SELECT')
       OR NOT has_column_privilege('inventory_aios_app','public.audit_events','occurred_at','SELECT')
       OR NOT has_column_privilege('inventory_aios_app','public.audit_events','metadata','INSERT')
       OR NOT has_column_privilege('inventory_aios_app','public.audit_events','action','INSERT')
       OR NOT has_column_privilege('inventory_aios_app','public.audit_events','actor_user_id','INSERT')
       OR NOT has_column_privilege('inventory_aios_app','public.audit_events','entity_id','INSERT')
       OR has_column_privilege('inventory_aios_app','public.audit_events','action','SELECT')
       OR has_table_privilege('inventory_aios_app','public.administrator_bootstrap_events','SELECT')
       OR NOT has_function_privilege('inventory_aios_app','public.inventory_aios_cleanup_login_attempts(integer,integer)','EXECUTE') THEN
        RAISE EXCEPTION 'Shared login-attempt repository privileges are incomplete';
    END IF;
END
$verify$;

COMMIT;
