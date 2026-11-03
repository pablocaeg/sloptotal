# Benchmarks

Speed, load and older accuracy scripts. They talk to a running instance
(`http://localhost:8000` by default, `SLOPTOTAL_URL` where supported) and write
their reports to `benchmarks/results/`. Run them from the repository root.

| Script | Measures |
|---|---|
| `bench_engines.py`, `bench_full.py`, `bench_realistic.py` | Per-engine latency and snippet accuracy, in-process |
| `bench_engine_costs.py` | Memory after load and median latency of each of the 23 engines, one fresh process per engine; its results are in [`docs/MODELS.md`](../docs/MODELS.md) |
| `bench_snippets.py` | Snippet-scan throughput, the browser-extension workload |
| `load_test.py` | CLI load generator (`--url`, `--concurrency`) |
| `concurrency_test.py`, `realistic_load_test.py` | Queue behaviour under concurrent and realistic mixed traffic |
| `eval_dataset.py`, `eval_hard.py`, `eval_urls.py`, `eval_diagnose.py` | Early accuracy runs on RAID and MAGE samples |

The accuracy numbers quoted in the README come from the newer, reproducible
harness in [`tests/eval/`](../tests/eval/), not from these scripts.

## Performance decisions

The scripts in [`perf/`](perf/) compare speed changes with their effect on
scores and verdicts. PRs [#62](https://github.com/pablocaeg/sloptotal/pull/62)
and [#63](https://github.com/pablocaeg/sloptotal/pull/63) are worked examples.

| Script | Measures |
|---|---|
| [`large_models.py`](perf/large_models.py) | Speed and accuracy of variants for the three large classifiers: Desklib, ReMoDetect and SuperAnnotate. |
| [`retime.py`](perf/retime.py) | Interleaved, shuffled timing of window plans; writes the combined plan's scores back into the `large_models.py` output. |
| [`decide.py`](perf/decide.py) | Critical-path latency (the slowest large model), per-engine score changes and final verdict changes after production calibration. |
| [`replay.py`](perf/replay.py) | End-to-end latency under production-shaped traffic, reporting p50, p90 and max by text-length band. |

Run `large_models.py`, then `retime.py`, then `decide.py` with the retiming
output as its third argument:

```bash
PYTHONPATH=. SLOPTOTAL_TORCH_THREADS=2 python benchmarks/perf/large_models.py texts.json large_models_out.json
PYTHONPATH=.:benchmarks/perf SLOPTOTAL_TORCH_THREADS=2 python benchmarks/perf/retime.py texts.json large_models_out.json retime_out.json
PYTHONPATH=. python benchmarks/perf/decide.py texts.json large_models_out.json retime_out.json
```

`texts.json` supplies the timing texts and the fixed accuracy set with baseline
engine scores. Then run `replay.py` against an instance with production settings
and `SLOPTOTAL_CACHE_ENABLED=false`. Its server address is currently hardcoded
to `http://127.0.0.1:8012`; it uses SlopBench texts from
`tests/eval/slopbench/corpus/` and a JSON list of production word counts in
`lengths.json`:

```bash
python benchmarks/perf/replay.py lengths.json 2.5 10 replay_out.json
```

Here `2.5` is requests per minute and `10` is the arrival period in minutes.
