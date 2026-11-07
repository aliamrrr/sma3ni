-- Default services and routing rules. Keywords are stored raw (Darija / MSA /
-- French); the nlp-worker normalises them the same way as transcripts.
-- Edit freely in production: UPDATE routing_rules SET keywords = ... WHERE category = ...

INSERT INTO services (code, name_fr, name_ar) VALUES
    ('triage',             'Cellule de tri central',                       'خلية الفرز المركزية'),
    ('etat_civil',         'Bureau d''état civil (commune)',               'مكتب الحالة المدنية'),
    ('urbanisme',          'Service urbanisme',                            'مصلحة التعمير'),
    ('eau_electricite',    'Distribution eau et électricité (SRM)',        'توزيع الماء والكهرباء'),
    ('proprete_voirie',    'Propreté, voirie et assainissement',           'النظافة والطرق والتطهير'),
    ('sante',              'Délégation de la santé',                       'مندوبية الصحة'),
    ('protection_sociale', 'Protection sociale (ASD, RSU, AMO)',           'الحماية الاجتماعية'),
    ('identite',           'Identité (CNIE, passeport)',                   'الهوية'),
    ('inspection',         'Inspection et intégrité',                      'المفتشية والنزاهة'),
    ('protection_civile',  'Autorité locale et protection civile',         'السلطة المحلية والوقاية المدنية')
ON CONFLICT (code) DO NOTHING;

INSERT INTO routing_rules (category, service_code, priority, keywords) VALUES
    ('etat_civil', 'etat_civil', 3, ARRAY[
        'عقد الازدياد', 'رسم الولادة', 'الحالة المدنية', 'الدفتر العائلي', 'كناش الحالة المدنية',
        'شهادة الحياة', 'شهادة السكنى', 'شهادة الوفاة', 'نسخة كاملة',
        'extrait', 'acte de naissance', 'etat civil', 'livret de famille', 'copie integrale',
        'certificat de residence']),
    ('urbanisme', 'urbanisme', 3, ARRAY[
        'رخصة البناء', 'رخصة البني', 'رخصة السكن', 'التصميم', 'البناء العشوائي', 'التعمير',
        'permis de construire', 'permis d habiter', 'urbanisme']),
    ('eau_electricite', 'eau_electricite', 3, ARRAY[
        'الما', 'الماء', 'الضو', 'الضوء', 'الكهرباء', 'الفاتورة', 'لافاكتور', 'الكونطور', 'العداد',
        'مقطوع', 'تسرب', 'coupure', 'facture', 'compteur', 'electricite', 'fuite']),
    ('proprete_voirie', 'proprete_voirie', 3, ARRAY[
        'الزبل', 'الازبال', 'الوسخ', 'الحفرة', 'الحفر', 'الواد الحار', 'قنوات الصرف', 'البالوعة',
        'الكلاب الضالة', 'الطريق', 'الزنقة محفورة',
        'poubelle', 'dechets', 'nid de poule', 'voirie', 'assainissement', 'eclairage public']),
    ('sante', 'sante', 3, ARRAY[
        'السبيطار', 'الصبيطار', 'المستشفى', 'المستوصف', 'الطبيب', 'الدكتور', 'الدوا', 'الدواء',
        'hopital', 'medecin', 'dispensaire', 'rendez vous', 'urgences']),
    ('protection_sociale', 'protection_sociale', 3, ARRAY[
        'الدعم المباشر', 'الدعم', 'السجل الاجتماعي', 'المؤشر', 'التغطية الصحية', 'امو', 'تضامن',
        'الضمان الاجتماعي', 'التقاعد', 'المنحة',
        'amo', 'cnss', 'rsu', 'aide directe', 'aide sociale', 'retraite', 'allocation']),
    ('identite', 'identite', 3, ARRAY[
        'البطاقة الوطنية', 'لاكارط ناسيونال', 'الباسبور', 'جواز السفر',
        'carte nationale', 'cnie', 'passeport']),
    ('integrite', 'inspection', 1, ARRAY[
        'رشوة', 'الرشوة', 'التدويرة', 'الفساد', 'الشطط',
        'corruption', 'pot de vin', 'abus de pouvoir']),
    ('danger', 'protection_civile', 1, ARRAY[
        'خطر', 'خطير', 'حريق', 'انهيار', 'طاحت', 'غادي تطيح', 'مهددة بالانهيار',
        'danger', 'incendie', 'effondrement'])
ON CONFLICT (category) DO NOTHING;
