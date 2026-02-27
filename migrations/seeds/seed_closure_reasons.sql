-- ref_closure_reason — 5 rows (scope §5.3)
-- Used when Admin closes a Tier-4 case.

INSERT INTO ref_closure_reason (code, label, label_th, requires_note) VALUES
    (
        'BUDGET_NOT_ALLOCATED',
        'Budget not allocated',
        'งบประมาณยังไม่ได้รับการจัดสรร',
        FALSE
    ),
    (
        'BUDGET_INSUFFICIENT',
        'Budget insufficient',
        'งบประมาณไม่เพียงพอ',
        FALSE
    ),
    (
        'SCOPE_TOO_LARGE',
        'Scope too large',
        'ขอบเขตงานใหญ่เกินไป',
        FALSE
    ),
    (
        'PENDING_EXTERNAL_AGENCY',
        'Pending external agency',
        'รอหน่วยงานอื่น',
        FALSE
    ),
    (
        'OTHER',
        'Other',
        'อื่น ๆ',
        TRUE   -- free-text note required
    )
ON CONFLICT (code) DO NOTHING;
