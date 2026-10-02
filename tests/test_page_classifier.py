from app.page_classifier import classify_page_type

LONG_TEXT = "Clear prose explains the subject with useful details. " * 6


def test_short_page_is_not_scoreable():
    result = classify_page_type("Too short.")
    assert (result["type"], result["scoreable"]) == ("short", False)


def test_hub_from_high_list_density():
    result = classify_page_type(
        LONG_TEXT,
        html_features={"list_items": 30, "paragraph_count": 4},
    )
    assert (result["type"], result["scoreable"]) == ("hub", False)


def test_hub_from_many_navigation_links():
    result = classify_page_type(
        LONG_TEXT,
        html_features={"nav_links": 21, "paragraph_count": 4},
    )
    assert (result["type"], result["scoreable"]) == ("hub", False)


def test_landing_from_bold_text():
    result = classify_page_type(
        LONG_TEXT,
        html_features={"bold_count": 6, "paragraph_count": 4},
    )
    assert (result["type"], result["scoreable"]) == ("landing", False)


def test_landing_from_form():
    result = classify_page_type(
        LONG_TEXT,
        html_features={"form_count": 2, "paragraph_count": 4},
    )
    assert (result["type"], result["scoreable"]) == ("landing", False)


def test_landing_from_code_blocks():
    result = classify_page_type(
        LONG_TEXT,
        html_features={"code_blocks": 4},
    )
    assert (result["type"], result["scoreable"]) == ("reference", True)


def test_reference_from_colon_density():
    text = "parameter: value and default: string. " * 8
    result = classify_page_type(text, html_features={"code_blocks": 1})
    assert (result["type"], result["scoreable"]) == ("reference", True)


def test_reference_from_tech_pattern():
    text = (
        LONG_TEXT
        + "returns, param,  type, default, args, kwargs, raises, str, int, float, bool, None, True, False, dict, tuple, list"
    )
    result = classify_page_type(text, html_features={"code_blocks": 1})
    assert (result["type"], result["scoreable"]) == ("reference", True)


def test_reference_from_code_fences():
    text = LONG_TEXT + "``` ``` ``` ```"
    result = classify_page_type(text)
    assert (result["type"], result["scoreable"]) == ("reference", True)


def test_article_is_default():
    result = classify_page_type(LONG_TEXT)
    assert (result["type"], result["scoreable"]) == ("article", True)
