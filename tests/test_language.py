import pytest

from app.language import count_words, detect_language

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
