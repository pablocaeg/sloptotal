"""
Shared GPT-2 forward pass cache.

Multiple engines need the same GPT-2 Large logits/loss for the same text.
Instead of each engine acquiring the lock and running its own forward pass,
they all call get_gpt2_outputs() which computes once and caches.

This turns 6 sequential forward passes into 1 — the single biggest speedup.
"""

import threading
from collections import OrderedDict

import torch

_cache_lock = threading.Lock()
_cache: OrderedDict[int, dict] = OrderedDict()
_MAX_CACHE = 5


def get_gpt2_outputs(text: str) -> dict:
    """
    Returns cached GPT-2 Large outputs for the given text.
    Dict keys: 'logits', 'loss', 'input_ids', 'n_tokens'
    All tensors are detached (no grad).
    """
    text_hash = hash(text)

    with _cache_lock:
        if text_hash in _cache:
            return _cache[text_hash]

    # Not cached — compute under the model lock
    from app.engines.perplexity import _load_model, _lock

    model, tokenizer = _load_model()

    with _lock:
        # Double-check after acquiring lock (another thread may have computed it)
        with _cache_lock:
            if text_hash in _cache:
                return _cache[text_hash]

        encodings = tokenizer(
            text, return_tensors="pt", truncation=True, max_length=1024
        )
        input_ids = encodings.input_ids
        n_tokens = input_ids.size(1) - 1

        if n_tokens < 5:
            result = {
                "logits": None,
                "loss": None,
                "input_ids": input_ids,
                "n_tokens": n_tokens,
            }
        else:
            # Forward pass on the model's device; results come back to the CPU so
            # the engines' post-processing is unchanged and the cache (up to 5
            # copies of 1024 x 50257 logits) never holds GPU memory.
            device_ids = input_ids.to(next(model.parameters()).device)
            with torch.no_grad():
                outputs = model(device_ids, labels=device_ids)
                result = {
                    "logits": outputs.logits.detach().cpu(),
                    "loss": outputs.loss.item(),
                    "input_ids": input_ids.detach(),
                    "n_tokens": n_tokens,
                }

    # Store in cache
    with _cache_lock:
        _cache[text_hash] = result
        while len(_cache) > _MAX_CACHE:
            _cache.popitem(last=False)

    return result


# Same pattern for DistilGPT-2
_distil_cache_lock = threading.Lock()
_distil_cache: OrderedDict[int, dict] = OrderedDict()


def get_distil_outputs(text: str) -> dict:
    """
    Returns cached DistilGPT-2 outputs: 'loss', 'input_ids', 'n_tokens'
    """
    text_hash = hash(text)

    with _distil_cache_lock:
        if text_hash in _distil_cache:
            return _distil_cache[text_hash]

    from app.engines.cross_perplexity import _distil_lock, _load_distil_model

    model, tokenizer = _load_distil_model()

    with _distil_lock:
        with _distil_cache_lock:
            if text_hash in _distil_cache:
                return _distil_cache[text_hash]

        encodings = tokenizer(
            text, return_tensors="pt", truncation=True, max_length=1024
        )
        input_ids = encodings.input_ids

        if input_ids.size(1) < 10:
            result = {
                "loss": None,
                "input_ids": input_ids,
                "n_tokens": input_ids.size(1) - 1,
            }
        else:
            device_ids = input_ids.to(next(model.parameters()).device)
            with torch.no_grad():
                outputs = model(device_ids, labels=device_ids)
                result = {
                    "loss": outputs.loss.item(),
                    "input_ids": input_ids.detach(),
                    "n_tokens": input_ids.size(1) - 1,
                }

    with _distil_cache_lock:
        _distil_cache[text_hash] = result
        while len(_distil_cache) > _MAX_CACHE:
            _distil_cache.popitem(last=False)

    return result


def clear_caches():
    """Call after analysis is complete to free memory."""
    with _cache_lock:
        _cache.clear()
    with _distil_cache_lock:
        _distil_cache.clear()
