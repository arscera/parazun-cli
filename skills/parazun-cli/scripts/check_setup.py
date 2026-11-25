#!/usr/bin/env python3
"""Check the install of the Parazun CLI, the credential and one live call.

The script prints one line per check and a verdict at the end. It never
prints a secret: it prints whether a credential is there and never its
value.

The verdicts are PASS, FAIL and NEED. NEED means the check did not run
because a credential is missing, and it is not a failure.

Usage:
    python3 check_setup.py
    python3 check_setup.py --path product --param asin=B00FLYWNYQ
"""

import argparse
import json
import os
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request

DEFAULT_SPEC = "https://api.parazun.com/openapi.json"
DEFAULT_CALL = ["departments"]

# The repository that holds this skill, so the script finds the virtual
# environment of the repository when the command is not on the path.
REPOSITORY = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)


def find_cli():
    """The command of the CLI, and where it was found."""
    named = os.getenv("PARAZUN_CLI", "").strip()
    if named:
        return named, "PARAZUN_CLI"
    found = shutil.which("parazun")
    if found:
        return found, "the path"
    local = os.path.join(REPOSITORY, ".venv", "bin", "parazun")
    if os.path.exists(local):
        return local, "the virtual environment of the repository"
    return None, "nowhere"


def run(command, arguments):
    """Run the CLI and return the three channels of its answer."""
    try:
        result = subprocess.run(
            [command] + arguments,
            capture_output=True,
            text=True,
            timeout=90,
        )
    except subprocess.TimeoutExpired:
        return 124, "", "the command did not answer in 90 seconds"
    return result.returncode, result.stdout, result.stderr


def credentials_path():
    """The path of the credentials file, from the environment."""
    directory = os.getenv("PARAZUN_CONFIG_DIR", "").strip()
    if not directory:
        directory = os.path.join(os.path.expanduser("~"), ".config", "parazun")
    return os.path.join(directory, "credentials.json")


def check_install(command, where):
    """The command answers."""
    code, out, err = run(command, ["--help"])
    ok = code == 0 and "Commands" in out
    return ("PASS" if ok else "FAIL"), "the command answers: %s (%s)" % (command, where)


def check_credentials_file():
    """The file of the credentials is a secret."""
    path = credentials_path()
    if not os.path.exists(path):
        if os.getenv("PARAZUN_API_KEY", "").strip():
            return "PASS", ("the credentials file is not there and the key of "
                            "the environment carries the credential: %s" % path)
        return "NEED", ("there is no credential on this machine. The file is "
                        "not there: %s" % path)
    mode = stat.S_IMODE(os.stat(path).st_mode)
    directory_mode = stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode)
    ok = mode == 0o600 and directory_mode == 0o700
    return ("PASS" if ok else "FAIL"), (
        "the credentials file has the mode %o and its directory the mode %o: %s"
        % (mode, directory_mode, path))


def check_sign_in(command):
    """The state of the sign in of the machine."""
    code, out, err = run(command, ["auth", "status"])
    if code == 0:
        return "PASS", "the machine is signed in: %s" % out.strip().replace("\n", " | ")
    if "not signed in" in out + err:
        return "NEED", ("the machine is not signed in. Run `parazun auth "
                        "login`, or set PARAZUN_API_KEY.")
    return "FAIL", "the sign in could not be read: %s" % (out + err).strip()


def check_environment_key():
    """The key of the environment is there, or it is not."""
    present = bool(os.getenv("PARAZUN_API_KEY", "").strip())
    if present:
        return "PASS", "PARAZUN_API_KEY is set"
    return "PASS", "PARAZUN_API_KEY is not set"


def check_live_call(command, arguments):
    """One call reaches the API."""
    code, out, err = run(command, arguments)
    status = ""
    for line in err.splitlines():
        if line.startswith("HTTP "):
            status = line
    if code == 0:
        return "PASS", "the call answered: %s (%d bytes on stdout)%s" % (
            arguments[0], len(out), " | %s" % status if status else "")
    if "not signed in" in (out + err):
        return "NEED", ("the call could not run: the machine is not signed "
                        "in. Run `parazun auth login`, or set PARAZUN_API_KEY.")
    return "FAIL", "the call was refused: %s | %s" % (
        status or "no status line", (err.strip().splitlines() or [""])[0])


def check_specification(url):
    """The published specification answers."""
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "parazun-cli-skill"})
        with urllib.request.urlopen(request, timeout=30) as response:
            spec = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, ValueError) as error:
        return "FAIL", "the specification did not answer: %s" % error
    paths = spec.get("paths") or {}
    retired = 0
    for path in paths.values():
        for method, operation in (path or {}).items():
            if method not in ("get", "post"):
                continue
            summary = (operation.get("summary") or "").upper()
            if "(RETIRED)" in summary or "(DEPRECATED)" in summary:
                retired += 1
    return "PASS", ("the specification answers: %d paths, %d live, %d retired "
                    "or deprecated" % (len(paths), len(paths) - retired, retired))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", default=None,
                        help="The path of the API for the live call.")
    parser.add_argument("--param", action="append", default=[],
                        help="A parameter of the live call, as name=value.")
    parser.add_argument("--spec", default=DEFAULT_SPEC,
                        help="The address of the specification.")
    args = parser.parse_args()

    command, where = find_cli()
    if command is None:
        print("FAIL  the command of the CLI was not found. Install it, or set "
              "PARAZUN_CLI to its path.")
        return 1

    if args.path:
        call = ["request", args.path]
        for item in args.param:
            call.extend(["--param", item])
    else:
        call = list(DEFAULT_CALL)

    checks = [
        ("the install", check_install(command, where)),
        ("the credential file", check_credentials_file()),
        ("the sign in", check_sign_in(command)),
        ("the key of the environment", check_environment_key()),
        ("the specification", check_specification(args.spec)),
        ("a live call", check_live_call(command, call)),
    ]

    failures = 0
    needs = 0
    for name, (verdict, detail) in checks:
        if verdict == "FAIL":
            failures += 1
        elif verdict == "NEED":
            needs += 1
        print("%-5s %-28s %s" % (verdict, name, detail))
    print("")
    print("%d checks, %d failed, %d need a credential."
          % (len(checks), failures, needs))
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
