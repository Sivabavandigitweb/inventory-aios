\set ON_ERROR_STOP on
-- Run only after the separately approved audit migration, connected as an administrator.
BEGIN;
DO $guard$
BEGIN
    IF current_database() <> 'inventory_aios_restore_check' THEN
        RAISE EXCEPTION 'Wrong database: expected inventory_aios_restore_check, got %', current_database();
    END IF;
    IF to_regprocedure('public.inventory_aios_audit_metadata_is_valid(jsonb)') IS NULL THEN
        RAISE EXCEPTION 'Audit metadata validator is missing; apply no grants';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=current_user AND rolsuper) THEN
        RAISE EXCEPTION 'Administrator privileges are required';
    END IF;
END
$guard$;
GRANT EXECUTE ON FUNCTION public.inventory_aios_audit_metadata_is_valid(jsonb) TO inventory_aios_app;
DO $verify$
BEGIN
    IF NOT has_function_privilege('inventory_aios_app', 'public.inventory_aios_audit_metadata_is_valid(jsonb)', 'EXECUTE') THEN
        RAISE EXCEPTION 'Runtime cannot execute the audit metadata validator';
    END IF;
END
$verify$;
COMMIT;
