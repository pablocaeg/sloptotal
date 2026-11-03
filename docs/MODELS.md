# What each engine costs

How much memory each of the 23 engines needs once its model is loaded, and how long it takes on a text of about 300
words, on CPU. The numbers come from [`benchmarks/bench_engine_costs.py`](../benchmarks/bench_engine_costs.py), which
measures every engine in its own fresh process.

## Measured on

Apple M5, 10 cores, 16 GB RAM, macOS (Darwin 25.5.0), Python 3.12.13, torch 2.14.1, CPU only. Each engine ran with **one
torch thread**, which is the default: every profile sets `SLOPTOTAL_TORCH_THREADS=1` (`app/autoconfig.py`). Latency is
the median of 12 different texts of 300 words each, taken from the human texts of the SlopBench corpus.

It was a laptop with other applications open: at the start of the run the load average was 3.2 and 4.9 GB of swap was
in use. Two complete runs agreed within 8 % on memory and within 7 % on latency, so read the memory figures to about
the nearest 100 MB. Numbers from another machine, thread count or text length will differ; the benchmark takes
`--threads` and `--runs`.

## The table

Memory is the peak resident size of the process after the model is loaded and has run once, minus the same process
before the load. The peak is used, not the current value, because under memory pressure the operating system pages
model weights out and the current value understates what the engine needs. The last column applies to the eight engines
that share one GPT-2 forward pass (see below).

| Engine | Model | Memory (MB) | Median latency (s) | With the shared pass cached (s) |
|---|---|---:|---:|---:|
| BERT-tiny RAID | `ShantanuT01/BERT-tiny-RAID` | 20 | 0.003 | |
| E5-Small | `MayZhou/e5-small-lora-ai-generated-detector` | 113 | 0.042 | |
| TMR Detector | `Oxidane/tmr-ai-text-detector` | 409 | 0.088 | |
| Fakespot | `fakespot-ai/roberta-base-ai-text-detection-v1` | 409 | 0.086 | |
| OpenAI Detector | `roberta-base-openai-detector` | 421 | 0.088 | |
| ChatGPT Detector | `Hello-SimpleAI/chatgpt-detector-roberta` | 411 | 0.088 | |
| SuperAnnotate | `SuperAnnotate/ai-detector-low-fpr` | 1,307 | 0.291 | |
| ReMoDetect | `hyunseoki/ReMoDetect-deberta` | 1,532 | 0.440 | |
| Desklib DeBERTa | `desklib/ai-text-detector-v1.01` | 1,528 | 0.441 | |
| Perplexity | `gpt2-medium` | 1,745 | 0.396 | < 0.001 |
| Log-Rank | `gpt2-medium` | 1,915 | 0.397 | 0.010 |
| GLTR | `gpt2-medium` | 1,906 | 0.393 | 0.010 |
| DivEye | `gpt2-medium` | 1,746 | 0.398 | 0.014 |
| Burstiness | `gpt2-medium` | 1,735 | 0.409 | 0.015 |
| Fast-DetectGPT | `gpt2-medium` | 1,972 | 0.433 | 0.039 |
| Binoculars | `gpt2-medium`, `distilgpt2` | 2,134 | 0.476 | < 0.001 |
| Cross-Perplexity | `gpt2-medium`, `distilgpt2` | 2,166 | 0.469 | < 0.001 |
| Linguistic Markers, Structural Analysis, Vocabulary Richness, Formulaic Patterns, Readability Uniformity, Sentiment & Hedging | none (regex and statistics) | 0 | 0.001 or less each | |

## Reading it

**The GPT-2 engines share one model and one forward pass.** Eight engines read the same GPT-2 Medium output through
`app/engines/gpt2_cache.py`, and Binoculars and Cross-Perplexity also read a DistilGPT-2 pass. In the server the model is
loaded once, so those eight together need about 2.2 GB, not eight times 1.9 GB (an estimate: Cross-Perplexity, which loads
both models, measures 2.2 GB alone). Their first column of latency includes the forward pass, about 0.4 s. When the pass is
already cached, which is the case for all but the first of them in a real report, the last column is what each one adds.

**Adding it up.** One copy of every model comes to about 8.3 GB: the sum of the rows above with the GPT-2 group counted
once (2.2 GB for the group, 0.02 + 0.11 + 0.41 + 0.41 + 0.42 + 0.41 for the small classifiers, 1.31 + 1.53 + 1.53 for the
large ones). That is an estimate from separate measurements; it was not measured as one process, and it leaves out the
server's own overhead. Run one after another on one thread, the 23 engines would take about 2.1 s for a 300-word text
(the classifiers add up to 1.6 s, the GPT-2 group about 0.55 s including the DistilGPT-2 pass). The server runs
engines concurrently, so wall-clock time per report is lower.

**Profiles change workers and replicas, not which engines run.** The lite profile's startup banner says "4 (lite mode)"
and `app/autoconfig.py` describes it as "4 fast engines only", but `SLOPTOTAL_LITE` is read by nothing except that
banner, and `_preload_models()` in `app/main.py` loads every model on every profile. So every profile holds all the
models above. What a profile changes is the worker counts and the number of replicas of four classifiers: TMR,
Fakespot, E5 and BERT-tiny. Each extra replica of those four costs about 0.95 GB (409 + 409 +
113 + 20 MB), and the performance profile uses two replicas when RAM is at least 32 GB.

**Disk.** The models total about 9.0 GB (one weight file each, plus tokenizers and configs). The first run downloads
them all.

**What was not measured.** A GPU, other thread counts and other text lengths: only 300 words, on CPU, with one thread.
The time to load each model is not in the table. The server loads the models in a background thread at startup
(`_preload_models`), so a request that arrives before that finishes waits for it.

## Reproducing it

```bash
pip install -r requirements.txt
python benchmarks/bench_engine_costs.py > engine-costs.md
```

The first run downloads every model (about 9 GB), so run it once beforehand if the download should not count. For
memory figures that mean something, close other applications first, and check that the machine is not swapping.
