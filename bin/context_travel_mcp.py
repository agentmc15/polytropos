"""CT4 bounded MCP stdio adapter for the shared context travel query core."""

import argparse
import importlib.util
import json
import sys
from pathlib import Path


PROTOCOL_VERSION = "2025-11-25"
MAX_FRAME_BYTES = 131072
MAX_FRAMES = 256
MAX_IDS = 256


def _query_module():
    path = Path(__file__).resolve().with_name("context_travel_query.py")
    spec = importlib.util.spec_from_file_location("context_travel_mcp_query", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_query = _query_module()
HELP = ("usage: context_travel_mcp.py --config ABSOLUTE_PATH\n"
        "Serve bounded MCP JSON-RPC 2.0 messages over UTF-8 stdio.\n"
        "Startup help exits before config loading; normal stdout contains protocol messages only.\n")


def _error(code, message, request_id=None):
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def _result(request_id, value):
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


def _write(stream, message):
    data = json.dumps(message, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    if len(data) > MAX_FRAME_BYTES:
        data = json.dumps(_error(-32603, "response exceeds limit"),
                          separators=(",", ":")).encode("utf-8") + b"\n"
    stream.write(data)
    stream.flush()


def _id(value):
    return ((type(value) is int and abs(value) <= (1 << 53) - 1) or
            (type(value) is str and 0 < len(value) <= 128
             and value == value.strip() and not any(ord(char) < 32 for char in value)
             and not _query._redact.scan(value)))


def _initialize_params(value):
    if type(value) is not dict or set(value) != {"protocolVersion", "capabilities", "clientInfo"}:
        return False
    version = value["protocolVersion"]
    if type(version) is not str or not version or len(version) > 32:
        return False
    caps = value["capabilities"]
    if type(caps) is not dict or not set(caps) <= {
            "experimental", "roots", "sampling", "elicitation", "tasks"} \
            or any(type(item) is not dict for item in caps.values()):
        return False
    if "roots" in caps:
        roots = caps["roots"]
        if not set(roots) <= {"listChanged"} or (
                "listChanged" in roots and type(roots["listChanged"]) is not bool):
            return False
    info = value["clientInfo"]
    if type(info) is not dict or not {"name", "version"} <= set(info) \
            or not set(info) <= {"name", "version", "title", "description", "websiteUrl", "icons"}:
        return False
    for key in ("name", "version", "title", "description", "websiteUrl"):
        if key in info and (type(info[key]) is not str or len(info[key]) > 512
                            or (key in ("name", "version") and not info[key])):
            return False
    if "icons" in info:
        icons = info["icons"]
        if type(icons) is not list or len(icons) > 16:
            return False
        for icon in icons:
            if type(icon) is not dict or "src" not in icon \
                    or not set(icon) <= {"src", "mimeType", "sizes"} \
                    or type(icon["src"]) is not str or len(icon["src"]) > 1024:
                return False
            if "mimeType" in icon and (type(icon["mimeType"]) is not str
                                       or len(icon["mimeType"]) > 128):
                return False
            if "sizes" in icon and (type(icon["sizes"]) is not list or len(icon["sizes"]) > 16
                                    or any(type(size) is not str or len(size) > 32
                                           for size in icon["sizes"])):
                return False
    return True


def _tools():
    # JSON Schema is intentionally closed at the top level. The shared core
    # applies the exact nested contract, digest, and configured-subject checks.
    definitions = []
    for name in _query.OPERATIONS:
        if name in ("overview", "brief"):
            optional = {"intent_links": {"type": "array"},
                        "acceptance_links": {"type": "array"},
                        "dependency_freshness": {"type": "array"}}
            assignment_required = ["repository_id", "checkout_id", "revision", "kit_path",
                                   "task_id", "assignment_id", "assignment_role", "question"]
            assignment_props = {key: {"type": "string"} for key in assignment_required
                                if key != "revision"}
            assignment_props["revision"] = {"type": ["string", "null"]}
            for key in ("source_state_ref", "source_ref", "acceptance_ref"):
                assignment_props[key] = {"type": ["object", "null"]}
            assignment = {"type": "object", "additionalProperties": False,
                          "required": assignment_required, "properties": assignment_props}
            schema = {"type": "object", "additionalProperties": False,
                      "properties": {"request": {"type": "object"},
                                     "assignment": assignment,
                                     "view": {"type": "object"}, **optional},
                      "oneOf": [
                          {"required": ["request"], "not": {"anyOf": [
                              {"required": ["assignment"]}, {"required": ["view"]}]}},
                          {"required": ["assignment"], "not": {"anyOf": [
                              {"required": ["request"]}, {"required": ["view"]}]}},
                          {"required": ["view"], "not": {"anyOf": [
                              {"required": [key]} for key in
                              ("request", "assignment", *optional)]}}]}
        elif name == "explain":
            schema = {"type": "object", "additionalProperties": False,
                      "required": ["view", "finding_id"],
                      "properties": {"view": {"type": "object"},
                                     "finding_id": {"type": ["string", "null"]}}}
        elif name == "changes":
            schema = {"type": "object", "additionalProperties": False,
                      "required": ["before", "after"],
                      "properties": {"before": {"type": "object"},
                                     "after": {"type": "object"}}}
        else:
            schema = {"type": "object", "additionalProperties": False}
        description = ("Read-only context travel " + name +
                       ("; use assignment for a first call, sealed request or view for reuse"
                        if name in ("overview", "brief") else ""))
        definitions.append({"name": name,
                            "description": description,
                            "inputSchema": schema})
    return definitions


def serve(config, stdin, stdout):
    """Serve one bounded binary LF JSON-RPC session; calls run synchronously."""
    try:
        policy = _query._config(config)
    except (ValueError, TypeError, RecursionError):
        raise _query.QueryError("invalid startup config") from None
    seen_ids = set()
    initialized = False
    announced = False
    for _ in range(MAX_FRAMES):
        frame = stdin.readline(MAX_FRAME_BYTES + 1)
        if not frame:
            break
        if type(frame) is str:
            frame = frame.encode("utf-8")
        if len(frame) > MAX_FRAME_BYTES:
            _write(stdout, _error(-32000, "request exceeds limit"))
            break
        if not frame.endswith(b"\n"):
            _write(stdout, _error(-32700, "invalid frame"))
            break
        try:
            message = _query.parse_json(frame, max_bytes=MAX_FRAME_BYTES)
        except ValueError:
            _write(stdout, _error(-32700, "invalid JSON"))
            continue
        if type(message) is not dict or message.get("jsonrpc") != "2.0" \
                or type(message.get("method")) is not str:
            _write(stdout, _error(-32600, "invalid request"))
            continue
        method = message["method"]
        has_id = "id" in message
        request_id = message.get("id")
        if has_id:
            if not _id(request_id):
                _write(stdout, _error(-32600, "invalid request ID"))
                continue
            if request_id in seen_ids:
                _write(stdout, _error(-32600, "duplicate request ID", request_id))
                continue
            if len(seen_ids) >= MAX_IDS:
                _write(stdout, _error(-32000, "session ID limit"))
                break
            seen_ids.add(request_id)
        if method == "notifications/initialized":
            if has_id:
                _write(stdout, _error(-32600, "notification cannot carry an ID"))
            elif initialized and set(message) <= {"jsonrpc", "method", "params"} \
                    and message.get("params", {}) in ({}, None):
                announced = True
            continue
        if method == "notifications/cancelled":
            # Calls are bounded and synchronous. A cancellation observed after a
            # call has completed, or for an unknown ID, has no effect or reply.
            if has_id:
                _write(stdout, _error(-32600, "notification cannot carry an ID"))
            continue
        if not has_id:
            # A well-formed JSON-RPC notification never receives a response,
            # including when this server does not implement its method.
            continue
        if not has_id or set(message) - {"jsonrpc", "method", "id", "params"}:
            _write(stdout, _error(-32600, "invalid request"))
            continue
        params = message.get("params", {})
        if method == "initialize":
            if initialized or not _initialize_params(params):
                _write(stdout, _error(-32602, "invalid initialization", request_id))
                continue
            initialized = True
            _write(stdout, _result(request_id, {"protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "context-travel", "version": "1"}}))
            continue
        if method == "ping":
            if params not in ({}, None):
                _write(stdout, _error(-32602, "invalid ping", request_id))
            else:
                _write(stdout, _result(request_id, {}))
            continue
        if not announced:
            _write(stdout, _error(-32000, "session not initialized", request_id))
            continue
        if method == "tools/list":
            if params not in ({}, None):
                _write(stdout, _error(-32602, "invalid tool list", request_id))
            else:
                _write(stdout, _result(request_id, {"tools": _tools()}))
        elif method == "tools/call":
            if type(params) is not dict or set(params) != {"name", "arguments"} \
                    or type(params["name"]) is not str or params["name"] not in _query.OPERATIONS:
                _write(stdout, _error(-32602, "invalid tool call", request_id))
                continue
            try:
                envelope = _query.run_query(policy, params["name"], params["arguments"])
                value = _query.canonical_bytes(envelope).decode("utf-8")
                _write(stdout, _result(request_id, {"content": [{"type": "text", "text": value}]}))
            except (ValueError, TypeError, RecursionError):
                _write(stdout, _result(request_id, {"content": [{"type": "text",
                    "text": "context travel query failed"}], "isError": True}))
        else:
            _write(stdout, _error(-32601, "method not found", request_id))


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise _query.QueryError("invalid server arguments")


def main(argv=None, stdin=None, stdout=None, stderr=None):
    input_stream = sys.stdin.buffer if stdin is None else stdin
    output_stream = sys.stdout.buffer if stdout is None else stdout
    error_stream = sys.stderr if stderr is None else stderr
    arguments = sys.argv[1:] if argv is None else list(argv)
    if arguments in (["--help"], ["-h"]):
        if hasattr(output_stream, "buffer"):
            output_stream.buffer.write(HELP.encode("utf-8"))
        else:
            try:
                output_stream.write(HELP.encode("utf-8"))
            except TypeError:
                output_stream.write(HELP)
        output_stream.flush()
        return 0
    parser = _Parser(prog="context-travel-mcp", add_help=False)
    parser.add_argument("--config", required=True)
    try:
        options = parser.parse_args(arguments)
        config = _query.load_config(options.config)
    except (ValueError, TypeError, OSError, UnicodeError, RecursionError):
        error_stream.write("context travel MCP startup failed\n")
        error_stream.flush()
        return 2
    try:
        serve(config, input_stream, output_stream)
        return 0
    except OSError:
        error_stream.write("context travel MCP transport failed\n")
        error_stream.flush()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
