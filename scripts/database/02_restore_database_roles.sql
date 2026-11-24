\set ON_ERROR_STOP on
-- DATABASE-SPECIFIC: connect to inventory_aios_restore_check as a reviewed superuser.
-- The separate 02_transfer_database_owner.ps1 stage sets database owner to inventory_aios_owner.
-- This script handles database-local schema/object ownership and least-privilege grants.
DO $guard$
BEGIN
    IF current_database() <> 'inventory_aios_restore_check' THEN
        RAISE EXCEPTION 'Wrong database: expected inventory_aios_restore_check, got %', current_database();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'inventory_aios_owner' AND NOT rolcanlogin) THEN
        RAISE EXCEPTION 'inventory_aios_owner must exist and be NOLOGIN';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'inventory_aios_migrator' AND rolcanlogin) THEN
        RAISE EXCEPTION 'inventory_aios_migrator must exist and be LOGIN';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'inventory_aios_app' AND rolcanlogin) THEN
        RAISE EXCEPTION 'The existing inventory_aios_app LOGIN role is required';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = current_user AND rolsuper) THEN
        RAISE EXCEPTION 'A reviewed superuser administrator is required for ownership transfer';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles r ON r.oid=m.member
        WHERE r.rolname='inventory_aios_app'
    ) THEN
        RAISE EXCEPTION 'inventory_aios_app has inherited role memberships; review and remove excess access before rehearsal';
    END IF;
    IF (SELECT version_num FROM public.alembic_version) <> '36368303c6c6'
       OR (SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname='public') <> 12
       OR (SELECT count(*) FROM pg_catalog.pg_constraint WHERE connamespace='public'::regnamespace AND contype IN ('p','f','u')) <> 36
       OR (SELECT count(*) FROM pg_catalog.pg_constraint WHERE connamespace='public'::regnamespace AND contype='c') <> 3
       OR (SELECT count(*) FROM pg_catalog.pg_constraint WHERE connamespace='public'::regnamespace AND contype='n') <> 67
       OR (SELECT count(*) FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind='f') <> 2
       OR (SELECT count(*) FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class x ON x.oid=i.indexrelid JOIN pg_catalog.pg_namespace n ON n.oid=x.relnamespace WHERE n.nspname='public' AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint c WHERE c.conindid=i.indexrelid)) <> 8
       OR (SELECT count(*) FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal) <> 11 THEN
        RAISE EXCEPTION 'Restore baseline does not match expected revision/object counts; no role grants or ownership changed';
    END IF;
END
$guard$;

BEGIN;
SET LOCAL search_path TO pg_catalog, public;
REVOKE CONNECT, CREATE, TEMPORARY ON DATABASE inventory_aios_restore_check FROM PUBLIC, inventory_aios_app;
GRANT CONNECT ON DATABASE inventory_aios_restore_check TO inventory_aios_app, inventory_aios_migrator;

ALTER SCHEMA public OWNER TO inventory_aios_owner;
REVOKE ALL ON SCHEMA public FROM PUBLIC, inventory_aios_app;
GRANT USAGE ON SCHEMA public TO inventory_aios_app;

DO $owners$
DECLARE
    obj record;
    alter_verb text;
BEGIN
    FOR obj IN
        SELECT n.nspname, c.relname, c.relkind
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relkind IN ('r','p','v','m','S','f')
          AND c.relowner <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'inventory_aios_owner')
          AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype = 'e')
    LOOP
        alter_verb := CASE obj.relkind WHEN 'S' THEN 'ALTER SEQUENCE' WHEN 'v' THEN 'ALTER VIEW' WHEN 'm' THEN 'ALTER MATERIALIZED VIEW' WHEN 'f' THEN 'ALTER FOREIGN TABLE' ELSE 'ALTER TABLE' END;
        EXECUTE format('%s %I.%I OWNER TO inventory_aios_owner', alter_verb, obj.nspname, obj.relname);
    END LOOP;
    FOR obj IN
        SELECT n.nspname, p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid) AS args, p.prokind
        FROM pg_catalog.pg_proc p
        JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND p.prokind IN ('f','p')
          AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e')
          AND p.proowner <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'inventory_aios_owner')
    LOOP
        IF obj.prokind = 'p' THEN
            EXECUTE format('ALTER PROCEDURE %I.%I(%s) OWNER TO inventory_aios_owner', obj.nspname, obj.proname, obj.args);
        ELSE
            EXECUTE format('ALTER FUNCTION %I.%I(%s) OWNER TO inventory_aios_owner', obj.nspname, obj.proname, obj.args);
        END IF;
    END LOOP;
    FOR obj IN
        SELECT n.nspname, t.typname
        FROM pg_catalog.pg_type t
        JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace
        WHERE n.nspname = 'public' AND t.typtype IN ('e','d','r','m')
          AND t.typowner <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname = 'inventory_aios_owner')
          AND t.typrelid = 0
          AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid = 'pg_type'::regclass AND d.objid = t.oid AND d.deptype = 'e')
    LOOP
        EXECUTE format('ALTER TYPE %I.%I OWNER TO inventory_aios_owner', obj.nspname, obj.typname);
    END LOOP;
END
$owners$;

-- Remove inherited PUBLIC/application grants, then grant only active workflow access.
REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM PUBLIC, inventory_aios_app;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM PUBLIC, inventory_aios_app;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC, inventory_aios_app;
GRANT SELECT ON TABLE public.employees, public.users, public.roles, public.user_roles TO inventory_aios_app;

-- employee_history has no runtime DML grant while registration remains disabled.
-- If approved registration later needs INSERT, grant it in a separately reviewed migration;
-- never grant UPDATE, DELETE, TRUNCATE, TRIGGER, ownership, or schema CREATE to runtime.

ALTER DEFAULT PRIVILEGES FOR ROLE inventory_aios_owner
    REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE inventory_aios_owner IN SCHEMA public
    REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE inventory_aios_owner IN SCHEMA public
    REVOKE ALL ON SEQUENCES FROM PUBLIC;

-- audit_events is not in the restored revision yet. When the pending audit migration has
-- been separately approved/applied, runtime needs validator EXECUTE for its CHECK constraint.
DO $audit$
BEGIN
    IF to_regprocedure('public.inventory_aios_audit_metadata_is_valid(jsonb)') IS NOT NULL THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION public.inventory_aios_audit_metadata_is_valid(jsonb) TO inventory_aios_app';
    END IF;
END
$audit$;
COMMIT;
