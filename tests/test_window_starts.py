from app.engines.base import LARGE_MODEL_MAX_WINDOWS, MAX_WINDOWS, window_starts


def test_texts_that_fit_keep_every_window():
    assert window_starts(1200, 510, 256) == list(range(0, 1200, 256))
    assert window_starts(256 * MAX_WINDOWS, 510, 256) == list(
        range(0, 256 * MAX_WINDOWS, 256)
    )


def test_long_texts_get_a_bounded_even_sample_from_start_to_end():
    starts = window_starts(5200, 510, 256)
    assert len(starts) == MAX_WINDOWS
    assert starts[0] == 0 and starts[-1] == 5200 - 510
    assert starts == sorted(set(starts))
    gaps = {b - a for a, b in zip(starts, starts[1:], strict=False)}
    assert max(gaps) - min(gaps) <= 1


def test_large_models_read_long_texts_in_at_most_four_side_by_side_windows():
    starts = window_starts(3000, 510, 510, LARGE_MODEL_MAX_WINDOWS)

    assert starts == [0, 830, 1660, 2490]
    assert window_starts(1200, 510, 510, LARGE_MODEL_MAX_WINDOWS) == [0, 510, 1020]
