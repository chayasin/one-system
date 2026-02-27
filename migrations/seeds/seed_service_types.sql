-- ref_service_type — 12 rows (scope §7.3)
-- channel: NULL = available on all channels; 'CALL_1146' or 'LINE' = channel-specific

INSERT INTO ref_service_type (code, label, channel) VALUES
    ('1',  'สอบถามสภาพการจราจร',                           NULL),
    ('2',  'สอบถามเส้นทาง',                                 NULL),
    ('3',  'แจ้งอุบัติเหตุ',                                NULL),
    ('4',  'ขอความช่วยเหลือรถเสีย',                         NULL),
    ('5',  'ภัยพิบัติ',                                      NULL),
    ('6',  'ร้องเรียน',                                      NULL),
    ('7',  'สอบถามข้อมูลหน่วยงานกรมทางหลวงชนบท',           NULL),
    ('8',  'สอบถามข้อมูลหน่วยงานอื่นๆ',                    NULL),
    ('9',  'อื่น ๆ',                                         NULL),
    ('10', 'เบอร์รบกวน',                                     'CALL_1146'),
    ('11', 'ข่าวประชาสัมพันธ์/รูปภาพสวัสดี',               'LINE'),
    ('12', 'กดประเมินปรับปรุง',                              'CALL_1146')
ON CONFLICT (code) DO NOTHING;
