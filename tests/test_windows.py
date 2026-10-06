import threading
import time

from app.analyzer import SHORT_LANE_WORDS, lane_for
from app.engines.base import FairLock, score_in_windows


class _WordTokenizer:
    def encode(self, text, add_special_tokens=False):
        return text.split()

    def decode(self, ids, skip_special_tokens=True):
        return " ".join(ids)


def test_a_text_that_fits_is_scored_once_as_a_whole():
    seen = []
    score = score_in_windows(
        "a b c",
        _WordTokenizer(),
        lambda t: seen.append(t) or 0.5,
        FairLock(),
        window=10,
    )
    assert score == 0.5 and seen == ["a b c"]


def test_a_long_text_is_the_mean_of_its_windows():
    text = " ".join(str(i) for i in range(110))
    scores = iter([0.2, 0.4, 0.6, 0.8])
    score = score_in_windows(
        text,
        _WordTokenizer(),
        lambda t: next(scores),
        FairLock(),
        window=30,
        stride=30,
        max_windows=4,
    )
    assert abs(score - 0.5) < 1e-9


def test_the_lock_is_handed_on_in_arrival_order():
    lock = FairLock()
    order = []
    lock.__enter__()

    def wait_then_record(name):
        with lock:
            order.append(name)

    threads = []
    for name in ("first", "second", "third"):
        t = threading.Thread(target=wait_then_record, args=(name,))
        t.start()
        threads.append(t)
        time.sleep(0.05)
    lock.__exit__(None, None, None)
    for t in threads:
        t.join(timeout=2)

    assert order == ["first", "second", "third"]


def test_texts_up_to_the_threshold_take_the_short_lane():
    assert lane_for(" ".join(["word"] * SHORT_LANE_WORDS)) == "short"
    assert lane_for(" ".join(["word"] * (SHORT_LANE_WORDS + 1))) == "full"
