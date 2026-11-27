\set ON_ERROR_STOP on
-- PREPARED ONLY. Run only after separate approval on inventory_aios_restore_check.
-- Connect as inventory_aios_migrator; this transaction assumes inventory_aios_owner.
SET ROLE inventory_aios_owner;
BEGIN;
DO $guard$
BEGIN
    IF current_database() <> 'inventory_aios_restore_check' THEN
        RAISE EXCEPTION 'Wrong database: authentication grants are rehearsal-only';
    END IF;
    IF session_user <> 'inventory_aios_migrator' OR current_user <> 'inventory_aios_owner' THEN
        RAISE EXCEPTION 'Expected migrator session assuming inventory_aios_owner';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'inventory_aios_owner' AND NOT rolcanlogin AND NOT rolsuper
          AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'inventory_aios_migrator' AND rolcanlogin AND NOT rolsuper
          AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls
    ) OR NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'inventory_aios_app' AND rolcanlogin AND NOT rolsuper
          AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls
    ) THEN
        RAISE EXCEPTION 'Database role attributes do not match the least-privilege contract';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM public.alembic_version WHERE version_num = 'b2d4f6a8c013') THEN
        RAISE EXCEPTION 'The approved final rehearsal schema b2d4f6a8c013 must be applied first';
    END IF;
    IF to_regclass('public.user_password_credentials') IS NULL
       OR to_regclass('public.auth_sessions') IS NULL THEN
        RAISE EXCEPTION 'Authentication tables are missing';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles r ON r.oid = m.member
        WHERE r.rolname = 'inventory_aios_app'
    ) THEN
        RAISE EXCEPTION 'Runtime role has memberships; review before granting authentication access';
    END IF;
END
$guard$;

-- Remove inherited object-level access to these new tables before granting only
-- repository operations. This does not grant password provisioning or reset rights.
REVOKE ALL PRIVILEGES ON TABLE public.user_password_credentials FROM PUBLIC, inventory_aios_app;
REVOKE ALL PRIVILEGES ON TABLE public.auth_sessions FROM PUBLIC, inventory_aios_app;

GRANT SELECT (user_id, password_hash, credential_version)
    ON TABLE public.user_password_credentials TO inventory_aios_app;
GRANT SELECT (id, user_id, token_hash, credential_version, created_at, last_seen_at, expires_at, revoked_at)
    ON TABLE public.auth_sessions TO inventory_aios_app;
GRANT INSERT (id, user_id, token_hash, credential_version, created_at, last_seen_at, expires_at)
    ON TABLE public.auth_sessions TO inventory_aios_app;
GRANT UPDATE (last_seen_at, revoked_at)
    ON TABLE public.auth_sessions TO inventory_aios_app;

COMMIT;
RESET ROLE;
