#!/usr/bin/env python3
"""Print the surface of the Parazun API from the published specification.

The CLI models the API, so the ground truth of the API is the published
specification and not the documentation of the CLI. This script reads the
specification and prints the paths, the parameters of each path, the
default of each parameter and the enumeration of each parameter.

It uses the standard library only, so it runs with any Python 3.

Usage:
    python3 api_surface.py
    python3 api_surface.py --url https://api.parazun.com/openapi.json
    python3 api_surface.py --paths /product /search
    python3 api_surface.py --json
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_SPEC = "https://api.parazun.com/openapi.json"


def normalise(name):
    """The name of a path, with the leading slash.

    The name is accepted without the slash, so the command that reads this
    script never carries a token that looks like an absolute path.
    """
    name = name.strip()
    if not name:
        return name
    return name if name.startswith("/") else "/" + name


def fetch(url, timeout=30):
    """Read the specification and return it as a document."""
    request = urllib.request.Request(url, headers={"User-Agent": "parazun-cli-skill/1"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise SystemExit("The specification did not answer: HTTP %s" % error.code)
    except urllib.error.URLError as error:
        raise SystemExit("The specification did not answer: %s" % error.reason)
    except ValueError as error:
        raise SystemExit("The specification is not JSON: %s" % error)


def is_retired(path, operation):
    """True when the operation is retired or deprecated.

    The marker is in the summary of the operation or in the flag of the
    operation. A path whose name carries the word is not a signal, because
    a path can be renamed and keep its meaning.
    """
    if operation.get("deprecated"):
        return True
    summary = (operation.get("summary") or "").upper()
    return "(RETIRED)" in summary or "(DEPRECATED)" in summary


def parameters_of(operation):
    """The parameters of one operation, in the order of the specification."""
    return operation.get("parameters") or []


def describe(parameter):
    """One line that describes one parameter."""
    name = parameter.get("name", "?")
    where = parameter.get("in", "query")
    schema = parameter.get("schema") or {}
    kind = schema.get("type", "string")
    pieces = ["%s (%s, %s)" % (name, where, kind)]
    if "default" in schema:
        pieces.append("default=%s" % json.dumps(schema["default"]))
    if "enum" in schema:
        pieces.append("enum=%s" % json.dumps(schema["enum"]))
    if parameter.get("deprecated"):
        pieces.append("DEPRECATED")
    return " ".join(pieces)


def print_responses(spec):
    """Print the refusals of the API and the body of each one."""
    paths = spec.get("paths") or {}
    seen = {}
    for path in sorted(paths):
        for method, operation in (paths[path] or {}).items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            for status, response in (operation.get("responses") or {}).items():
                key = (status, response.get("description", ""))
                body = json.dumps(response.get("content", {}), ensure_ascii=False)
                seen.setdefault(key, body)
    if not seen:
        return
    print("=== THE REFUSALS ===")
    for (status, description), body in sorted(seen.items()):
        print("%s %s" % (status, description))
        print("    %s" % body)
    print("")


def print_surface(spec, only=None, as_json=False):
    """Print the surface of the specification."""
    paths = spec.get("paths") or {}
    wanted = set(normalise(name) for name in only) if only else None
    rows = []
    for path in sorted(paths):
        if wanted is not None and path not in wanted:
            continue
        operations = paths[path] or {}
        for method in sorted(operations):
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            operation = operations[method]
            rows.append(
                {
                    "path": path,
                    "method": method.upper(),
                    "summary": operation.get("summary", ""),
                    "retired": is_retired(path, operation),
                    "parameters": [
                        describe(parameter)
                        for parameter in parameters_of(operation)
                    ],
                }
            )

    if as_json:
        print(json.dumps({"paths": rows}, indent=2, ensure_ascii=False))
        return

    live = [row for row in rows if not row["retired"]]
    retired = [row for row in rows if row["retired"]]
    print("The specification: %d operations, %d live, %d retired or deprecated."
          % (len(rows), len(live), len(retired)))
    print("")
    for server in spec.get("servers") or []:
        print("The server: %s" % server.get("url", "?"))
    for name, scheme in (spec.get("components", {}).get("securitySchemes") or {}).items():
        pieces = [name, "%s in the header %s" % (scheme.get("type", "?"), scheme.get("name", "?"))]
        if scheme.get("scheme"):
            pieces.append(scheme["scheme"])
        if scheme.get("bearerFormat"):
            pieces.append(scheme["bearerFormat"])
        print("The credential: %s" % " ".join(pieces))
    print("")
    for title, group in (("LIVE", live), ("RETIRED OR DEPRECATED", retired)):
        if not group:
            continue
        print("=== %s ===" % title)
        for row in group:
            print("%s %s%s" % (row["method"], row["path"],
                                "  (%s)" % row["summary"] if row["summary"] else ""))
            for parameter in row["parameters"]:
                print("    %s" % parameter)
        print("")
    print_responses(spec)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_SPEC,
                        help="The address of the specification.")
    parser.add_argument("--paths", nargs="*", default=None,
                        help="Only these paths. The name carries no leading slash.")
    parser.add_argument("--json", action="store_true",
                        help="Print the surface as JSON.")
    args = parser.parse_args()

    spec = fetch(args.url)
    print_surface(spec, only=args.paths, as_json=args.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
