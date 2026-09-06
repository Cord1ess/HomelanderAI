-- ============================================================================
-- HomelanderAI — dev seed data
-- Run after schema.sql. Local/dev use only — never run against a real deploy.
--
-- Dev login password for ALL seeded users: devpassword123
-- (hashed below with Argon2id — do not reuse this hash for real accounts)
-- ============================================================================

-- 2 tenants — isolation cannot be tested with only one.
INSERT INTO tenants (id, name, subscription_tier) VALUES
    ('11111111-1111-1111-1111-111111111111', 'Tenant A Insurance Co.', 'standard'),
    ('22222222-2222-2222-2222-222222222222', 'Tenant B Insurance Co.', 'standard');

-- 3 users under Tenant A: underwriter, senior_underwriter, admin.
INSERT INTO users (id, tenant_id, full_name, email, role, license_number, password_hash, is_active) VALUES
    ('a1111111-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
     'Dev Underwriter', 'underwriter@dev.local', 'underwriter', 'LIC-0001',
     '$argon2id$v=19$m=65536,t=3,p=4$LcR7NibWlRRLszB6Gxrv7Q$Px8qGGljXwVwFACq72XHpuPSNLrekg4GIWYCfceOz/Q', TRUE),
    ('a1111111-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
     'Dev Senior Underwriter', 'senior@dev.local', 'senior_underwriter', 'LIC-0002',
     '$argon2id$v=19$m=65536,t=3,p=4$LcR7NibWlRRLszB6Gxrv7Q$Px8qGGljXwVwFACq72XHpuPSNLrekg4GIWYCfceOz/Q', TRUE),
    ('a1111111-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
     'Dev Admin', 'admin@dev.local', 'admin', NULL,
     '$argon2id$v=19$m=65536,t=3,p=4$LcR7NibWlRRLszB6Gxrv7Q$Px8qGGljXwVwFACq72XHpuPSNLrekg4GIWYCfceOz/Q', TRUE);

-- The built-in demo account. `admin` / `admin123` signs in without the database
-- at all (see docs/DEMO_SETUP.md), but it presents fixed ids — so those ids need
-- real rows here, or the moment it creates an application the foreign key on
-- tenant_id fails. Seeding them also makes the same credentials work through the
-- ordinary password path once the database is up.
INSERT INTO tenants (id, name, subscription_tier) VALUES
    ('00000000-0000-0000-0000-0000000000c0', 'Demo Insurance Co.', 'demo');

INSERT INTO users (id, tenant_id, full_name, email, role, license_number, password_hash, is_active) VALUES
    ('00000000-0000-0000-0000-0000000000ad', '00000000-0000-0000-0000-0000000000c0',
     'Administrator', 'admin', 'admin', NULL,
     '$argon2id$v=19$m=65536,t=3,p=4$u2Em6TQYJnliER/RgDMvrg$3LPs+jFI3ydevY2uRwdPDFnH5Sm7ZMx1LabGCnouiAE', TRUE);

-- No model_arms rows here on purpose. The API registers each arm from its own
-- registry (app/arms/__init__.py) the first time it runs one, so the name,
-- version, preprocessing version and weight hash always describe the code that
-- actually produced the score. A hand-written row here would drift the moment
-- the model is retrained.

-- Default notification preferences — one row per user per notification_type.
DO $$
DECLARE
    u UUID;
    nt notification_type;
BEGIN
    FOR u IN
        SELECT id FROM users WHERE tenant_id = '11111111-1111-1111-1111-111111111111'
    LOOP
        FOR nt IN SELECT unnest(enum_range(NULL::notification_type))
        LOOP
            INSERT INTO notification_preferences (user_id, notification_type, email_enabled, in_app_enabled)
            VALUES (u, nt, TRUE, TRUE)
            ON CONFLICT (user_id, notification_type) DO NOTHING;
        END LOOP;
    END LOOP;
END $$;

-- ============================================================================
-- Isolation smoke test (manual):
--   SET LOCAL app.tenant_id = '11111111-1111-1111-1111-111111111111';
--   SELECT * FROM users;   -- should return only Tenant A's 3 users
--   SET LOCAL app.tenant_id = '22222222-2222-2222-2222-222222222222';
--   SELECT * FROM users;   -- should return 0 rows
-- ============================================================================
