"""Concurrent first requests must never see a half-loaded model.

Regression: requests arriving while the preloader was still loading got a
model without its tokenizer ('NoneType' object has no attribute 'encode'),
so four classifiers silently scored 0.0 and the report came back "Clean".
"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.engines import classifier_fakespot, classifier_tmr, perplexity
from app.model_pool import ModelPool


@pytest.fixture
def slow_tmr_loader(monkeypatch):
    calls = []

    def fake_replica():
        calls.append(1)
        time.sleep(0.2)
        return object(), object()

    monkeypatch.setattr(classifier_tmr, "_load_one_replica", fake_replica)
    monkeypatch.setattr(classifier_tmr, "_model", None)
    monkeypatch.setattr(classifier_tmr, "_tokenizer", None)
    monkeypatch.setattr(classifier_tmr, "_pool_size", 1)
    return calls


def test_concurrent_first_loads_see_a_complete_model(slow_tmr_loader):
    with ThreadPoolExecutor(max_workers=8) as ex:
        pairs = list(ex.map(lambda _: classifier_tmr._load_model(), range(8)))
    assert all(model is not None and tok is not None for model, tok in pairs)
    assert len({id(model) for model, _ in pairs}) == 1
    assert len(slow_tmr_loader) == 1


def test_pool_acquire_waits_for_initialization():
    pool = ModelPool(lambda: (time.sleep(0.2), "model")[1], pool_size=2, name="t")
    got = []

    def request():
        with pool.acquire(timeout=5) as replica:
            got.append(replica)

    t = threading.Thread(target=request)
    t.start()  # arrives before any replica exists
    pool.initialize()
    pool.initialize()  # idempotent: a second call must not add replicas
    t.join()
    assert got == ["model"]
    assert pool._pool.qsize() == 2


def test_loads_of_different_models_never_overlap(monkeypatch):
    """transformers' from_pretrained is not thread-safe across models: running
    two at once can leave a tied lm_head randomly initialised."""
    active, peak, lock = [0], [0], threading.Lock()

    def tracked(value):
        def load(*args, **kwargs):
            with lock:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.1)
            with lock:
                active[0] -= 1
            return value

        return load

    for mod in (classifier_tmr, classifier_fakespot):
        monkeypatch.setattr(mod, "_load_one_replica", tracked((object(), object())))
        monkeypatch.setattr(mod, "_model", None)
        monkeypatch.setattr(mod, "_tokenizer", None)
        monkeypatch.setattr(mod, "_pool_size", 1)
    monkeypatch.setattr(perplexity, "_model", None)
    monkeypatch.setattr(
        perplexity.GPT2TokenizerFast, "from_pretrained", tracked(object())
    )
    monkeypatch.setattr(
        perplexity.GPT2LMHeadModel, "from_pretrained", tracked(_FakeModel())
    )

    loaders = [
        classifier_tmr._load_model,
        classifier_fakespot._load_model,
        perplexity._load_model,
    ]
    with ThreadPoolExecutor(max_workers=3) as ex:
        list(ex.map(lambda f: f(), loaders))
    assert peak[0] == 1


class _FakeModel:
    def eval(self):
        return self

    def to(self, device):
        return self


def test_acquire_waits_out_a_slow_first_load():
    """The first boot downloads weights for minutes; requests must wait for the
    pool, not fail after the 30 s contention timeout (seen on first Docker run)."""
    pool = ModelPool(lambda: (time.sleep(0.5), "model")[1], pool_size=1, name="slow")
    loader = threading.Thread(target=pool.initialize)
    loader.start()
    time.sleep(0.05)  # the preloader is mid-download
    with pool.acquire(timeout=0.1) as replica:  # far shorter than the load
        assert replica == "model"
    loader.join()


def test_acquire_loads_the_pool_itself_when_nothing_preloaded():
    pool = ModelPool(lambda: "model", pool_size=2, name="lazy")
    with pool.acquire() as replica:
        assert replica == "model"


def test_failed_load_raises_and_is_retried():
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("network down")
        return "model"

    pool = ModelPool(flaky, pool_size=1, name="flaky")
    with pytest.raises(OSError):
        with pool.acquire():
            pass
    with pool.acquire() as replica:
        assert replica == "model"
