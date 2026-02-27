-- sla_config — 4 rows, one per priority (scope §5.1 + §5.2)
-- Thresholds are runtime-configurable by Admin (no code deployment required).

INSERT INTO sla_config (
    priority,
    temp_fix_hours,
    permanent_fix_days,
    overdue_t1_days,
    overdue_t2_days,
    overdue_t3_days,
    overdue_t4_days
) VALUES
    ('CRITICAL', 12,  7, 3, 7, 30, 365),
    ('HIGH',     24,  7, 3, 7, 30, 365),
    ('MEDIUM',   72,  7, 3, 7, 30, 365),
    ('LOW',      168, 7, 3, 7, 30, 365)
ON CONFLICT (priority) DO NOTHING;
