\set ON_ERROR_STOP on
-- PREPARED ONLY. Removes exactly privileges added by 09 and leaves all baseline
-- grants, PUBLIC ACLs, schema USAGE, and database CONNECT untouched.
-- The whole operation is transactional: interruption rolls it all back; rerun
-- after verifying the guarded identity/revision. Do not use DROP OWNED.
BEGIN;
SET LOCAL ROLE inventory_aios_owner;
DO $guard$
BEGIN
    IF current_database() <> 'inventory_aios_restore_check'
       OR session_user <> 'inventory_aios_migrator'
       OR current_user <> 'inventory_aios_owner'
       OR (SELECT version_num FROM public.alembic_version) <> 'd2a8f4c1b790'
       OR (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()) <> 'inventory_aios_owner'
       OR NOT EXISTS (
            SELECT 1 FROM pg_auth_members m
            WHERE m.roleid=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_owner')
              AND m.member=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_migrator')
              AND m.set_option AND NOT m.inherit_option AND NOT m.admin_option
       )
       OR EXISTS (SELECT 1 FROM pg_auth_members m WHERE m.member=(SELECT oid FROM pg_roles WHERE rolname='inventory_aios_app'))
       OR NOT has_database_privilege('inventory_aios_app',current_database(),'CONNECT')
       OR NOT has_schema_privilege('inventory_aios_app','public','USAGE') THEN
        RAISE EXCEPTION 'Unexpected database, migration identity, or schema revision';
    END IF;
END
$guard$;

REVOKE SELECT, INSERT, UPDATE ON TABLE
    public.inventory_products, public.receipts, public.receipt_lines,
    public.tracked_assets, public.quantity_inventory_lots, public.inventory_balances,
    public.asset_registration_requests, public.quantity_registration_requests,
    public.allocations, public.allocation_lines, public.inventory_returns,
    public.asset_repairs, public.disposal_requests, public.employee_exit_clearances,
    public.workflow_approvals, public.quantity_disposition_requests,
    public.idempotency_requests
FROM inventory_aios_app;
REVOKE SELECT, INSERT ON TABLE
    public.inventory_movements, public.asset_registration_events
FROM inventory_aios_app;
REVOKE SELECT ON TABLE public.asset_categories, public.suppliers, public.locations
FROM inventory_aios_app;

REVOKE SELECT (user_id, password_hash, credential_version)
    ON TABLE public.user_password_credentials FROM inventory_aios_app;
REVOKE SELECT (id, user_id, token_hash, credential_version, created_at, last_seen_at, expires_at, revoked_at)
    ON TABLE public.auth_sessions FROM inventory_aios_app;
REVOKE INSERT (id, user_id, token_hash, credential_version, created_at, last_seen_at, expires_at)
    ON TABLE public.auth_sessions FROM inventory_aios_app;
REVOKE UPDATE (last_seen_at, revoked_at)
    ON TABLE public.auth_sessions FROM inventory_aios_app;
REVOKE SELECT ON TABLE public.auth_login_attempt_buckets FROM inventory_aios_app;
REVOKE INSERT (scope, key_digest, window_started_at, failures, in_flight, updated_at)
    ON TABLE public.auth_login_attempt_buckets FROM inventory_aios_app;
REVOKE UPDATE (window_started_at, failures, in_flight, blocked_until, updated_at)
    ON TABLE public.auth_login_attempt_buckets FROM inventory_aios_app;
REVOKE EXECUTE ON FUNCTION public.inventory_aios_cleanup_login_attempts(integer, integer)
    FROM inventory_aios_app;

REVOKE INSERT (id, actor_user_id, action, entity_type, entity_id, change_source,
    metadata, previous_values, updated_values) ON TABLE public.audit_events FROM inventory_aios_app;
REVOKE SELECT (id, occurred_at) ON TABLE public.audit_events FROM inventory_aios_app;
REVOKE EXECUTE ON FUNCTION public.inventory_aios_audit_metadata_is_valid(jsonb) FROM inventory_aios_app;
REVOKE EXECUTE ON FUNCTION public.inventory_aios_audit_values_are_valid(jsonb) FROM inventory_aios_app;

DO $verify$
DECLARE
    table_name text;
BEGIN
    IF current_database() <> 'inventory_aios_restore_check'
       OR session_user <> 'inventory_aios_migrator'
       OR current_user <> 'inventory_aios_owner'
       OR (SELECT version_num FROM public.alembic_version) <> 'd2a8f4c1b790'
       OR has_schema_privilege('inventory_aios_app','public','CREATE')
       OR has_database_privilege('inventory_aios_app',current_database(),'CREATE')
       OR (SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname=current_database()) <> 'inventory_aios_owner'
       OR NOT has_database_privilege('inventory_aios_app',current_database(),'CONNECT')
       OR NOT has_schema_privilege('inventory_aios_app','public','USAGE')
       OR pg_has_role('inventory_aios_app','inventory_aios_owner','MEMBER')
       OR pg_has_role('inventory_aios_app','inventory_aios_migrator','MEMBER') THEN
        RAISE EXCEPTION 'Runtime privilege revocation did not preserve the guarded baseline';
    END IF;
    IF NOT has_table_privilege('inventory_aios_app','public.users','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.roles','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.user_roles','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.employees','SELECT') THEN
        RAISE EXCEPTION 'Baseline identity/employee read privileges changed';
    END IF;
    IF has_table_privilege('inventory_aios_app','public.auth_sessions','SELECT')
       OR has_table_privilege('inventory_aios_app','public.auth_sessions','INSERT')
       OR has_table_privilege('inventory_aios_app','public.auth_sessions','UPDATE')
       OR has_column_privilege('inventory_aios_app','public.user_password_credentials','password_hash','SELECT')
       OR has_column_privilege('inventory_aios_app','public.user_password_credentials','credential_version','SELECT')
       OR has_column_privilege('inventory_aios_app','public.auth_sessions','token_hash','SELECT')
       OR has_column_privilege('inventory_aios_app','public.auth_sessions','token_hash','INSERT')
       OR has_column_privilege('inventory_aios_app','public.auth_sessions','last_seen_at','UPDATE')
       OR has_column_privilege('inventory_aios_app','public.auth_sessions','revoked_at','UPDATE')
       OR has_table_privilege('inventory_aios_app','public.auth_login_attempt_buckets','SELECT')
       OR has_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','key_digest','INSERT')
       OR has_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','failures','UPDATE')
       OR has_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','blocked_until','UPDATE')
       OR has_table_privilege('inventory_aios_app','public.audit_events','INSERT')
       OR has_column_privilege('inventory_aios_app','public.audit_events','action','INSERT')
       OR has_column_privilege('inventory_aios_app','public.audit_events','actor_user_id','INSERT')
       OR has_column_privilege('inventory_aios_app','public.audit_events','entity_id','INSERT')
       OR has_column_privilege('inventory_aios_app','public.audit_events','metadata','INSERT')
       OR has_function_privilege('inventory_aios_app','public.inventory_aios_cleanup_login_attempts(integer,integer)','EXECUTE')
       OR has_function_privilege('inventory_aios_app','public.inventory_aios_audit_metadata_is_valid(jsonb)','EXECUTE')
       OR has_function_privilege('inventory_aios_app','public.inventory_aios_audit_values_are_valid(jsonb)','EXECUTE')
       OR has_any_column_privilege('inventory_aios_app','public.user_password_credentials','SELECT')
       OR has_any_column_privilege('inventory_aios_app','public.auth_sessions','SELECT')
       OR has_any_column_privilege('inventory_aios_app','public.auth_sessions','INSERT')
       OR has_any_column_privilege('inventory_aios_app','public.auth_sessions','UPDATE')
       OR has_any_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','INSERT')
       OR has_any_column_privilege('inventory_aios_app','public.auth_login_attempt_buckets','UPDATE')
       OR has_any_column_privilege('inventory_aios_app','public.audit_events','INSERT')
       OR has_any_column_privilege('inventory_aios_app','public.audit_events','SELECT')
       OR has_column_privilege('inventory_aios_app','public.user_password_credentials','password_hash','UPDATE') THEN
        RAISE EXCEPTION 'New runtime authentication or audit privileges remain';
    END IF;
    FOREACH table_name IN ARRAY ARRAY[
        'asset_categories','suppliers','locations','inventory_products','receipts',
        'receipt_lines','tracked_assets','quantity_inventory_lots','inventory_balances',
        'inventory_movements','asset_registration_events','asset_registration_requests',
        'quantity_registration_requests','allocations','allocation_lines','inventory_returns',
        'asset_repairs','disposal_requests','employee_exit_clearances','workflow_approvals',
        'quantity_disposition_requests','idempotency_requests'
    ] LOOP
        IF has_table_privilege('inventory_aios_app', 'public.' || table_name, 'SELECT')
           OR has_table_privilege('inventory_aios_app', 'public.' || table_name, 'INSERT')
           OR has_table_privilege('inventory_aios_app', 'public.' || table_name, 'UPDATE') THEN
            RAISE EXCEPTION 'Operational privileges remain on public.%', table_name;
        END IF;
    END LOOP;
END
$verify$;
COMMIT;
