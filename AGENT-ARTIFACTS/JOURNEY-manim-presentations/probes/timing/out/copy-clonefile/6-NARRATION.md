# Mixing Deluxe — narration

Generated from transcript.json. Slide and checkpoint headings are navigation aids, not spoken text.

## 01 — Mixing Deluxe

### 01.1 · Title

Mixing Deluxe: optimizing every GPU minute in production mixing proxy models.

## 02 — Context

### 02.1 · What a swarm does

A mixing study starts with different proportions of web, code, math, and other data. Each mix becomes a small model. We train it, evaluate it, and use those scores to decide which mixes are worth trying next.

### 02.2 · First project

My  first project was working on these trainer and evaluator jobs: moving from TorchTitan plus Olmes to an integrated PyTorch train-eval job.

## 03 — Project 1: Production-Ready Single Proxy Trainer

### 03.1 · One job

The first change was to make training and evaluation one job. Keep the model in the same process, give it a small, clear interface, and remove the handoff between two separate systems.

### 03.2 · Small and reliable

It scales to whatever GPUs are available with distributed data parallelism. It's merely two thousand lines, so it's easy to debug in production. The tests give very strong quality guarantees, so it just works: we trained a swarm with TorchTitan and with this job and compared them. And it's fully self-contained, eval suite included, so it's reliable to ship with no silent drift.

### 03.3 · Highly configurable

All of it is driven by one input. It supports multiple Llama sizes. It reads pretokenized or raw text, from one stream, two, or sixty. And the compute backend is configurable: it's just a field: pick Kubernetes or Modal, the GPU, and the count. That makes it flexible to any production design and environment, and it saves FDE time.

### 03.4 · Single job speedup

Putting training and evaluation into one job gave roughly a 1.25-times speedup.

### 03.5 · Speedup Counter

That is the first number on the Speedup Counter. Let's go crazy.

## 04 — Optimization 1: Compiled + Dense Eval loops

### 04.1 · What BPB measures

Evaluation asks how well the model predicts a continuation after reading its context. Take a toy continuation: the letter A, one UTF-8 byte. If the model gives its token probability one quarter, that costs two bits: minus log base two of one quarter. Two bits divided by one byte gives two bits per byte. Across a longer continuation, add the prediction bits and divide by its bytes. Lower is better.

### 04.2 · A curve, not one score

We do this across thousands of pairs, at checkpoints during training and once more at the end. Each evaluation gives another point on the learning curve.

### 04.3 · The old handoff

The old workflow exported a Hugging Face checkpoint, started a separate evaluator, and loaded the model again. Olmes then ran its evaluation tasks through the inference backend. That handoff added setup and repeated model-loading work around the actual scoring.

## 05 — Optimization 2: Custom training kernels

### 05.1 · Normal flow

Normally the LM head writes logits for the whole microbatch, cross-entropy reads them back to compute the loss, and calling backward makes PyTorch compute the logit gradients and then the two matmuls for dH and dW.

### 05.2 · QuACK base flow

QuACK loops over token chunks. For each chunk it computes the logits, computes the loss while overwriting those logits with their gradients, and runs the dH matmul and most of the dW matmuls. Backward then only scales the prepared gradients and finishes the last dW matmul.

### 05.3 · Kernel speedup

Less memory traffic, a bounded working set, and a compiled training path give another substantial gain. That brings the counter to about two times.

## 06 — Optimization 3: Make Zephon live tokenization go brrr

### 06.1 · Live tokenization

Live tokenization lets a mixing proxy change tokenizers without rebuilding every dataset. Pretokenized IDs still take the direct route.

### 06.2 · Starved models

The old live-text path fetched, encoded and packed on the CPU. Small proxy models consume batches fast, so gaps there leave GPU time idle.

### 06.3 · The measured gap

On Text++ with four H100s, HF live delivered 2.77 and 2.72 million tokens a second; ready batches reached 5.34 and 5.31.

### 06.4 · A faster tokenizer

Faster tokenizer engines, including the v1 work and Luke's arrow-tokenize, reduced encoding cost. The bottleneck moved into the rest of the loader.

### 06.5 · Faster is not finished

The v1 live path rose to 3.19 and 3.20 on that same Text++ setup, better but below its ready-batch ceiling.

### 06.6 · The mission

End-to-end A/B throughput mattered more than isolated tokenization speed. The two paired live rows show the remaining gap.

### 06.7 · Garbage collection

One fix freezes the hub's long-lived startup objects before data flows. On a separate single-stream test, median full-GC pauses fell from 432 to 132 milliseconds.

### 06.8 · Packing integers

Packing now emits int64 positions directly, avoiding a per-batch conversion and a torch CPU thread-pool wakeup.

### 06.9 · Cache lock

Cache hits read shared state concurrently. Misses and missing-file repair still coordinate under locks.

### 06.10 · Encode without fighting the workers

The v1 wrapper encodes once per text, preventing nested tokenization workers from competing with data-loader workers.

### 06.11 · Live catches up

In a separate double-stream run on four H100s, lock-free live loading reached 4.98 and 5.06 million tokens per second, near the 5.17 and 4.95 ready-batch measurements.

### 06.12 · Research benefit

That closes much of the old convenience penalty: we can try another tokenizer while retaining the research workflow.

### 06.13 · Four times

In the talk's approximate cumulative counter, this is the step from about two times to about four times.

### 06.14 · The money shot

Here is the whole story. A single job, packed and compiled evaluation, custom kernels, and live tokenization took one 104-million-parameter proxy model's train-eval job to about four times faster.

### 06.15 · Counter returns

Now the question is what happens when you run five hundred of these.

## 07 — Current Swarm Workflow

### 07.1 · One model versus a swarm

So one model is much better fed, and the train-eval job is much faster. But what about a swarm of five hundred models at once?

### 07.2 · One workflow per model

It fans out into a train-eval workflow for every model, each with its own orchestration.

### 07.3 · Trainer startup

Each training job first pays GPU startup.

### 07.4 · Training

Then it trains the model.

### 07.5 · Export

Then it exports the checkpoint for the separate evaluator.

### 07.6 · Evaluator startup

The evaluation job pays another startup and loads those weights.

### 07.7 · Evaluation

Only then does it score. On a large swarm, this orchestration, startup, export, and evaluation handoff repeats hundreds of times.

### 07.8 · The costs

This is expensive and inflexible. CPU scheduling clogs the swarm, every model pays GPU hours for repeated overhead, it only fits fixed-capacity clusters, it can't burst, and a claimed GPU can't be reused without scheduling again.

### 07.9 · Clear

So let's rebuild this workflow from the ground up.

## 08 — [In Progress] A well-oiled swarm machine

### 08.1 · A queue and warm workers

In the new workflow, one CPU fills a task queue with many tasks, and a stack of warm, cache-reuse workers pulls from it. Finished train checkpoints and evals land on the right.

### 08.2 · Tasks flow (loop)

Tasks keep flowing from the queue to whichever worker is free, and the queue refills. This slide loops for as long as you watch.

### 08.3 · Add a worker

Need more speed? Burst a new worker onto the top of the stack.

### 08.4 · Four workers (loop)

With four workers, tasks go out faster. Same loop.

### 08.5 · Two workers die

Two workers die. Machines get preempted, and nothing falls over.

### 08.6 · Tasks keep going (loop)

The remaining workers keep taking tasks and the swarm finishes anyway.

### 08.7 · Async CPU threads

Every non-GPU step, like exporting and uploading checkpoints, runs on asynchronous CPU threads, so the GPU keeps training.

### 08.8 · Warm caches

Between candidates, the warm job keeps the tokenizer, the compiled model, and the data shards, so only the first candidate pays for setup.

### 08.9 · Minimal work

The head node decides the minimum work each swarm model needs: a full train, a resumed train, or just a new eval.

### 08.10 · Ergonomic API

One line of config selects the GPU and count on Modal, or sends the same swarm to a Kubernetes queue. The same actor works on both, and you just pass a list of training configs while we handle the infrastructure.

### 08.11 · Algorithmic mixing

Algorithmic mixing is one swarm call over thirty random mixes. The steps that aren't swarm calls shrink to a few lines each.

### 08.12 · Mixing phase workflow

Phasing is two functions. The parent trains on the first mix until the learning rate decays, and the child continues the same model on a new mix.

### 08.13 · Working today and still to do

Here is what is working today, and what is left.

### 08.14 · Full swarms

And that is the full five-hundred-model mixing swarm: four times, and a lot more.

## 09 — So what?

### 09.1 · GPU-hours cut

GPU-hours are cut by more than half on proxy training swarms, thanks to a stack rebuilt from the ground up: fully compiled train and eval loops, GPU parallelism, custom kernels, and packed-tensor evals. That directly saves customer compute.

### 09.2 · One config line

One config line adapts 500-model swarms to bursty Modal or fixed-capacity Karpenter, with a pool of warm actors that have caches and async operations, so every GPU second goes to training. This replaces 500 separate Flyte workers that each paid their own scheduling and startup overhead.

### 09.3 · Live tokenization

Live tokenization in Zephon is optimized to match pretokenized dataloading speed and saturate even the most data-hungry small proxy models, which simplifies research flows.

### 09.4 · The swarm API

A tiny swarm API, Model1 through Model500, is in progress. It bundles these improvements and also supports MoEs, model merging, multi-phase mixing, and scaling-law studies, speeding up research iteration and setting up algorithmic mixing in product. I'm excited to help out on both.

## 10 — Questions

### 10.1 · Questions

Questions.
