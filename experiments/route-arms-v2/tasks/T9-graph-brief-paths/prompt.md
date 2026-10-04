# Task: Add shortest dependency paths to graph_brief

`bin/graph_brief.py` is an offline reader for an already-produced graphify `graph.json`. It must continue to never invoke graphify or any other external CLI. Add a path-finding subcommand over the graph it already reads.

## Required behaviour

1. Add a `paths START END` subcommand. It reads the same graph format as `brief`, accepts `--graph PATH` with the same default, and prints the shortest dependency path or paths from `START` to `END`.
2. Add options `--direction {forward,reverse,both}` (default `forward`), `--max-hops N` (default `8`), `--max-paths N` (default `20`), and `--json`. `--max-hops` must be a non-negative integer. `--max-paths` must be a positive integer. Invalid values use argparse's normal status 2.
3. Node lookup is deterministic and exact. A query first matches node ids exactly after stringifying each node's `id`. If exactly one id matches, use it. If more than one id matches, exit 2 with an ambiguity error. Only when no id matches, match the query exactly against node `label`; if exactly one labelled node with an id matches, use it; if more than one matches, exit 2 with an ambiguity error; if none matches, exit 2 with a not-found error. Nodes without an `id` are never valid endpoints.
4. Edge direction is explicit. `forward` follows each link from stringified `source` to stringified `target`; `reverse` follows target to source; `both` allows either direction. Ignore links whose `source` or `target` is missing or whose endpoint id is not present in the node list. Ignore the top-level graph `directed` flag for this subcommand.
5. Compute all shortest simple paths within `--max-hops`. Cycles must not loop forever and must not produce paths with repeated node ids. If `START` and `END` resolve to the same id, the result is the single zero-hop path even when `--max-hops 0`.
6. Break ties deterministically: neighbour expansion is by lexicographic node id, and the final set of shortest paths is sorted lexicographically by the full tuple of node ids before applying `--max-paths`.
7. On success in text mode, print exactly:
   `shortest paths from <start-id> to <end-id> (hops=<H>, count=<TOTAL>, direction=<D>):`
   followed by one line per displayed path:
   `  <INDEX>. <id1> -> <id2> -> <id3>`
   For a zero-hop path, the path line is just the single id. `INDEX` starts at 1. If not every shortest path is displayed because of `--max-paths`, append exactly:
   `  ... <REMAINING> more shortest path(s) not shown (increase --max-paths)`
8. On success with `--json`, print `json.dumps(payload, indent=2, sort_keys=True)` where payload has exactly these top-level keys: `direction`, `end`, `hops`, `max_hops`, `path_count`, `paths`, `shown_path_count`, `start`, and `truncated`. `start` and `end` are objects with `id` and `label`. `paths` is a list of displayed paths, each a list of node id strings. `path_count` is the total number of shortest paths before truncation, `shown_path_count` is the length of `paths`, and `truncated` is true iff `shown_path_count < path_count`.
9. If no path exists within the hop limit, exit 1. Text mode prints exactly `no path from <start-id> to <end-id> within <N> hops (direction=<D>)`. JSON mode prints the same sorted/indented JSON style with exactly `{"direction": <D>, "end": <end-id>, "error": "no-path", "max_hops": <N>, "message": <message>, "start": <start-id>}`.
10. Lookup errors exit 2. A not-found error prints exactly `node not found for query '<query>' (lookup checks exact id first, then exact label)`. An ambiguity error prints exactly `ambiguous node query '<query>' matched <COUNT> <ids|labels>:` followed by one sorted candidate id per line prefixed with two spaces. In JSON mode, these errors print sorted/indented objects with `error`, `message`, and `query`; ambiguity errors also include `candidates`.
11. Missing, corrupt, non-UTF-8, or shape-invalid graph files keep the existing `load_graph` behaviour and exit codes/messages used by `brief`: missing graph exits 0 with the existing "no graph at ..." message; parse/shape errors exit 2. Do not add tracebacks.
12. Existing `brief` and `demo` output and JSON must remain unchanged.

## Scope and rules

- You may change `bin/graph_brief.py` and add or update unit tests under `tests/` only.
- Python is stdlib-only; do not add dependencies, do not use pytest, and do not invoke `graphify`, `copilot`, `codex`, `claude`, `agent`, or other external CLIs.
- This module only reads a `graph.json`; do not add subprocess, shell, network, or home-directory access.
- Do not hardcode prices, model ids, pricing dates, or assumptions from pricing files.
- Add unit tests for id/label lookup, ambiguity, edge direction, cycles, disconnected nodes, hop limits, deterministic tie ordering, text output, JSON output, malformed edges, and unchanged `brief` behaviour.
- Run from the repo root and keep green: `python3 -m unittest discover -s tests -p test_graph_brief.py`. If you add another graph-brief test module, it must also pass with `python3 -m unittest discover -s tests -p 'test_graph_brief*.py'`.
