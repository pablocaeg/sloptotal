"""Benchmark per-engine speed to find bottlenecks."""
import sys, time
sys.path.insert(0, "/root/sloptotal")

AI_TEXT = (
    "Artificial intelligence has transformed numerous industries in recent years, "
    "fundamentally reshaping the way we approach complex problems. From healthcare to finance, "
    "the applications of machine learning and deep learning have proven to be remarkably versatile. "
    "One of the most significant developments in this field has been the emergence of large language "
    "models, which have demonstrated an unprecedented ability to generate human-like text. These models "
    "are trained on vast corpora of text data, enabling them to capture the nuances of language in ways "
    "that were previously thought to be the exclusive domain of human cognition. The implications of this "
    "technology are far-reaching, raising important questions about the nature of creativity and authorship."
)

from app.analyzer import _engines

# Warm up models
print("Warming up models...")
t0 = time.time()
for key, engine in _engines:
    engine.analyze(AI_TEXT)
print(f"Warmup done in {time.time()-t0:.1f}s\n")

# Clear cache between runs
from app.engines.gpt2_cache import clear_caches
clear_caches()

# Benchmark each engine individually
print(f"{'Engine':<28s} {'Time':>8s}  {'Score':>6s}")
print("-" * 50)

timings = []
for key, engine in _engines:
    clear_caches()  # Force fresh computation to measure real time
    t1 = time.time()
    result = engine.analyze(AI_TEXT)
    elapsed = time.time() - t1
    timings.append((key, engine.name, elapsed, result.score))
    print(f"{engine.name:<28s} {elapsed:>7.3f}s  {result.score:>5.3f}")

print("-" * 50)
total_sequential = sum(t for _, _, t, _ in timings)
print(f"{'Total (sequential)':<28s} {total_sequential:>7.3f}s")

# Now benchmark with shared cache (realistic scenario)
print("\n--- With GPT-2 cache sharing ---")
clear_caches()
t_start = time.time()

# First, time just the GPT-2 forward pass
from app.engines.gpt2_cache import get_gpt2_outputs, get_distil_outputs
t_gpt2 = time.time()
get_gpt2_outputs(AI_TEXT)
t_gpt2 = time.time() - t_gpt2

t_distil = time.time()
get_distil_outputs(AI_TEXT)
t_distil = time.time() - t_distil

print(f"GPT-2 Medium forward pass: {t_gpt2:.3f}s")
print(f"DistilGPT-2 forward pass:  {t_distil:.3f}s")

# Now time each engine with cache warm
gpt2_engines = []
classifier_engines = []
heuristic_engines = []

for key, engine in _engines:
    t1 = time.time()
    engine.analyze(AI_TEXT)
    elapsed = time.time() - t1

    if key in ("perplexity", "cross_perplexity", "gltr", "log_rank", "diveye", "fast_detectgpt", "binoculars", "burstiness"):
        gpt2_engines.append((engine.name, elapsed))
    elif key.startswith("classifier"):
        classifier_engines.append((engine.name, elapsed))
    else:
        heuristic_engines.append((engine.name, elapsed))

print(f"\nGPT-2 dependent engines (with cache):")
for name, t in sorted(gpt2_engines, key=lambda x: -x[1]):
    print(f"  {name:<28s} {t:.3f}s")

print(f"\nClassifier engines:")
for name, t in sorted(classifier_engines, key=lambda x: -x[1]):
    print(f"  {name:<28s} {t:.3f}s")

print(f"\nHeuristic engines:")
for name, t in sorted(heuristic_engines, key=lambda x: -x[1]):
    print(f"  {name:<28s} {t:.3f}s")

# Simulate parallel execution
import concurrent.futures
clear_caches()

# Pre-warm GPT-2 cache
get_gpt2_outputs(AI_TEXT)
get_distil_outputs(AI_TEXT)

t_parallel = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=21) as ex:
    futures = [ex.submit(engine.analyze, AI_TEXT) for _, engine in _engines]
    concurrent.futures.wait(futures)
t_parallel = time.time() - t_parallel

# Full parallel including GPT-2 warmup
clear_caches()
t_full = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=21) as ex:
    futures = [ex.submit(engine.analyze, AI_TEXT) for _, engine in _engines]
    concurrent.futures.wait(futures)
t_full = time.time() - t_full

print(f"\n--- Parallel execution ---")
print(f"All 20 engines parallel (cache warm): {t_parallel:.3f}s")
print(f"All 20 engines parallel (cold start):  {t_full:.3f}s")
print(f"Speedup vs sequential: {total_sequential/t_full:.1f}x")
