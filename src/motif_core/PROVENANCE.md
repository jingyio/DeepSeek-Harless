# MotifAgent runtime subset

Adapted from the frozen `MotifAgent-ATC26-Artifact` source snapshot.
Its `SOURCE_LOCK.json` pins the upstream development source at commit
`c73849cfe8d27e3bb3b932dbc70c84fa34c980e6` (tag
`taubench-semantic-readset-20260910`) and frozen-tree SHA-256
`f54adb3f324514b5e4c4f43f236fc36213c62636996d589819f979da98749e5c`.
The artifact checkout has a separate Git HEAD; the source commit is identified
through this lock, not by `git show` in the artifact checkout. The snapshot
passed `python3 scripts/verify_source_lock.py` on 2026-09-25. Source files:

- `motif_agent/runtime/context_manager.py`
- `motif_agent/runtime/evidence.py`
- `motif_agent/runtime/observation.py`
- `motif_agent/runtime/dependencies.py`
- `motif_agent/agent/handoff.py`
- `motif_agent/offline/motif_miner.py` (added as a trimmed, candidate-only miner;
  TauBench trajectory loader and CLI removed, trace normalization adapted for
  DSH's paired tool events)

The runtime subset initially changed only package import paths. SSS later
adapted `evidence.py` and `dependencies.py` to key cached results by each
node's evidence version and verified parent signatures, and to enforce
active negative guards after parameter flow. The offline miner was trimmed
and adapted for SSS; the original artifact was not modified. The copied code remains under its
Apache-2.0 license in `LICENSE`. SSS's office adapter calls the runtime
classes and functions directly;
the artifact's TauBench-specific general `MotifExecutor` has not yet been ported.

SSS later added `offline/trace_compiler.py` and `read_executor.py` as a
conservative read-only adaptation of the frozen operatorizer, dependency
compiler and MotifExecutor control path. These are new SSS implementations,
not verbatim copies. The compiler needs distinct training task traces,
explicit parameter-source provenance and a separate held-out trace before the
read-only artifact can execute. It does not cover the frozen system's full
connector, parallel, write, negative-motif or serving functionality.

SSS then extended this read-only slice to declared collection entry parameters
for cross-source retrieval. `src/workflows/research_retrieval_tools.py` is an SSS
tool adapter: it keeps the existing deterministic retrieval algorithm while
the compiled Motif owns source-snapshot dependency and execution control.

`offline/failure_evolution.py` is an SSS extension inspired by EvoGraph's
versioned structural revision idea. A failed operator produces a
privacy-minimal effective-binding signature. Independent failure replays,
contrasting success, and a separate task-quality review record are required
before an exact-input negative guard can be activated. The read executor
checks active guards after parameter flow and before a cached result or tool
call. A versioned registry tracks activation and rollback; only its currently
active guards are loaded. Proposal and replay-candidate statuses never affect
execution.

`offline/library_builder.py`, `offline/repeat_compiler.py`, and `controller.py`
are SSS adaptations of the frozen `offline/motif_dag_builder.py`,
`offline/connector_table.py`, `offline/motif_skill_operatorizer.py`,
`runtime/plan_matchers.py`, and `runtime/motif_executor.py` control flow. They
compile a library from independent traces and held-out tasks, annotate the
observed serial order separately from verified parameter edges, match a
requested output against certified motifs, execute through the migrated
dependency solver, and suspend/reenter through typed handoffs. The repeat
compiler promotes exact source-list reads, or a bounded subset frontier where
every observed call declares that source and an independent held-out task
also selects a subset. The runtime hands that candidate list to the semantic
port and validates the selected values before reading. It does not port write
operators, parallel execution, or open-world planning. The frozen source was
not edited.

`offline/link_compiler.py` is a further SSS extension. It promotes an observed
observed connector to an executable read dependency only when an explicitly
attributed scalar parameter transfer repeats in independent training tasks
and an unseen task, with no unknown or failed tool between the motifs.
`controller.py` builds an acyclic Motif graph from these edges, binds each
successor from current predecessor output, and suspends or reenters at any
missing parameter. It supports chains and joins without a hop count limit.
It does not execute intervening observed tools without certified dependencies,
or yet cover write operations and top-level semantic workflow nodes.

The online DSH path now keeps deterministic parameter programs inside each
exported Motif skill. `online_skill_runtime.mjs` validates these bounded
programs against certified transfer edges and executes them in the core;
the DSH adapter only observes host events and emits approved tool calls.
Field transfer is a skill binding rather than a separate DAG node.

SSS now adds a bounded dynamic-code extension in `pure_code.py` and
`offline/dynamic_code_nodes.py`. A proposed pure expression is checked against
two training task traces and one held-out task, then becomes a signed code
node in a two-tool Motif skill. `dependencies.py` and the online skill runtime
execute it before the dependent read. This extension is SSS code, not a copy
of the frozen MotifAgent artifact; it currently handles one scalar result
and does not authorize general Python programs.
