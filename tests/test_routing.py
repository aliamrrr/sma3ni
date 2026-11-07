from sma3ni.routing import Rule, lang_family, route
from sma3ni.textnorm import normalize, variants

RULES = [
    Rule.build("etat_civil", "etat_civil", ["عقد الازدياد", "شهادة السكنى", "acte de naissance"], 3, 1),
    Rule.build("urbanisme", "urbanisme", ["رخصة البني", "permis de construire"], 3, 2),
    Rule.build("eau_electricite", "eau_electricite", ["الما", "الضو", "مقطوع", "facture"], 3, 3),
    Rule.build("proprete_voirie", "proprete_voirie", ["الزبل", "الواد الحار"], 3, 4),
    Rule.build("protection_sociale", "protection_sociale", ["الدعم المباشر", "المؤشر", "rsu"], 3, 5),
    Rule.build("integrite", "inspection", ["رشوة", "corruption"], 1, 6),
]


def decide(text, label="ary", conf=0.95):
    return route(text, RULES, label, conf, 0.5)


def test_normalize_folds_hamza_tashkeel_and_moroccan_letters():
    assert normalize("أَحْمَد إِبْرَاهِيم") == "احمد ابراهيم"
    assert normalize("مدرسة") == "مدرسه"
    assert normalize("ڭلسة") == "كلسه"
    assert normalize("Électricité, SVP!") == "electricite svp"


def test_variants_strip_clitics_but_not_to_two_letters():
    assert "ضو" not in variants("الضو")  # stem would be 2 letters
    assert "الما" in variants("والما")
    assert "ما" not in variants("الما")


def test_birth_certificate_request_in_darija():
    d = decide("السلام عليكم بغيت نخرج عقد الازدياد ديال ولدي و مابغاوش يعطيوهولي")
    assert (d.category, d.service_code, d.priority, d.needs_review) == ("etat_civil", "etat_civil", 3, False)


def test_negation_ma_does_not_trigger_water():
    d = decide("ما عندي حتى مشكل غير بغيت نسول")
    assert d.service_code == "triage" and "no_rule_matched" in d.review_reasons


def test_sewage_phrase_with_clitic():
    d = decide("الواد الحار طالع فالزنقة ديالنا هادي سيمانة")
    assert d.category == "proprete_voirie"


def test_code_switching_french():
    d = decide("عندي مشكل ف la facture ديال الضو، جاتني غالية بزاف")
    assert d.category == "eau_electricite"
    assert set(d.matched_keywords) >= {"facture", "الضو"}


def test_corruption_escalates_priority_even_on_tie():
    d = decide("طلبو مني رشوة باش يعطيوني رخصة البني")
    assert d.category == "integrite" and d.service_code == "inspection" and d.priority == 1


def test_social_support_index():
    d = decide("المؤشر ديالي طلع و حبسو عليا الدعم المباشر")
    assert d.category == "protection_sociale"


def test_language_gate():
    assert decide("بغيت عقد الازدياد", label="mey").lang_family == "hassaniya"
    amazigh = decide("بغيت عقد الازدياد", label="zgh")
    assert amazigh.needs_review and "language_not_supported_by_asr:amazigh" in amazigh.review_reasons
    low = decide("بغيت عقد الازدياد", conf=0.2)
    assert low.needs_review and low.category == "etat_civil"


def test_lang_family_labels():
    assert lang_family("ary") == "darija"
    assert lang_family("ary_Arab") == "darija"
    assert lang_family("Moroccan Arabic") == "darija"
    assert lang_family("arb_Arab") == "msa"
    assert lang_family("arz") == "arabic_other"
    assert lang_family("fas_Arab") == "other"
    assert lang_family(None) == "unknown"
    # real LIDstral-Arabic labels
    assert lang_family("Morocco") == "darija"
    assert lang_family("Mauritania") == "hassaniya"
    assert lang_family("MSA") == "msa"
    assert lang_family("Tamazight_Tifinagh") == "amazigh"
    assert lang_family("Saudi_Arabia") == "arabic_other"
    assert lang_family("UAE") == "arabic_other"
    assert lang_family("Malay_Jawi") == "other"


def test_empty_transcript():
    d = decide("   ")
    assert d.needs_review and "empty_transcript" in d.review_reasons


def test_keyword_reported_matches_rule_even_with_empty_keywords():
    rule = Rule.build("eau_electricite", "eau_electricite", ["!!!", "facture"], 3, 1)
    d = route("عندي مشكل ف la facture", [rule], "ary", 0.95, 0.5)
    assert d.matched_keywords == ("facture",)
