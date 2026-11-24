\set ON_ERROR_STOP on
-- CLUSTER-WIDE: run connected to the maintenance database as a PostgreSQL administrator.
BEGIN;
DO $guard$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'inventory_aios_app') THEN
        RAISE EXCEPTION 'inventory_aios_app is missing; do not create it in this script';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname IN ('inventory_aios_owner','inventory_aios_migrator')) THEN
        RAISE EXCEPTION 'Role-name conflict: inspect existing owner/migrator roles and memberships; no role was changed';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = current_user AND rolsuper
    ) THEN
        RAISE EXCEPTION 'A superuser administrator is required for reviewed cluster role setup';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname = 'inventory_aios_app'
          AND (NOT rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)
    ) THEN
        RAISE EXCEPTION 'Existing inventory_aios_app has unexpected role attributes; review it before proceeding';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles r ON r.oid = m.member
        WHERE r.rolname = 'inventory_aios_app'
    ) THEN
        RAISE EXCEPTION 'inventory_aios_app has role memberships; review inherited privileges before proceeding';
    END IF;
END
$guard$;
CREATE ROLE inventory_aios_owner
    NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT;
CREATE ROLE inventory_aios_migrator
    LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
GRANT inventory_aios_owner TO inventory_aios_migrator WITH INHERIT FALSE, SET TRUE;
COMMIT;
-- Set the migrator password interactively after this transaction using psql's \password command.
