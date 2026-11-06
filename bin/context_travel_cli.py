"""CT4 command line access to the shared, bounded context travel query core."""

import argparse
import importlib.util
import sys
from pathlib import Path


def _query_module():
    path = Path(__file__).resolve().with_name("context_travel_query.py")
    spec = importlib.util.spec_from_file_location("context_travel_cli_query", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_query = _query_module()
MAX_FRAME_BYTES = 131072
HELP = ("usage: context_travel_cli.py --config ABSOLUTE_PATH "
        "[--format json|text] {overview,brief,explain,changes,capabilities}\n"
        "Read one bounded JSON argument object from stdin; write one result to stdout.\n")


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise _query.QueryError("invalid command arguments")


def main(argv=None, stdin=None, stdout=None, stderr=None):
    """Run one query; only --config can supply startup bindings."""
    input_stream = sys.stdin if stdin is None else stdin
    output_stream = sys.stdout if stdout is None else stdout
    error_stream = sys.stderr if stderr is None else stderr
    arguments = sys.argv[1:] if argv is None else list(argv)
    if arguments in (["--help"], ["-h"]):
        if hasattr(output_stream, "buffer"):
            output_stream.buffer.write(HELP.encode("utf-8"))
        else:
            try:
                output_stream.write(HELP)
            except TypeError:
                output_stream.write(HELP.encode("utf-8"))
        output_stream.flush()
        return 0
    parser = _Parser(prog="context-travel", add_help=False)
    parser.add_argument("--config", required=True)
    parser.add_argument("--format", choices=("json", "text"), default="json")
    parser.add_argument("operation")
    try:
        options = parser.parse_args(arguments)
        config = _query.load_config(options.config)
        if options.operation not in _query.OPERATIONS:
            raise _query.QueryError("unknown operation")
        raw = (input_stream.buffer if hasattr(input_stream, "buffer") else input_stream).read(
            _query.MAX_INPUT_BYTES + 1)
        if type(raw) is str:
            raw = raw.encode("utf-8")
        args = {} if options.operation == "capabilities" and not raw.strip() else _query.parse_json(raw)
        result = _query.run_query(config, options.operation, args)
        if options.format == "text":
            rendered = _query.render_text(result, max_bytes=config["max_output_bytes"])
            output = rendered.encode("utf-8") + b"\n"
        else:
            output = _query.canonical_bytes(result) + b"\n"
        if len(output) > MAX_FRAME_BYTES:
            raise _query.QueryError("CLI response exceeds frame limit")
        if hasattr(output_stream, "buffer"):
            output_stream.buffer.write(output)
        else:
            try:
                output_stream.write(output)
            except TypeError:
                output_stream.write(output.decode("utf-8"))
        output_stream.flush()
        return 0
    except (ValueError, TypeError, OSError, UnicodeError, RecursionError):
        error_stream.write("context travel query failed\n")
        error_stream.flush()
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
