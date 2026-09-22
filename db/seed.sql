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

-- 3 users under Tenant A, one per staff role: underwriter, medical_professional, admin.
INSERT INTO users (id, tenant_id, full_name, email, role, license_number, password_hash, is_active) VALUES
    ('a1111111-0000-0000-0000-000000000001', '11111111-1111-1111-1111-111111111111',
     'Seed Underwriter', 'underwriter@dev.local', 'underwriter', 'LIC-0001',
     '$argon2id$v=19$m=65536,t=3,p=4$LcR7NibWlRRLszB6Gxrv7Q$Px8qGGljXwVwFACq72XHpuPSNLrekg4GIWYCfceOz/Q', TRUE),
    ('a1111111-0000-0000-0000-000000000002', '11111111-1111-1111-1111-111111111111',
     'Seed Medical Professional', 'medical@dev.local', 'medical_professional', 'LIC-0002',
     '$argon2id$v=19$m=65536,t=3,p=4$LcR7NibWlRRLszB6Gxrv7Q$Px8qGGljXwVwFACq72XHpuPSNLrekg4GIWYCfceOz/Q', TRUE),
    ('a1111111-0000-0000-0000-000000000003', '11111111-1111-1111-1111-111111111111',
     'Seed Admin', 'admin@dev.local', 'admin', NULL,
     '$argon2id$v=19$m=65536,t=3,p=4$LcR7NibWlRRLszB6Gxrv7Q$Px8qGGljXwVwFACq72XHpuPSNLrekg4GIWYCfceOz/Q', TRUE);

-- The three built-in accounts: `underwriter`, `medical` and `admin`, one per staff
-- role (apps/api/app/routers/auth.py, BUILT_IN_ACCOUNTS). They sign in without
-- the database at all (see docs/DEMO_SETUP.md), but they present fixed ids, and
-- a decision or an audit entry points at its author by foreign key. So those
-- ids need real rows, or the account can look around but not decide anything.
--
-- The API also creates these rows itself after a built-in sign-in, which is
-- what covers a database that was set up before they existed. Seeding them here
-- just means a fresh database has them from the first request.
--
-- The hash below is of a random value that was thrown away, on purpose. These
-- accounts are checked against ADMIN_PASSWORD in code and never against this
-- column. A real hash here would keep them working through the ordinary
-- sign-in after ADMIN_PASSWORD was cleared to switch them off.
INSERT INTO tenants (id, name, subscription_tier) VALUES
    ('00000000-0000-0000-0000-0000000000c0', 'Demo Insurance Co.', 'demo');

INSERT INTO users (id, tenant_id, full_name, email, role, license_number, password_hash, is_active) VALUES
    ('00000000-0000-0000-0000-0000000000b1', '00000000-0000-0000-0000-0000000000c0',
     'Underwriter', 'underwriter', 'underwriter', NULL,
     '$argon2id$v=19$m=65536,t=3,p=4$7H/sZWjcvLtPU8SO/r5k3w$Km9sr1HaIumMrWtVinf5giB9q/wAiQ34ejK275CEV+g', TRUE),
    ('00000000-0000-0000-0000-0000000000b2', '00000000-0000-0000-0000-0000000000c0',
     'Medical Professional', 'medical', 'medical_professional', NULL,
     '$argon2id$v=19$m=65536,t=3,p=4$7H/sZWjcvLtPU8SO/r5k3w$Km9sr1HaIumMrWtVinf5giB9q/wAiQ34ejK275CEV+g', TRUE),
    ('00000000-0000-0000-0000-0000000000ad', '00000000-0000-0000-0000-0000000000c0',
     'Administrator', 'admin', 'admin', NULL,
     '$argon2id$v=19$m=65536,t=3,p=4$7H/sZWjcvLtPU8SO/r5k3w$Km9sr1HaIumMrWtVinf5giB9q/wAiQ34ejK275CEV+g', TRUE);

-- No model_arms rows here on purpose. The API registers each arm from its own
-- registry (app/arms/__init__.py) the first time it runs one, so the name,
-- version, preprocessing version and weight hash always describe the code that
-- actually produced the score. A hand-written row here would drift the moment
-- the model is retrained.

-- ============================================================================
-- Isolation smoke test (manual):
--   SET LOCAL app.tenant_id = '11111111-1111-1111-1111-111111111111';
--   SELECT * FROM users;   -- should return only Tenant A's 3 users
--   SET LOCAL app.tenant_id = '22222222-2222-2222-2222-222222222222';
--   SELECT * FROM users;   -- should return 0 rows
-- ============================================================================
