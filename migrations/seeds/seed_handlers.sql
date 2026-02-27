-- ref_handler — 14 pre-loaded handler display names observed in data_sample.xlsx
-- user_id is NULL until Admin maps them in the Admin UI (Phase 9).
-- The exact strings must match what appears in the LINE source data's ผู้รับเรื่อง field.
--
-- NOTE: Replace the names below with the 14 actual handler display names
--       extracted from data_sample.xlsx once access is available.
--       The placeholders follow the naming pattern observed in the scope.

INSERT INTO ref_handler (display_name, user_id, is_active) VALUES
    ('ธนนันท์ จันที',        NULL, TRUE),
    ('สมชาย วงศ์ทอง',       NULL, TRUE),
    ('นภาพร รักดี',          NULL, TRUE),
    ('วิชัย สุขใจ',          NULL, TRUE),
    ('อรุณี พงษ์ศิริ',       NULL, TRUE),
    ('กิตติ มานะดี',         NULL, TRUE),
    ('ประภา เจริญสุข',       NULL, TRUE),
    ('สุชาติ บุญมาก',        NULL, TRUE),
    ('รัตนา ศรีสวัสดิ์',     NULL, TRUE),
    ('วันดี ทองคำ',          NULL, TRUE),
    ('ณัฐพล ใจดี',           NULL, TRUE),
    ('สิริพร โชคดี',         NULL, TRUE),
    ('มานพ สมหวัง',          NULL, TRUE),
    ('ลัดดา พิมพ์ทอง',       NULL, TRUE)
ON CONFLICT (display_name) DO NOTHING;

-- ⚠️  ACTION REQUIRED before go-live:
--     1. Export handler names from data_sample.xlsx (ผู้รับเรื่อง column, LINE sheet).
--     2. Replace the 14 placeholder names above with the exact strings from the export.
--     3. After Phase 2 user accounts are created, update user_id via the Admin UI or:
--        UPDATE ref_handler SET user_id = '<uuid>' WHERE display_name = '<name>';
