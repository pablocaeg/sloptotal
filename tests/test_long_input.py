import uuid

from app.analyzer import fit_to_limit
from app.database import create_report, get_report, init_database


def test_short_text_is_untouched():
    assert fit_to_limit("A short paragraph.", limit=100) == "A short paragraph."


def test_long_text_is_cut_at_a_word_boundary():
    text = "word " * 30
    fitted = fit_to_limit(text, limit=52)
    assert len(fitted) <= 52
    assert fitted.endswith("word")
    assert text.startswith(fitted)


def test_text_without_spaces_is_cut_at_the_limit():
    assert fit_to_limit("x" * 200, limit=50) == "x" * 50


async def test_a_report_keeps_the_whole_text_and_the_submitted_length():
    await init_database()
    report_id = uuid.uuid4().hex[:12]
    text = "sentence number {} of a long essay. " * 200
    await create_report(
        report_id,
        uuid.uuid4().hex,
        "text",
        "s",
        text,
        len(text.split()),
        23,
        input_chars=250_000,
    )
    report = await get_report(report_id)
    assert report.text_excerpt == text
    assert report.input_chars == 250_000
