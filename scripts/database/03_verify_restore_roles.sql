\set ON_ERROR_STOP on
BEGIN READ ONLY;
DO $guard$
DECLARE n integer;
BEGIN
    IF current_database() <> 'inventory_aios_restore_check' THEN
        RAISE EXCEPTION 'Wrong database: expected inventory_aios_restore_check, got %', current_database();
    END IF;
    SELECT count(*) INTO n FROM pg_catalog.pg_tables WHERE schemaname='public';
    IF n <> 12 THEN RAISE EXCEPTION 'Expected 12 public tables including alembic_version; found %', n; END IF;
    IF (SELECT count(*) FROM pg_catalog.pg_constraint WHERE connamespace='public'::regnamespace AND contype IN ('p','f','u')) <> 36
       OR (SELECT count(*) FROM pg_catalog.pg_constraint WHERE connamespace='public'::regnamespace AND contype='c') <> 3
       OR (SELECT count(*) FROM pg_catalog.pg_constraint WHERE connamespace='public'::regnamespace AND contype='n') <> 67 THEN
        RAISE EXCEPTION 'Constraint categories do not match the verified PostgreSQL 18 restore baseline';
    END IF;
    SELECT count(*) INTO n FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace ns ON ns.oid=p.pronamespace WHERE ns.nspname='public' AND p.prokind='f';
    IF n <> 2 THEN RAISE EXCEPTION 'Expected 2 application functions; found %', n; END IF;
    SELECT count(*) INTO n FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace ns ON ns.oid=c.relnamespace WHERE ns.nspname='public' AND NOT t.tgisinternal;
    IF n <> 11 THEN RAISE EXCEPTION 'Expected 11 application triggers; found %', n; END IF;
    IF (SELECT version_num FROM public.alembic_version) <> '36368303c6c6' THEN
        RAISE EXCEPTION 'Unexpected Alembic revision in restore';
    END IF;
END
$guard$;
DO $role_checks$
DECLARE bad integer;
BEGIN
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='inventory_aios_owner' AND (rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls)) THEN
        RAISE EXCEPTION 'inventory_aios_owner has unsafe role attributes';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='inventory_aios_migrator' AND rolcanlogin AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole AND NOT rolreplication AND NOT rolbypassrls AND NOT rolinherit) THEN
        RAISE EXCEPTION 'inventory_aios_migrator has unsafe role attributes';
    END IF;
    IF (SELECT pg_catalog.pg_get_userbyid(datdba) FROM pg_catalog.pg_database WHERE datname=current_database()) <> 'inventory_aios_owner' THEN
        RAISE EXCEPTION 'Rehearsal database is not owned by inventory_aios_owner';
    END IF;
    IF has_database_privilege('inventory_aios_app', current_database(), 'CREATE') OR has_database_privilege('inventory_aios_app', current_database(), 'TEMP') THEN
        RAISE EXCEPTION 'Runtime role has database CREATE or TEMP privilege';
    END IF;
    IF (SELECT nspowner FROM pg_catalog.pg_namespace WHERE nspname='public') <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='inventory_aios_owner') THEN
        RAISE EXCEPTION 'public schema is not owned by inventory_aios_owner';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_namespace ns WHERE ns.nspname='public' AND ns.nspowner <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='inventory_aios_owner')) THEN
        RAISE EXCEPTION 'public schema ownership mismatch';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace ns ON ns.oid=t.typnamespace WHERE ns.nspname='public' AND t.typtype IN ('e','d','r','m') AND t.typrelid=0 AND t.typowner <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='inventory_aios_owner') AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid='pg_type'::regclass AND d.objid=t.oid AND d.deptype='e')) THEN
        RAISE EXCEPTION 'One or more application types have the wrong owner';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace ns ON ns.oid=c.relnamespace
        WHERE ns.nspname='public' AND c.relkind IN ('r','p','v','m','S','f')
          AND c.relowner <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='inventory_aios_owner')
          AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid='pg_class'::regclass AND d.objid=c.oid AND d.deptype='e')
    ) THEN RAISE EXCEPTION 'One or more application relation objects have the wrong owner'; END IF;
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace ns ON ns.oid=p.pronamespace
        WHERE ns.nspname='public' AND p.prokind IN ('f','p')
          AND p.proowner <> (SELECT oid FROM pg_catalog.pg_roles WHERE rolname='inventory_aios_owner')
          AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_depend d WHERE d.classid='pg_proc'::regclass AND d.objid=p.oid AND d.deptype='e')
    ) THEN RAISE EXCEPTION 'One or more application functions/procedures have the wrong owner'; END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles parent ON parent.oid=m.roleid
        JOIN pg_catalog.pg_roles member ON member.oid=m.member
        WHERE parent.rolname='inventory_aios_owner' AND member.rolname='inventory_aios_migrator'
          AND NOT m.inherit_option AND m.set_option
    ) THEN RAISE EXCEPTION 'Migrator membership must have INHERIT FALSE and SET TRUE'; END IF;
    IF EXISTS (SELECT 1 FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles r ON r.oid=m.member WHERE r.rolname='inventory_aios_app') THEN
        RAISE EXCEPTION 'Runtime role has inherited role memberships';
    END IF;
    IF NOT has_database_privilege('inventory_aios_app', current_database(), 'CONNECT') THEN
        RAISE EXCEPTION 'Runtime role cannot connect to the rehearsal database';
    END IF;
    IF NOT has_table_privilege('inventory_aios_app','public.employees','SELECT') OR has_table_privilege('inventory_aios_app','public.employees','INSERT') OR has_table_privilege('inventory_aios_app','public.employees','UPDATE') OR has_table_privilege('inventory_aios_app','public.employees','DELETE') THEN
        RAISE EXCEPTION 'Runtime employee privileges do not match the least-privilege plan';
    END IF;
    IF has_table_privilege('inventory_aios_app','public.employee_history','UPDATE') OR has_table_privilege('inventory_aios_app','public.employee_history','DELETE') OR has_table_privilege('inventory_aios_app','public.employee_history','TRUNCATE') OR has_table_privilege('inventory_aios_app','public.employee_history','TRIGGER') THEN
        RAISE EXCEPTION 'Runtime role can modify or disable employee_history safeguards';
    END IF;
    IF has_schema_privilege('inventory_aios_app','public','CREATE') THEN
        RAISE EXCEPTION 'Runtime role can create schema objects';
    END IF;
    SELECT count(*) INTO bad FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace ns ON ns.oid=p.pronamespace
    CROSS JOIN LATERAL pg_catalog.aclexplode(COALESCE(p.proacl, pg_catalog.acldefault('f',p.proowner))) a
    WHERE ns.nspname='public' AND p.prokind='f' AND a.grantee=0 AND a.privilege_type='EXECUTE';
    IF bad <> 0 THEN RAISE EXCEPTION 'PUBLIC retains EXECUTE on % public functions', bad; END IF;
    SELECT count(*) INTO bad FROM pg_catalog.pg_default_acl d CROSS JOIN LATERAL pg_catalog.aclexplode(d.defaclacl) a WHERE d.defaclrole=(SELECT oid FROM pg_catalog.pg_roles WHERE rolname='inventory_aios_owner') AND d.defaclobjtype IN ('f','p') AND a.grantee=0 AND a.privilege_type='EXECUTE';
    IF bad <> 0 THEN RAISE EXCEPTION 'Owner default privileges still grant function EXECUTE to PUBLIC'; END IF;
    IF to_regprocedure('public.inventory_aios_audit_metadata_is_valid(jsonb)') IS NOT NULL
       AND NOT has_function_privilege('inventory_aios_app','public.inventory_aios_audit_metadata_is_valid(jsonb)','EXECUTE') THEN
        RAISE EXCEPTION 'Runtime role lacks audit validator EXECUTE privilege';
    END IF;
END
$role_checks$;
SELECT current_database() AS database_name, pg_catalog.pg_get_userbyid(d.datdba) AS database_owner, current_user, session_user, current_setting('transaction_read_only') AS read_only FROM pg_catalog.pg_database d WHERE d.datname=current_database();
SELECT count(*) AS explicit_nonconstraint_index_count FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class idx ON idx.oid=i.indexrelid JOIN pg_catalog.pg_namespace ns ON ns.oid=idx.relnamespace WHERE ns.nspname='public' AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint co WHERE co.conindid=i.indexrelid);
SELECT version_num AS alembic_revision FROM public.alembic_version;
SELECT count(*) AS public_table_count FROM pg_catalog.pg_tables WHERE schemaname='public';
SELECT contype AS constraint_type, count(*) AS catalog_count FROM pg_catalog.pg_constraint WHERE connamespace='public'::regnamespace GROUP BY contype ORDER BY contype;
SELECT count(*) AS application_function_count FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.prokind='f';
SELECT count(*) AS application_trigger_count FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND NOT t.tgisinternal;
SELECT count(*) AS archive_listed_style_indexes FROM pg_catalog.pg_index i JOIN pg_catalog.pg_class idx ON idx.oid=i.indexrelid JOIN pg_catalog.pg_namespace n ON n.oid=idx.relnamespace WHERE n.nspname='public' AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_constraint co WHERE co.conindid=i.indexrelid);
SELECT c.relname AS table_name, pg_catalog.pg_get_userbyid(c.relowner) AS owner, c.relkind
FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND c.relkind IN ('r','p','v','m','S','f') ORDER BY 1;
SELECT p.proname, pg_catalog.pg_get_function_identity_arguments(p.oid) AS arguments,
       pg_catalog.pg_get_userbyid(p.proowner) AS owner, p.proacl,
       pg_catalog.pg_get_functiondef(p.oid) AS normalized_definition
FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='public' AND p.prokind='f' ORDER BY 1,2;
SELECT c.relname AS table_name, t.tgname, pg_catalog.pg_get_triggerdef(t.oid,true) AS definition
FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_class c ON c.oid=t.tgrelid
JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
WHERE n.nspname='public' AND NOT t.tgisinternal ORDER BY 1,2;
SELECT tablename,indexname,indexdef FROM pg_catalog.pg_indexes WHERE schemaname='public' ORDER BY 1,2;
SELECT table_name, privilege_type, grantee FROM information_schema.role_table_grants
WHERE table_schema='public' AND grantee IN ('PUBLIC','inventory_aios_app') ORDER BY 1,2,3;
SELECT r.rolname, r.rolcanlogin, r.rolsuper, r.rolcreatedb, r.rolcreaterole, r.rolbypassrls
FROM pg_catalog.pg_roles r WHERE r.rolname IN ('inventory_aios_owner','inventory_aios_migrator','inventory_aios_app') ORDER BY 1;
SELECT member.rolname AS member, parent.rolname AS granted_role, m.inherit_option, m.set_option
FROM pg_catalog.pg_auth_members m JOIN pg_catalog.pg_roles member ON member.oid=m.member
JOIN pg_catalog.pg_roles parent ON parent.oid=m.roleid
WHERE member.rolname IN ('inventory_aios_migrator','inventory_aios_app') ORDER BY 1,2;
SELECT has_table_privilege('inventory_aios_app','public.employee_history','UPDATE') AS app_history_update,
       has_table_privilege('inventory_aios_app','public.employee_history','DELETE') AS app_history_delete,
       has_table_privilege('inventory_aios_app','public.employee_history','TRUNCATE') AS app_history_truncate,
       has_table_privilege('inventory_aios_app','public.employee_history','TRIGGER') AS app_history_trigger,
       has_schema_privilege('inventory_aios_app','public','CREATE') AS app_schema_create;
COMMIT;
