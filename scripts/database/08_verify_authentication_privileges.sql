\set ON_ERROR_STOP on
BEGIN READ ONLY;
DO $guard$
BEGIN
    IF current_database() <> 'inventory_aios_restore_check' THEN
        RAISE EXCEPTION 'Wrong database: authentication verification is rehearsal-only';
    END IF;
    IF session_user <> 'inventory_aios_app' OR current_user <> 'inventory_aios_app' THEN
        RAISE EXCEPTION 'Connect directly as inventory_aios_app';
    END IF;
    -- Revision is checked by Alembic/migrator before this direct runtime-role
    -- verification. The application role intentionally cannot read alembic_version.
    IF EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles r ON r.oid = m.member
        WHERE r.rolname = 'inventory_aios_app'
    ) OR EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        JOIN pg_catalog.pg_roles r ON r.oid = c.relowner
        WHERE n.nspname = 'public'
          AND c.relname IN ('user_password_credentials', 'auth_sessions')
          AND r.rolname <> 'inventory_aios_owner'
    ) THEN
        RAISE EXCEPTION 'Runtime membership or authentication table ownership is invalid';
    END IF;
    IF (SELECT r.rolcanlogin OR r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolreplication OR r.rolbypassrls
        FROM pg_catalog.pg_roles r WHERE r.rolname = 'inventory_aios_owner')
       OR (SELECT count(*) FROM pg_catalog.pg_roles r
           WHERE r.rolname IN ('inventory_aios_owner','inventory_aios_migrator','inventory_aios_app')) <> 3
       OR NOT (SELECT r.rolcanlogin AND NOT r.rolsuper AND NOT r.rolcreatedb
               AND NOT r.rolcreaterole AND NOT r.rolreplication AND NOT r.rolbypassrls
               FROM pg_catalog.pg_roles r WHERE r.rolname = 'inventory_aios_migrator')
       OR NOT (SELECT r.rolcanlogin AND NOT r.rolsuper AND NOT r.rolcreatedb
               AND NOT r.rolcreaterole AND NOT r.rolreplication AND NOT r.rolbypassrls
           FROM pg_catalog.pg_roles r WHERE r.rolname = 'inventory_aios_app')
       OR (SELECT pg_catalog.pg_get_userbyid(d.datdba) FROM pg_catalog.pg_database d
           WHERE d.datname = current_database()) <> 'inventory_aios_owner'
       OR (SELECT pg_catalog.pg_get_userbyid(n.nspowner) FROM pg_catalog.pg_namespace n
           WHERE n.nspname = 'public') <> 'inventory_aios_owner' THEN
        RAISE EXCEPTION 'Owner, migrator, runtime role, database, or schema ownership is invalid';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_catalog.pg_auth_members m
        JOIN pg_catalog.pg_roles member ON member.oid = m.member
        JOIN pg_catalog.pg_roles granted ON granted.oid = m.roleid
        WHERE member.rolname = 'inventory_aios_migrator'
          AND granted.rolname = 'inventory_aios_owner'
          AND NOT m.inherit_option AND m.set_option
    ) THEN
        RAISE EXCEPTION 'Migrator-to-owner membership options are invalid';
    END IF;
    IF has_table_privilege(current_user, 'public.user_password_credentials', 'INSERT')
       OR has_table_privilege(current_user, 'public.user_password_credentials', 'UPDATE')
       OR has_table_privilege(current_user, 'public.user_password_credentials', 'DELETE')
       OR has_table_privilege(current_user, 'public.auth_sessions', 'DELETE')
       OR has_table_privilege(current_user, 'public.auth_sessions', 'TRUNCATE')
       OR has_schema_privilege(current_user, 'public', 'CREATE')
       OR has_database_privilege(current_user, current_database(), 'CREATE')
       OR has_column_privilege(current_user, 'public.user_password_credentials', 'password_hash', 'UPDATE')
       OR has_column_privilege(current_user, 'public.auth_sessions', 'token_hash', 'UPDATE')
       OR has_column_privilege(current_user, 'public.auth_sessions', 'user_id', 'UPDATE') THEN
        RAISE EXCEPTION 'Unexpected authentication or schema mutation privileges';
    END IF;
    IF NOT has_column_privilege(current_user, 'public.user_password_credentials', 'password_hash', 'SELECT')
       OR NOT has_column_privilege(current_user, 'public.user_password_credentials', 'credential_version', 'SELECT')
       OR NOT has_column_privilege(current_user, 'public.auth_sessions', 'token_hash', 'SELECT')
       OR NOT has_column_privilege(current_user, 'public.auth_sessions', 'id', 'INSERT')
       OR NOT has_column_privilege(current_user, 'public.auth_sessions', 'last_seen_at', 'UPDATE')
       OR NOT has_column_privilege(current_user, 'public.auth_sessions', 'revoked_at', 'UPDATE') THEN
        RAISE EXCEPTION 'Required authentication repository privileges are missing';
    END IF;
END
$guard$;
SELECT current_database() AS database_name, session_user, current_user,
       has_column_privilege(current_user, 'public.user_password_credentials', 'password_hash', 'SELECT') AS credential_hash_read,
       has_table_privilege(current_user, 'public.user_password_credentials', 'UPDATE') AS credential_update,
       has_table_privilege(current_user, 'public.auth_sessions', 'INSERT') AS session_insert,
       has_table_privilege(current_user, 'public.auth_sessions', 'DELETE') AS session_delete,
       has_schema_privilege(current_user, 'public', 'CREATE') AS schema_create;
COMMIT;
