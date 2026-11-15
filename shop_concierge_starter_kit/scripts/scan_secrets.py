"""Scan the git repo (tracked files AND full history) for committed secrets.

Usage: python scripts/scan_secrets.py [repo_dir]
Prints only WHERE a match is (file, commit, pattern name), never the matched text.
Exit code 1 if anything is found. Run it before every deploy and in T9-style reviews.
"""
import re
import subprocess
import sys
from pathlib import Path

PATTERNS = {
    "anthropic-api-key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "private-key-block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "github-token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "slack-token": re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    "secret-assignment": re.compile(
        r"(?i)\b(password|passwd|secret_key|api_key|apikey|auth_token)\b\s*[:=]\s*['\"]?"
        r"(?!change-me|example|your|<|\$\{|\s)[A-Za-z0-9/+_.-]{16,}"),
}
FORBIDDEN_NAMES = re.compile(r"(^|/)(\.env|id_rsa|id_ed25519|godaddy_vps[^/]*)$|\.(pem|db|sqlite3?)$")
SKIP_ASSIGNMENT_IN = re.compile(r"(^|/)(tests/|\.env\.example$)")      # fixtures use obvious fake values


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout


def scan(root):
    root = Path(root)
    findings = []                                           # (where, what)
    for name in git(root, "ls-files").splitlines():
        if FORBIDDEN_NAMES.search(name):
            findings.append((name, "forbidden-file-tracked"))
    for name in set(git(root, "log", "--all", "--name-only", "--pretty=format:").splitlines()):
        if name and FORBIDDEN_NAMES.search(name):
            findings.append((f"{name} (history)", "forbidden-file-in-history"))
    commit, path = "", ""
    for line in git(root, "log", "--all", "-p", "--no-color", "--pretty=format:@@@%h").splitlines():
        if line.startswith("@@@"):
            commit = line[3:]
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            for label, pattern in PATTERNS.items():
                if label == "secret-assignment" and SKIP_ASSIGNMENT_IN.search(path):
                    continue
                if pattern.search(line):
                    findings.append((f"{path} @ {commit}", label))
    return sorted(set(findings))


if __name__ == "__main__":
    found = scan(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent)
    for where, what in found:
        print(f"FOUND {what}: {where}")
    print(f"{len(found)} finding(s)")
    sys.exit(1 if found else 0)
