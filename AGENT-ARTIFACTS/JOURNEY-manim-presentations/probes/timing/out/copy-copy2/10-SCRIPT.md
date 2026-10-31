# Mixing Deluxe

Optimizing every GPU minute in production mixing proxy models. Full narration and animation checkpoints for Minh’s technical company presentation. Source references and corrections are in the private notes; these are not audience-facing text.

Target: 20 minutes. This readable copy is generated from transcript.json. Edit that source and rerun this exporter.

## 01 — Mixing Deluxe

Transition: Open from black; retain the same dark canvas into Context.

### 01.1 · Title

**Say**

Mixing Deluxe: optimizing every GPU minute in production mixing proxy models.

**Show**

Reveal the title, then its subtitle. One small mix card becomes a GPU rectangle, establishing the shapes used throughout.

**On screen:** Mixing Deluxe · Optimizing every GPU minute in production mixing proxy models

## 02 — Context

Transition: Connected reveal from the title.

### 02.1 · What a swarm does

**Say**

A mixing study starts with different proportions of web, code, math, and other data. Each mix becomes a small model. We train it, evaluate it, and use those scores to decide which mixes are worth trying next.

**Show**

Spread a few candidate cards across the frame. Each has a different colored proportion bar and the same 104M parameter label. Feed one card into a CPU circle, then a training GPU rectangle and an evaluation GPU rectangle.

**On screen:** 104M · mix · TorchTitan training · Olmes evaluation

**Private note:** The 104M card is the representative D0384_L03/Llama-3 model, not the smallest-model configuration used by the Zephon benchmarks. Sources: Gantavya report; old swarm_train_eval and torchtitan_train_eval graphs.

### 02.2 · First project

**Say**

My  first project was working on these trainer and evaluator jobs: moving from TorchTitan plus Olmes to an integrated PyTorch train-eval job.

**Show**

Box one row of CPU, training GPU and evaluation GPU, labeled First project: Move to pure pytorch. Leave the rest of the graph visible but subdued.

**On screen:** First project: Move to pure pytorch

## 03 — Project 1: Production-Ready Single Proxy Trainer

Transition: Move the boxed row to the top, then show the single job below it..

### 03.1 · One job

**Say**

The first change was to make training and evaluation one job. Keep the model in the same process, give it a small, clear interface, and remove the handoff between two separate systems.

**Show**

Move the boxed row to the top and disappear the rest of the workflow. Keep the purple box, remove its label, draw an arrow down, and show a single CPU and one GPU rectangle labeled PyTorch train-eval, with Single job to do train-eval below. The title stays at the top of the next slides.

**On screen:** Project 1: Production-Ready Single Proxy Trainer · PyTorch train-eval · Single job to do train-eval

**Private note:** The integrated path uses transformers model components and PyTorch. 'PyTorch' does not imply no transformers dependency. Treat the card as a capability illustration, not the benchmark setup.

### 03.2 · Small and reliable

**Say**

It scales to whatever GPUs are available with distributed data parallelism. It's merely two thousand lines, so it's easy to debug in production. The tests give very strong quality guarantees, so it just works: we trained a swarm with TorchTitan and with this job and compared them. And it's fully self-contained, eval suite included, so it's reliable to ship with no silent drift.

**Show**

Grey out the starting workflow; keep the arrow and the single job central. Five benefit cards point out from the job, green payoffs beneath.

**On screen:** Distributed data parallelism | scale to what’s available · Merely 2K lines | Easy to debug in prod · Tests provide very strong quality guarantees | it just works! · torchtitan parity guarantees by training a swarm with torchtitan and this · Fully self-contained including the eval suite | reliable to ship, no silent drift

**Private note:** Source scope: train.py, eval.py, models.py, eval_suite.py total 3,269 lines at the audit; orchestration/support files excluded. PRs 11776 and 12239 contain reported parity/evaluation verification. Do not fabricate measured curve samples; use a schematic comparison or source data.

### 03.3 · Highly configurable

**Say**

All of it is driven by one input. It supports multiple Llama sizes. It reads pretokenized or raw text, from one stream, two, or sixty. And the compute backend is configurable: it's just a field: pick Kubernetes or Modal, the GPU, and the count. That makes it flexible to any production design and environment, and it saves FDE time.

**Show**

Clear the benefits. An INPUT code box shows the job's input schema, with an elbow arrow into the central job; four benefits stack on the right with no connectors. When Adaptive compute backend appears, the ModalBackendOption and KubernetesBackendOption lines in the INPUT box are highlighted.

**On screen:** green|flexible to any prod design and environment, save FDE time · white|Multiple llama flavors · green|Input pretokenized, raw, or any arbitrary mix of 1, 2, or 60 · rainbow|Configurable compute backend|KubernetesBackendOption, ModalBackendOption, GPU, and count

```python
class MixingCandidateSeedTrainEvalInputs:
    queue: str
    backend_option: ModalBackendOption
                  | KubernetesBackendOption
    mix: dict[str, float]  # 1, 2, or 60 streams
    tokenizer: str | None  # None: pretokenized
    model: str = "swarm_d0384_l03"  # 7 Llama sizes
    steps: int = 7630
    eval_every: int | None = 500

ModalBackendOption(gpu="H100!:2")
KubernetesBackendOption(gpus=2)
```

**Private note:** A single run uses one stream kind; do not draw a hybrid raw-plus-pretokenized run. Historical per-run backends were ModalBackendOption/KubernetesBackendOption; new swarm API names appear later.

### 03.4 · Single job speedup

**Say**

Putting training and evaluation into one job gave roughly a 1.25-times speedup.

**Show**

Clear the benefits and show Two jobs, then an arrow to Single job, then a second arrow to the green ~1.25x speedup. The counter then docks on the right.

**On screen:** Two jobs · Single job · 1.25x speedup

### 03.5 · Speedup Counter

**Say**

That is the first number on the Speedup Counter. Let's go crazy.

**Show**

Everything clears and the 1.25x speedup becomes a yellow-bordered Speedup Counter box in the center, with Let's go crazy! below it. The box then moves to the top right and stays there for the rest of the talk.

**On screen:** 1.25x · Let's go crazy!

## 04 — Optimization 1: Compiled + Dense Eval loops

Transition: The counter stays at the top right; the title is fixed..

### 04.1 · What BPB measures

**Say**

Evaluation asks how well the model predicts a continuation after reading its context. Take a toy continuation: the letter A, one UTF-8 byte. If the model gives its token probability one quarter, that costs two bits: minus log base two of one quarter. Two bits divided by one byte gives two bits per byte. Across a longer continuation, add the prediction bits and divide by its bytes. Lower is better.

**Show**

Show context “Next letter:” in the context color and continuation “A” in the continuation color. This toy tokenizer emits A as one token. Carry p(A)=0.25 into −log₂(0.25)=2 bits, and the actual UTF-8 byte 0x41 into a one-byte denominator. Resolve 2 bits / 1 byte = 2 BPB. Keep context bytes and context predictions outside both accumulators; then fan out to longer pairs.

**On screen:** Optimization 1: Compiled + Dense Eval loops · A · 0x41 · 1 byte · p(A) = 0.25 · −log₂(0.25) = 2 bits · 2 bits / 1 byte = 2 BPB

**Private note:** The numerical example is deliberately constructed, not a measured model prediction; A is one token in the toy and one UTF-8 byte. General BPB is negative summed natural-log likelihood divided by ln(2) and continuation UTF-8 bytes. Per-task result is mean document BPB, not a byte-weighted aggregate.

### 04.2 · A curve, not one score

**Say**

We do this across thousands of pairs, at checkpoints during training and once more at the end. Each evaluation gives another point on the learning curve.

**Show**

Show training segments interrupted by small evaluation segments. Each evaluation emits a point into a BPB-versus-training-tokens curve. Hold the final curve, with no invented numerical y-values.

**On screen:** training tokens · BPB

**Private note:** Mid-training sample evaluation defaults to every 500 steps and up to 50 documents per task; full evaluation follows the final step. The curve is schematic unless actual source scores are supplied.

### 04.3 · The old handoff

**Say**

The old workflow exported a Hugging Face checkpoint, started a separate evaluator, and loaded the model again. Olmes then ran its evaluation tasks through the inference backend. That handoff added setup and repeated model-loading work around the actual scoring.

**Show**

Temporarily contrast export, external storage, evaluator startup, reload and task preparation with the integrated job. Trace the same weights through each handoff.

**On screen:** export · startup · reload · score

**Private note:** Verified old graph scores the final checkpoint and supports optional separate conversion. Olmes defaults to vLLM. Do not claim every old periodic evaluation paused the same live training job or that a model reload happened for each task.

## 05 — Optimization 2: Custom training kernels

Transition: The counter stays at the top right; the title is fixed..

### 05.1 · Normal flow

**Say**

Normally the LM head writes logits for the whole microbatch, cross-entropy reads them back to compute the loss, and calling backward makes PyTorch compute the logit gradients and then the two matmuls for dH and dW.

**Show**

Left: the four steps of the normal flow, GPU steps as purple rectangles and CPU steps as yellow circles.

**On screen:** Optimization 2: Custom training kernels · Normal flow · gpu|GPU · forward|LM-head matmul writes the full microbatch of logits · gpu|GPU · forward|Cross-entropy reads the logits and computes the loss · cpu|CPU call|loss.backward() starts backward · gpu|GPU · backward|PyTorch computes the logit gradients, then two matmuls give dH and dW

### 05.2 · QuACK base flow

**Say**

QuACK loops over token chunks. For each chunk it computes the logits, computes the loss while overwriting those logits with their gradients, and runs the dH matmul and most of the dW matmuls. Backward then only scales the prepared gradients and finishes the last dW matmul.

**Show**

Right: the four steps of the QuACK base flow beside the normal flow.

**On screen:** QuACK base flow · cpu|CPU orchestration|Loop over token chunks and launch the GPU work · gpu|GPU · QuACK forward|Per chunk: compute logits; compute the loss and overwrite the logits with their gradients; run the dH matmul and most dW matmuls · cpu|CPU call|loss.backward() starts backward · gpu|GPU · QuACK backward|Scale the prepared gradients and finish the last dW matmul

### 05.3 · Kernel speedup

**Say**

Less memory traffic, a bounded working set, and a compiled training path give another substantial gain. That brings the counter to about two times.

**Show**

Bring the counter forward, update 1.44× to 2× only on this click, then dock it.

**On screen:** 1.44x · 2x

## 06 — Optimization 3: Make Zephon live tokenization go brrr

Transition: Deliberate black chapter break, then reveal the data pipelines.

### 06.1 · Live tokenization

**Say**

Live tokenization lets a mixing proxy change tokenizers without rebuilding every dataset. Pretokenized IDs still take the direct route.

**Show**

Reveal one fixed Zephon canvas: a live-text raw-shard-to-GPU lane, a separate token-ID lane that bypasses the tokenizer, three framed regions below, and the persistent approximate 2× rail. The rate rows and feature cards remain unrevealed.

**On screen:** LIVE TEXT · raw shards · tokenizer · PRETOKENIZED · token IDs · tokenizer bypass · approx. 2×

**Private note:** Keep this as a capability explanation, not a measured DeepSeek GPU-hour equality claim.

### 06.2 · Starved models

**Say**

The old live-text path fetched, encoded and packed on the CPU. Small proxy models consume batches fast, so gaps there leave GPU time idle.

**Show**

On the same canvas, outline the live queue and add a GPU-waiting callout; leave the pretokenized bypass and panel frames in place.

**On screen:** GPU waiting

**Private note:** Pipeline drawing is conceptual; the hub is orchestration, not a mandatory serial payload stage. Do not claim a specific global op order for all Zephon configurations.

### 06.3 · The measured gap

**Say**

On Text++ with four H100s, HF live delivered 2.77 and 2.72 million tokens a second; ready batches reached 5.34 and 5.31.

**Show**

Reveal the ready-batch ceiling and HF-live paired rates in the left Text++ panel. Keep the v1 row and right-panel rates hidden.

**On screen:** Text++ · MTok/s · ready ceiling 5.34 / 5.31 · HF live 2.77 / 2.72

**Private note:** PR 77 main-v1-tokenize-mtextpp.png: HF legend 2.77/2.72, ceiling 5.34/5.31. These are trainer throughput/ready-batch ceiling, not standalone loader benchmarks.

### 06.4 · A faster tokenizer

**Say**

Faster tokenizer engines, including the v1 work and Luke's arrow-tokenize, reduced encoding cost. The bottleneck moved into the rest of the loader.

**Show**

Retire the waiting callout, pulse the live tokenizer, and move the amber focus from queue to pack on the same pipeline.

**On screen:** pack

**Private note:** Credit Luke's arrow-tokenize without asserting it is the engine used by PR 77. The standalone 50–100× figure lacks a source in the requested PRs, so do not invent that numeric label.

### 06.5 · Faster is not finished

**Say**

The v1 live path rose to 3.19 and 3.20 on that same Text++ setup, better but below its ready-batch ceiling.

**Show**

Reveal the v1 live 3.19 / 3.20 paired rate beneath HF live in the fixed Text++ panel.

**On screen:** v1 live 3.19 / 3.20

**Private note:** PR 77 plot v1 repetitions 3.19/3.20. Do not compare this directly as a time series with the later double-stream experiment.

### 06.6 · The mission

**Say**

End-to-end A/B throughput mattered more than isolated tokenization speed. The two paired live rows show the remaining gap.

**Show**

Remove the pack focus and outline the two Text++ live rows together for the end-to-end A/B comparison.

**On screen:** HF live · v1 live

**Private note:** Specific A/B measurements in PRs 69/70/71/77 support the mechanisms. Counter figures remain Minh's approximate cumulative observations.

### 06.7 · Garbage collection

**Say**

One fix freezes the hub's long-lived startup objects before data flows. On a separate single-stream test, median full-GC pauses fell from 432 to 132 milliseconds.

**Show**

Reveal the Freeze hub objects card inside the center panel. Above it, show the two-line note that explicitly scopes the 432 to 132 ms median full-GC pause to a separate single-stream test.

**On screen:** Freeze hub objects · single stream · median full-GC pause · 432 → 132 ms

**Private note:** PR 69: this is cyclic garbage collection, not refcount-triggered scanning. GC and refcounting continue. Single-stream median full-GC pause reported 432ms to 132ms; do not generalize to all mixes.

### 06.8 · Packing integers

**Say**

Packing now emits int64 positions directly, avoiding a per-batch conversion and a torch CPU thread-pool wakeup.

**Show**

Retire the temporary GC note and reveal the int64 positions card beside the freeze card.

**On screen:** int64 positions

**Private note:** PR 70 concerns position indices, not token compression. Its ~96% result is the re-fed live-batch ceiling, not a standalone full-pipeline result.

### 06.9 · Cache lock

**Say**

Cache hits read shared state concurrently. Misses and missing-file repair still coordinate under locks.

**Show**

Reveal the concurrent cache-hit card; keep its coordinate-misses subtitle visible so the missed-shard path is not presented as lock-free.

**On screen:** Cache hits concurrent · coordinate misses

**Private note:** PR 71. Do not animate all cache operations as lock-free. Reported microbench cache-hit improvement is 5–7×, distinct from end-to-end training gains.

### 06.10 · Encode without fighting the workers

**Say**

The v1 wrapper encodes once per text, preventing nested tokenization workers from competing with data-loader workers.

**Show**

Reveal the one-encode-per-text card. The four mechanisms now fill the center grid without moving the pipelines or rate panels.

**On screen:** One encode per text

**Private note:** PR 77: encode_batch ignores the RAYON_NUM_THREADS constraint in the observed v1 path. Keep unsupported tokenizer options out of the talk.

### 06.11 · Live catches up

**Say**

In a separate double-stream run on four H100s, lock-free live loading reached 4.98 and 5.06 million tokens per second, near the 5.17 and 4.95 ready-batch measurements.

**Show**

Reveal the four source-paired rows in the already titled double-stream panel: ready ceiling, pretokenized, live with lock, and live lock-free. Keep the Text++ panel visible as a distinct workload, with no fabricated time series.

**On screen:** double stream · MTok/s · ready ceiling 5.17 / 4.95 · pretokenized 4.59 / 4.57 · live with lock 4.29 / 4.36 · live lock-free 4.98 / 5.06

**Private note:** PR 71 body and cache-hit-m2.png. Live lock-free plot legend 4.98/5.06, pretokenized 4.59/4.57, ceiling 5.17/4.95. This is not a universal guarantee and is not the Text++ plot from the previous slide.

### 06.12 · Research benefit

**Say**

That closes much of the old convenience penalty: we can try another tokenizer while retaining the research workflow.

**Show**

Change only the live-lane tokenizer label to new tokenizer. The pretokenized token-ID bypass, measured panels, and mechanism cards stay fixed.

**On screen:** new tokenizer · tokenizer bypass

**Private note:** This states the capability and intended benefit, not a controlled measurement of equal DeepSeek GPU-hours.

### 06.13 · Four times

**Say**

In the talk's approximate cumulative counter, this is the step from about two times to about four times.

**Show**

Morph the persistent center-bottom narrative counter from approx. 2× to approx. 4× in place. The source-paired rate panels remain visible and distinct.

**On screen:** 2x · 4x

### 06.14 · The money shot

**Say**

Here is the whole story. A single job, packed and compiled evaluation, custom kernels, and live tokenization took one 104-million-parameter proxy model's train-eval job to about four times faster.

**Show**

The Speedup Counter sits at 4x in the center with the title 104M proxy model train-eval job speedup above it. Four colored elbow arms point out to a summary of each optimization.

**On screen:** 104M proxy model train-eval job speedup · Single job · 1.25x · Packed, compiled eval · 1.44x · Kernels + compilation · 2x · Live tokenization · 4x

### 06.15 · Counter returns

**Say**

Now the question is what happens when you run five hundred of these.

**Show**

The summary clears and the counter returns to the top right.

## 07 — Current Swarm Workflow

Transition: Intentional black break; start the wider workflow picture.

### 07.1 · One model versus a swarm

**Say**

So one model is much better fed, and the train-eval job is much faster. But what about a swarm of five hundred models at once?

**Show**

On this click show the original 500-models meme from assets/500-models-meme.png at large readable size. Preserve the two-panel joke and its existing models caption; do not replace it with a generic grid. Keep the completed approximate 4× counter docked. The next click opens the workflow drawing.

**On screen:** 500 models

**Private note:** Original embedded image kix.f352mx7ipx3y in the Google Doc, immediately after Show this on click. Downloaded and personally inspected with page6 context.

### 07.2 · One workflow per model

**Say**

It fans out into a train-eval workflow for every model, each with its own orchestration.

**Show**

Following the original workflow drawing, grow branches from the single coordinator into six representative per-model CPU circles at staggered horizontal start positions. Label repeat500times. Show the branches and circles before any GPU segments.

**On screen:** per-model workflows · 500 models

### 07.3 · Trainer startup

**Say**

Each training job first pays GPU startup.

**Show**

On this click extend a red startup segment from each branch CPU circle into its training GPU rectangle. Keep a shared left-to-right time axis and hold before training.

**On screen:** GPU startup

**Private note:** Startup GPU occupancy is schematic for this depicted workflow, not every deployment.

### 07.4 · Training

**Say**

Then it trains the model.

**Show**

On this click append a bright training segment after each trainer startup. Move tokens through the GPU rectangles. Preserve the earlier CPU and startup regions.

**On screen:** train

### 07.5 · Export

**Say**

Then it exports the checkpoint for the separate evaluator.

**Show**

Append the first red Export interval to each training GPU timeline, as in the original drawing, and carry the same checkpoint toward the evaluator. These are schematic elapsed workflow phases; any CPU-writing close-up must preserve the drawing’s red overhead band.

**On screen:** export · checkpoint

**Private note:** The original drawing explicitly shows Startup/Train/Export followed by Startup/Eval/Export. Preserve that visible sequence. Diagram durations are schematic and do not claim every export operation executes on GPU.

### 07.6 · Evaluator startup

**Say**

The evaluation job pays another startup and loads those weights.

**Show**

On this click reveal the evaluator GPU rectangle and its red startup segment. Move the stored checkpoint into it; stop before scoring.

**On screen:** evaluator startup · reload

### 07.7 · Evaluation

**Say**

Only then does it score. On a large swarm, this orchestration, startup, export, and evaluation handoff repeats hundreds of times.

**Show**

Append the light useful-work Eval interval after the second red Startup interval, following the original drawing. Keep all preceding phases visible. Hold before the drawing’s final Export interval.

**On screen:** eval · repeated overhead

### 07.8 · The costs

**Say**

This is expensive and inflexible. CPU scheduling clogs the swarm, every model pays GPU hours for repeated overhead, it only fits fixed-capacity clusters, it can't burst, and a claimed GPU can't be reused without scheduling again.

**Show**

The finished workflow slides left and five red costs appear on the right.

**On screen:** CPU scheduling clogs swarm · GPU hours paying repeated overhead · Only compatible with fixed-cap clusters · Not scalable to bursted compute · Claimed GPU can't reuse, need schedule anew

### 07.9 · Clear

**Say**

So let's rebuild this workflow from the ground up.

**Show**

Everything clears except the Speedup Counter in the top right.

## 08 — [In Progress] A well-oiled swarm machine

Transition: One continuous scene: new workflow, four feature slides, status, and the final counter zoom..

### 08.1 · A queue and warm workers

**Say**

In the new workflow, one CPU fills a task queue with many tasks, and a stack of warm, cache-reuse workers pulls from it. Finished train checkpoints and evals land on the right.

**Show**

CPU, a full task queue, a stack of warm workers and a finished-swarm box.

### 08.2 · Tasks flow (loop)

**Say**

Tasks keep flowing from the queue to whichever worker is free, and the queue refills. This slide loops for as long as you watch.

**Show**

Looped: each worker takes the next queued task and the queue refills.

### 08.3 · Add a worker

**Say**

Need more speed? Burst a new worker onto the top of the stack.

**Show**

A worker is added on top of the stack.

### 08.4 · Four workers (loop)

**Say**

With four workers, tasks go out faster. Same loop.

**Show**

Looped with four workers.

### 08.5 · Two workers die

**Say**

Two workers die. Machines get preempted, and nothing falls over.

**Show**

Two workers are crossed out and removed.

### 08.6 · Tasks keep going (loop)

**Say**

The remaining workers keep taking tasks and the swarm finishes anyway.

**Show**

Looped with the two remaining workers.

### 08.7 · Async CPU threads

**Say**

Every non-GPU step, like exporting and uploading checkpoints, runs on asynchronous CPU threads, so the GPU keeps training.

**Show**

GPU lane trains candidates back to back while CPU threads export and upload in the shadow of the next training.

**On screen:** Async CPU threads for all non-GPU work ensures every GPU second goes to training

### 08.8 · Warm caches

**Say**

Between candidates, the warm job keeps the tokenizer, the compiled model, and the data shards, so only the first candidate pays for setup.

**Show**

Candidate rows: the first pays tokenizer, compile and dataloader setup; later rows show thin cached bars and finish sooner.

**On screen:** Tokenizer, compiled model, and dataloader caching saves even more time between candidates

### 08.9 · Minimal work

**Say**

The head node decides the minimum work each swarm model needs: a full train, a resumed train, or just a new eval.

**Show**

A head CPU branches to three candidates with progress bars: full train, resume train, new eval only.

**On screen:** Head node determines the minimal amount of work each swarm model needs to do

### 08.10 · Ergonomic API

**Say**

One line of config selects the GPU and count on Modal, or sends the same swarm to a Kubernetes queue. The same actor works on both, and you just pass a list of training configs while we handle the infrastructure.

**Show**

INPUT: the algorithmic-mixing swarm call from the first victory lap, with the Modal backend line highlighted and an elbow arrow to the Kubernetes alternative; two short notes on the right.

**On screen:** Ergonomic API with|one line config|to select GPU and switch between bursty Modal compute|or fixed-size Karpenter · backend=KubernetesFanOut(queue=H100_QUEUE, width=12) · Datology Actor that works on both K8s & Modal · Simply pass in a list of training configs (archs, sizes, mixes, etc.), we handle the infra

```python
draws = np.random.default_rng(1).dirichlet(np.ones(5), 30)
search = start(SwarmProxyTrainEvalConfig(
    swarm=[config(dict(zip(GROUPS, d))) for d in draws],
    repeats=2,
    ranker=Ranker(compare=COMPARE),
    backend=ModalFanOut(gpu=GpuType.H100, width=12),
))
```

### 08.11 · Algorithmic mixing

**Say**

Algorithmic mixing is one swarm call over thirty random mixes. The steps that aren't swarm calls shrink to a few lines each.

**Show**

The first victory lap's code, with the non-swarm steps reduced to short comments.

**On screen:** Algorithmic mixing in · just a few lines

```python
# 5 lines: 30 random mixes of text++'s five stream groups
draws = np.random.default_rng(1).dirichlet(np.ones(5), 30)

# Step 1. Train the random mixes, twice each.
search = start(SwarmProxyTrainEvalConfig(
    swarm=[config(dict(zip(GROUPS, d))) for d in draws],
    repeats=2,
    ranker=Ranker(compare=COMPARE),
    backend=ModalFanOut(gpu=GpuType.H100, width=12),
))

# Steps 2-3. ~10 lines: is the batch readable? Fit one log-linear
#   law per task and check it out of sample.
# Step 4. optimize_mixture(...): the law's one-shot argmin, p*.
# Step 5. Validate p*, uniform, text++'s split and the best random
#   mix on fresh seeds (repeats=4, seed=2).
# Step 6. Report: predicted vs measured, each with its error bar.
```

### 08.12 · Mixing phase workflow

**Say**

Phasing is two functions. The parent trains on the first mix until the learning rate decays, and the child continues the same model on a new mix.

**Show**

The phasing lap's parent and child functions from SYSTEM.md.

**On screen:** Mixing phase workflow in · just a few lines

```python
# Phase 1: text++'s own mix, until the LR decay begins.
def parent(model):
    n, k, full = split(model)
    return ProxyTrainEvalConfig(model=model, mix=P1, steps=k,
                                lr_schedule=full[:k], checkpoints=Checkpoints.ALL)

# Phase 2: the same model, optimizer and LR continue on a new mix.
def child(model, parent_id, mix):
    n, k, full = split(model)
    return ProxyTrainEvalConfig(model=model, mix=mix,
                                start_from=RunRef(train_id=parent_id), steps=n - k,
                                lr_schedule=full[k:], checkpoints=Checkpoints.FINAL)

# 5 lines: split() cuts one LR schedule where its decay begins.
# Step 2. 30 sampled phase-2 mixes branch from the small parent at once.
```

### 08.13 · Working today and still to do

**Say**

Here is what is working today, and what is left.

**Show**

Left: what has been shown and works. Right: what is left, some labeled research.

**On screen:** 10–20 swarm models on K8s and Modal;Warm actors, cached setup;Async export threads;One-line backend switch · Resume and eval-only planning;Results returned from start();EWMA model merging|[research];MoE swarms|[research];Multiphase mixing|[research];Get Luke's review

### 08.14 · Full swarms

**Say**

And that is the full five-hundred-model mixing swarm: four times, and a lot more.

**Show**

The counter zooms to the center showing 4x + A LOT, labeled Full 500-model mixing swarms.

**On screen:** Full 500-model mixing swarms · 4x + A LOT

## 09 — So what?

Transition: Intentional clean break from code to outcomes.

### 09.1 · GPU-hours cut

**Say**

GPU-hours are cut by more than half on proxy training swarms, thanks to a stack rebuilt from the ground up: fully compiled train and eval loops, GPU parallelism, custom kernels, and packed-tensor evals. That directly saves customer compute.

**Show**

The counter docks and the headline appears with the first point.

**On screen:** So what? · GPU-hours cut by more than half on proxy training swarms · Compiled train and eval loops, GPU parallelism, custom kernels and packed-tensor evals, directly saving customer compute

### 09.2 · One config line

**Say**

One config line adapts 500-model swarms to bursty Modal or fixed-capacity Karpenter, with a pool of warm actors that have caches and async operations, so every GPU second goes to training. This replaces 500 separate Flyte workers that each paid their own scheduling and startup overhead.

**Show**

Second point.

**On screen:** One config line: bursty Modal or fixed-capacity Karpenter · Warm actors with caches and async ops put every GPU second into training, replacing 500 Flyte workers that each paid scheduling and startup overhead

### 09.3 · Live tokenization

**Say**

Live tokenization in Zephon is optimized to match pretokenized dataloading speed and saturate even the most data-hungry small proxy models, which simplifies research flows.

**Show**

Third point.

**On screen:** Live tokenization in Zephon matches pretokenized dataloading speed · Saturates even the most data-hungry small proxy models, simplifying research flows

### 09.4 · The swarm API

**Say**

A tiny swarm API, Model1 through Model500, is in progress. It bundles these improvements and also supports MoEs, model merging, multi-phase mixing, and scaling-law studies, speeding up research iteration and setting up algorithmic mixing in product. I'm excited to help out on both.

**Show**

Fourth point, tagged in progress.

**On screen:** swarm(Model1, Model2, ..., Model500): a tiny API · Bundles these improvements and adds MoEs, model merging, multi-phase mixing and scaling-law studies, speeding up research iteration and setting up algorithmic mixing in product. Excited to help out on both! · [in progress]

## 10 — Questions

Transition: Clean black break after the workflow ending.

### 10.1 · Questions

**Say**

Questions.

**Show**

Fade in a single centered question mark on true black and hold.

**On screen:** ?
