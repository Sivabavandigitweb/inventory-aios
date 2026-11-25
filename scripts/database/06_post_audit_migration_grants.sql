\set ON_ERROR_STOP on
BEGIN;
SET LOCAL ROLE inventory_aios_owner;

DO $guard$
DECLARE
    applied_revision text;
BEGIN
    IF current_database() <> 'inventory_aios_restore_check' THEN
        RAISE EXCEPTION 'Wrong database: expected inventory_aios_restore_check';
    END IF;
    IF session_user <> 'inventory_aios_migrator'
       OR current_user <> 'inventory_aios_owner' THEN
        RAISE EXCEPTION 'Connect as inventory_aios_migrator and assume inventory_aios_owner';
    END IF;
    SELECT version_num INTO applied_revision FROM public.alembic_version;
    IF applied_revision IS DISTINCT FROM '7d4a9c2e1b60' THEN
        RAISE EXCEPTION 'Unexpected Alembic revision';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_roles
        WHERE rolname='inventory_aios_app' AND rolcanlogin AND NOT rolsuper
    ) THEN
        RAISE EXCEPTION 'Expected restricted runtime login is missing';
    END IF;
    IF pg_catalog.pg_has_role('inventory_aios_app','inventory_aios_owner','MEMBER')
       OR pg_catalog.pg_has_role('inventory_aios_app','inventory_aios_migrator','MEMBER') THEN
        RAISE EXCEPTION 'Runtime role has an unexpected role membership';
    END IF;
    IF (SELECT relowner FROM pg_catalog.pg_class
        WHERE oid='public.audit_events'::regclass)
       <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='inventory_aios_owner') THEN
        RAISE EXCEPTION 'Audit table owner does not match the expected owner';
    END IF;
    IF pg_catalog.to_regprocedure(
        'public.inventory_aios_audit_metadata_is_valid(jsonb)'
    ) IS NULL THEN
        RAISE EXCEPTION 'Audit metadata validator is missing';
    END IF;
    IF NOT has_table_privilege('inventory_aios_app','public.employees','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.roles','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.user_roles','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.users','SELECT') THEN
        RAISE EXCEPTION 'Existing runtime read permissions are incomplete';
    END IF;
END
$guard$;

-- Reassert private function execution; runtime invokes only the check validator.
REVOKE ALL PRIVILEGES ON FUNCTION
    public.inventory_aios_audit_metadata_is_valid(jsonb) FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION
    public.inventory_aios_prevent_audit_event_mutation() FROM PUBLIC;
REVOKE ALL PRIVILEGES ON FUNCTION
    public.inventory_aios_audit_metadata_is_valid(jsonb) FROM inventory_aios_app;
REVOKE ALL PRIVILEGES ON FUNCTION
    public.inventory_aios_prevent_audit_event_mutation() FROM inventory_aios_app;

-- Clear stale table/column grants, then grant only the tested ORM privileges.
REVOKE ALL PRIVILEGES ON TABLE public.audit_events FROM inventory_aios_app;
REVOKE SELECT (id, actor_user_id, action, entity_type, entity_id, occurred_at, change_source, metadata)
ON TABLE public.audit_events FROM inventory_aios_app, PUBLIC;
REVOKE INSERT (id, actor_user_id, action, entity_type, entity_id, occurred_at, change_source, metadata)
ON TABLE public.audit_events FROM inventory_aios_app, PUBLIC;
REVOKE UPDATE (id, actor_user_id, action, entity_type, entity_id, occurred_at, change_source, metadata)
ON TABLE public.audit_events FROM inventory_aios_app, PUBLIC;
REVOKE REFERENCES (id, actor_user_id, action, entity_type, entity_id, occurred_at, change_source, metadata)
ON TABLE public.audit_events FROM inventory_aios_app, PUBLIC;
REVOKE ALL PRIVILEGES ON TABLE public.audit_events FROM PUBLIC;
GRANT INSERT (
    id,
    actor_user_id,
    action,
    entity_type,
    entity_id,
    change_source,
    metadata
)
ON TABLE public.audit_events
TO inventory_aios_app;
GRANT SELECT (occurred_at) ON TABLE public.audit_events TO inventory_aios_app;
GRANT EXECUTE ON FUNCTION
    public.inventory_aios_audit_metadata_is_valid(jsonb) TO inventory_aios_app;

DO $verify$
BEGIN
    IF current_database() <> 'inventory_aios_restore_check'
       OR session_user <> 'inventory_aios_migrator'
       OR current_user <> 'inventory_aios_owner'
       OR (SELECT version_num FROM public.alembic_version) <> '7d4a9c2e1b60' THEN
        RAISE EXCEPTION 'Database identity or revision changed during grant review';
    END IF;
    IF has_table_privilege('inventory_aios_app','public.audit_events','INSERT')
       OR has_table_privilege('inventory_aios_app','public.audit_events','SELECT')
       OR NOT has_column_privilege(
           'inventory_aios_app','public.audit_events','occurred_at','SELECT'
       )
       OR has_column_privilege('inventory_aios_app','public.audit_events','id','SELECT')
       OR has_table_privilege('inventory_aios_app','public.audit_events','UPDATE')
       OR has_table_privilege('inventory_aios_app','public.audit_events','DELETE')
       OR has_table_privilege('inventory_aios_app','public.audit_events','TRUNCATE')
       OR has_table_privilege('inventory_aios_app','public.audit_events','TRIGGER')
       OR has_table_privilege('inventory_aios_app','public.audit_events','REFERENCES')
       OR has_schema_privilege('inventory_aios_app','public','CREATE')
       OR NOT has_function_privilege(
           'inventory_aios_app',
           'public.inventory_aios_audit_metadata_is_valid(jsonb)',
           'EXECUTE'
       ) THEN
        RAISE EXCEPTION 'Runtime audit privileges do not match least-privilege plan';
    END IF;
    -- Check effective column rights, including inherited and PUBLIC privileges.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute a
        WHERE a.attrelid='public.audit_events'::regclass
          AND a.attnum > 0 AND NOT a.attisdropped
          AND (
              has_column_privilege('inventory_aios_app', a.attrelid, a.attnum, 'INSERT')
                  IS DISTINCT FROM (a.attname = ANY (ARRAY[
                      'id','actor_user_id','action','entity_type',
                      'entity_id','change_source','metadata'
                  ]))
              OR has_column_privilege('inventory_aios_app', a.attrelid, a.attnum, 'SELECT')
                  IS DISTINCT FROM (a.attname='occurred_at')
              OR has_column_privilege('inventory_aios_app', a.attrelid, a.attnum, 'UPDATE')
              OR has_column_privilege('inventory_aios_app', a.attrelid, a.attnum, 'REFERENCES')
          )
    ) THEN
        RAISE EXCEPTION 'Runtime effective audit column privileges differ from the plan';
    END IF;
    IF has_database_privilege('inventory_aios_app',current_database(),'CREATE')
       OR has_database_privilege('inventory_aios_app',current_database(),'TEMP')
       OR pg_catalog.pg_has_role('inventory_aios_app','inventory_aios_owner','MEMBER')
       OR pg_catalog.pg_has_role('inventory_aios_app','inventory_aios_migrator','MEMBER') THEN
        RAISE EXCEPTION 'Runtime has unexpected DDL or role escalation privileges';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_attribute a
        CROSS JOIN LATERAL pg_catalog.aclexplode(a.attacl) acl
        WHERE a.attrelid='public.audit_events'::regclass AND acl.grantee=0
    ) THEN
        RAISE EXCEPTION 'PUBLIC has audit column privileges';
    END IF;
    IF has_function_privilege(
        'inventory_aios_app','public.inventory_aios_prevent_audit_event_mutation()','EXECUTE'
    ) THEN
        RAISE EXCEPTION 'Runtime can execute the audit trigger function directly';
    END IF;
    IF NOT has_table_privilege('inventory_aios_app','public.employees','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.roles','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.user_roles','SELECT')
       OR NOT has_table_privilege('inventory_aios_app','public.users','SELECT') THEN
        RAISE EXCEPTION 'Existing runtime read permissions changed';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(c.relacl, pg_catalog.acldefault('r',c.relowner))
        ) acl
        WHERE n.nspname='public' AND c.relname='audit_events'
          AND acl.grantee=0
    ) THEN
        RAISE EXCEPTION 'PUBLIC has audit table privileges';
    END IF;
    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_proc p
        CROSS JOIN LATERAL pg_catalog.aclexplode(
            COALESCE(p.proacl, pg_catalog.acldefault('f',p.proowner))
        ) acl
        WHERE p.oid IN (
            'public.inventory_aios_audit_metadata_is_valid(jsonb)'::regprocedure,
            'public.inventory_aios_prevent_audit_event_mutation()'::regprocedure
        )
          AND acl.grantee=0 AND acl.privilege_type='EXECUTE'
    ) THEN
        RAISE EXCEPTION 'PUBLIC can execute a protected audit function';
    END IF;
END
$verify$;

COMMIT;