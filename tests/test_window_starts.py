from app.engines.base import MAX_WINDOWS, window_starts


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
    gaps = {b - a for a, b in zip(starts, starts[1:])}
    assert max(gaps) - min(gaps) <= 1
