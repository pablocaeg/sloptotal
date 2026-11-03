import pytest

from app.calibration import language_support
from app.language import count_words, detect_language, is_unspaced

SAMPLES = {
    "en": "I think the council should have voted on the plan before the summer, because it was clear that the budget would not be ready in time for the new school year.",
    "es": "El ayuntamiento aprobó el plan después de varios meses de debate, y los vecinos de la zona dijeron que no se les había consultado antes de la votación.",
    "fr": "Le conseil a voté le plan après plusieurs mois de débat, et les habitants du quartier ont dit qu'ils n'avaient pas été consultés avant le vote.",
    "de": "Der Stadtrat hat den Plan nach monatelanger Debatte beschlossen, und die Anwohner sagten, sie seien vor der Abstimmung nicht gefragt worden.",
    "pt": "A câmara aprovou o plano depois de vários meses de debate, e os moradores da zona disseram que não foram consultados antes da votação.",
    "it": "Il consiglio ha approvato il piano dopo mesi di dibattito, e gli abitanti della zona hanno detto che non sono stati consultati prima del voto.",
    "nl": "De gemeenteraad heeft het plan na maanden van debat goedgekeurd, en de bewoners zeiden dat zij niet voor de stemming zijn geraadpleegd.",
    "pl": "Rada miasta przyjęła plan po wielu miesiącach debaty, a mieszkańcy dzielnicy powiedzieli, że nie zostali o to zapytani przed głosowaniem.",
    "tr": "Belediye meclisi aylar süren tartışmanın ardından planı kabul etti ve bölge sakinleri oylamadan önce kendilerine danışılmadığını söyledi, ama karar değişmedi.",
    "ru": "Городской совет утвердил план после нескольких месяцев споров, и жители района сказали, что с ними не советовались перед голосованием.",
    "uk": "Міська рада ухвалила план після кількох місяців суперечок, і мешканці району сказали, що з ними не радилися перед голосуванням.",
    "ar": "وافق مجلس المدينة على الخطة بعد أشهر من النقاش، وقال سكان الحي إنه لم تتم استشارتهم قبل التصويت.",
    "hi": "नगर परिषद ने महीनों की बहस के बाद योजना को मंज़ूरी दी, और इलाके के निवासियों ने कहा कि मतदान से पहले उनसे सलाह नहीं ली गई।",
    "zh": "市议会经过几个月的辩论后批准了这项计划，该地区的居民说，投票前没有人征求他们的意见。",
    "ja": "市議会は数か月にわたる議論の末にこの計画を承認したが、地域の住民は投票の前に意見を聞かれなかったと話している。",
    "ko": "시의회는 몇 달간의 논쟁 끝에 계획을 승인했지만, 지역 주민들은 투표 전에 의견을 묻지 않았다고 말했다.",
}


@pytest.mark.parametrize("lang", sorted(SAMPLES))
def test_each_known_language_is_detected(lang):
    assert detect_language(SAMPLES[lang]) == lang


def test_english_written_in_the_first_person_is_not_polish():
    text = "I woke up and I could not move. I tried to open my eyes, but I was too tired, and I fell asleep again before I could call anyone."
    assert detect_language(text) == "en"


def test_text_with_no_known_function_words_is_other():
    assert (
        detect_language(
            "Lorem ipsum dolor sit amet consectetur adipiscing elit sed eiusmod tempor"
        )
        == "other"
    )
    assert detect_language("12345 67890") == "other"


def test_chinese_and_japanese_are_counted_at_two_characters_a_word():
    assert count_words("東京都は日本の首都である。") == 6
    assert count_words("这是一个测试。") == 3
    assert count_words("SlopTotal は 文章 を 判定する") == 5


def test_spaced_text_is_counted_by_spaces():
    assert count_words("Hello there,  world") == 3


# Article 1 of the Universal Declaration of Human Rights in Thai, which is 30
# words in English. Splitting it on spaces would give 3.
THAI_ARTICLE_1 = (
    "มนุษย์ทั้งหลายเกิดมามีอิสระและเสมอภาคกันในเกียรติศักดิ์และสิทธิ "
    "ต่างมีเหตุผลและมโนธรรม และควรปฏิบัติต่อกันด้วยเจตนารมณ์แห่งภราดรภาพ"
)


def test_a_thai_sentence_is_counted_near_its_english_length():
    assert len(THAI_ARTICLE_1.split()) == 3
    assert count_words(THAI_ARTICLE_1) == 26


@pytest.mark.parametrize(
    "letter, characters_per_word",
    [("ก", 5), ("ກ", 6), ("ក", 6), ("က", 8)],
    ids=["thai", "lao", "khmer", "burmese"],
)
def test_thai_lao_khmer_and_burmese_are_counted_by_characters(
    letter, characters_per_word
):
    assert count_words(letter * characters_per_word * 10) == 10
    assert count_words(letter * (characters_per_word * 10 + 1)) == 11


def test_spaces_between_thai_phrases_do_not_add_words():
    assert count_words("ก" * 5 + " " + "ก" * 5) == 2


def test_thai_and_spaced_words_are_added_together():
    assert count_words("Hello " + "ก" * 10 + " world") == 4


def test_thai_lao_khmer_and_burmese_count_as_unspaced():
    assert is_unspaced("กรุงเทพมหานครเป็นเมืองหลวง")
    assert is_unspaced("東京都は日本の首都である。")
    assert not is_unspaced("Bangkok is the capital of Thailand.")


# Issue #87: Finnish, Czech and Hungarian had no FUNCTION_WORDS entry, so they
# fell through to whichever language shared a few short words. Czech read as
# Polish, which is a *supported* language, so Czech text was scored under the
# Polish calibration instead of being reported as unsupported.
UNCALIBRATED_SENTENCES = {
    "fi": (
        "Kaupunginvaltuusto hyväksyi suunnitelman useiden kuukausien keskustelun "
        "jälkeen, ja asukkaat sanoivat että heiltä ei ollut kysytty mitään tästä "
        "asiasta lainkaan ennen päätöstä, joka tehtiin hyvin nopeasti."
    ),
    "cs": (
        "Zastupitelstvo schválilo plán po několika měsících diskuse a obyvatelé "
        "řekli, že se jich na to nikdo nezeptal před tím rozhodnutím, které bylo "
        "přijato velmi rychle a bez jejich vědomí."
    ),
    "hu": (
        "A képviselő-testület több hónapos vita után elfogadta a tervet, és a "
        "lakók azt mondták, hogy senki nem kérdezte meg őket erről a döntésről, "
        "amelyet nagyon gyorsan hoztak meg."
    ),
}


@pytest.mark.parametrize("lang", sorted(UNCALIBRATED_SENTENCES))
def test_finnish_czech_and_hungarian_are_detected(lang):
    text = UNCALIBRATED_SENTENCES[lang]
    assert count_words(text) >= 25
    assert detect_language(text) == lang


@pytest.mark.parametrize("lang", sorted(UNCALIBRATED_SENTENCES))
def test_finnish_czech_and_hungarian_are_unsupported(lang):
    """They have no fit, so they must be reported rather than scored."""
    assert language_support(detect_language(UNCALIBRATED_SENTENCES[lang])) == (
        "unsupported"
    )


# Issue #52: Romanian, Indonesian, Vietnamese, Swedish and Danish have function
# words so they are reported as unsupported, but the calibration has no fit for
# them, so the 16 languages in SAMPLES do not cover them. Catalan is below.
UNSUPPORTED_SENTENCES = {
    "ro": (
        "Consiliul local a aprobat planul după câteva luni de dezbateri, iar "
        "locuitorii din cartier au spus că nimeni nu i-a întrebat despre această "
        "decizie, care a fost luată foarte repede și fără ca ei să fie informați "
        "din timp."
    ),
    "id": (
        "Dewan kota menyetujui rencana itu setelah berbulan-bulan berdebat, dan "
        "warga di sekitar kawasan itu mengatakan bahwa tidak ada yang bertanya "
        "kepada mereka tentang keputusan ini, yang diambil dengan sangat cepat "
        "dan tanpa pemberitahuan sebelumnya."
    ),
    "vi": (
        "Hội đồng thành phố đã thông qua kế hoạch sau nhiều tháng tranh luận, và "
        "người dân trong khu vực nói rằng không ai hỏi ý kiến họ về quyết định "
        "này, một quyết định được đưa ra rất nhanh và không báo trước cho họ."
    ),
    "sv": (
        "Kommunfullmäktige godkände planen efter flera månaders debatt, och de "
        "boende i området sa att ingen hade frågat dem något om beslutet, som "
        "fattades mycket snabbt och utan att de hade fått veta det i förväg."
    ),
    "da": (
        "Byrådet godkendte planen efter flere måneders debat, og beboerne i "
        "området sagde, at ingen havde spurgt dem om noget vedrørende "
        "beslutningen, som blev truffet meget hurtigt og uden at de havde fået "
        "besked på forhånd."
    ),
}


@pytest.mark.parametrize("lang", sorted(UNSUPPORTED_SENTENCES))
def test_romanian_indonesian_vietnamese_swedish_and_danish_are_detected(lang):
    text = UNSUPPORTED_SENTENCES[lang]
    assert count_words(text) >= 25
    assert detect_language(text) == lang


@pytest.mark.parametrize("lang", sorted(UNSUPPORTED_SENTENCES))
def test_romanian_indonesian_vietnamese_swedish_and_danish_are_unsupported(lang):
    """They have no fit, so they must be reported rather than scored."""
    assert language_support(detect_language(UNSUPPORTED_SENTENCES[lang])) == (
        "unsupported"
    )


# Issue #141: Catalan shares most of its commonest function words (no de la el
# un en al que una del) with Spanish, so it read as Spanish, a supported
# language, and was scored under the Spanish calibration. Written to differ
# in topic and register, not to pass.
CATALAN_SENTENCES = [
    (
        "El consell municipal va aprovar el pla després de diversos mesos de "
        "debat, i els veïns del barri van dir que ningú no els havia preguntat "
        "res sobre aquesta decisió, que es va prendre molt de pressa i sense "
        "avisar-los amb temps."
    ),
    (
        "Barcelona és la capital de Catalunya i la segona ciutat més gran "
        "d'Espanya, amb una població d'uns un milió sis-cents mil habitants, i "
        "és coneguda arreu del món per la seva arquitectura i la seva cuina."
    ),
    (
        "La llengua catalana es parla a Catalunya, al País Valencià, a les Illes "
        "Balears, a Andorra i a una part d'Aragó, i té més de deu milions de "
        "parlants que l'utilitzen cada dia."
    ),
    (
        "Els investigadors de la universitat han descobert que alguns dels "
        "ocells que viuen al delta de l'Ebre canvien les seves rutes migratòries "
        "a causa de l'escalfament del clima."
    ),
    (
        "No podem continuar així, perquè si no canviem la manera de treballar, "
        "tot el projecte acabarà fracassant i haurem perdut molts mesos d'esforç "
        "sense cap resultat que valgui la pena."
    ),
    (
        "Aquesta recepta és molt senzilla: només cal barrejar la farina amb els "
        "ous i la llet, deixar reposar la massa una hora i després coure-la a "
        "foc lent en una paella."
    ),
]


@pytest.mark.parametrize("text", CATALAN_SENTENCES)
def test_catalan_is_detected_and_unsupported(text):
    assert count_words(text) >= 25
    assert detect_language(text) == "ca"
    assert language_support(detect_language(text)) == "unsupported"


SPANISH_SENTENCES = [
    (
        "No es el momento de la discusión en el parlamento, porque el presidente "
        "del gobierno ha dicho que el debate de los presupuestos se aplazará "
        "hasta el próximo mes."
    ),
    (
        "Me dijo que no vendría a la cena porque estaba cansado, pero al final "
        "apareció a las diez con una botella de vino y un pastel que había "
        "comprado en la pastelería de la calle."
    ),
    (
        "La nueva línea de tren unirá el centro de la ciudad con un barrio de la "
        "periferia, y no se espera que las obras terminen antes de que acabe el "
        "año que viene."
    ),
    (
        "Los investigadores de la universidad han descubierto que algunos de los "
        "pájaros que viven en el delta del río cambian sus rutas de migración a "
        "causa del calentamiento del clima."
    ),
]


@pytest.mark.parametrize("text", SPANISH_SENTENCES)
def test_spanish_is_still_spanish(text):
    """no de la el un en al are listed for Catalan too, so they now vote for both;
    the Spanish-only words (los, se, las, por, con, para, su, lo, y) must still win."""
    assert count_words(text) >= 25
    assert detect_language(text) == "es"
    assert language_support("es") == "supported"


def test_czech_is_not_mistaken_for_polish():
    """The regression that mattered: pl is calibrated, so a wrong pl here meant
    Czech text was scored under the Polish fit instead of flagged."""
    assert detect_language(UNCALIBRATED_SENTENCES["cs"]) != "pl"


def test_polish_is_still_polish():
    text = (
        "Rada miasta zatwierdziła plan po kilku miesiącach dyskusji, a mieszkańcy "
        "powiedzieli, że nikt ich o to nie zapytał przed podjęciem decyzji, która "
        "została przyjęta bardzo szybko."
    )
    assert detect_language(text) == "pl"
    assert language_support("pl") == "supported"


def test_dutch_is_still_dutch():
    """hu shares de/is/van with nl, so the Hungarian list must not outvote it."""
    text = (
        "De gemeenteraad heeft het plan na enkele maanden van discussie "
        "goedgekeurd, en de bewoners zeiden dat niemand hen daarover had gevraagd "
        "voordat het besluit werd genomen."
    )
    assert detect_language(text) == "nl"
