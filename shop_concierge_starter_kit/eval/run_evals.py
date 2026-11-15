"""Run eval/cases.json through answer(). Exit 1 on any failure.

Usage: python eval/run_evals.py [--ai] [--db PATH]
Matching: contains_any is case-insensitive; must_not_contain is case-insensitive, and
alphabetic items match whole words only (so "Rs" does not match "hours").
"""
import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from app import answer as engine, db, global_lookups as g  # noqa: E402
import seed  # noqa: E402


def banned(text, item):
    if item.isalpha():
        return re.search(rf"\b{re.escape(item)}\b", text, re.I) is not None
    return item.lower() in text.lower()


def check(case, result):
    text, why = result["answer"], []
    if bool(result["found"]) != bool(case["expect_found"]):
        why.append(f"found={result['found']}, expected {case['expect_found']}")
    if case.get("contains_any") and not any(s.lower() in text.lower() for s in case["contains_any"]):
        why.append(f"none of {case['contains_any']} in answer")
    for s in case.get("must_not_contain", []):
        if banned(text, s):
            why.append(f"answer contains forbidden {s!r}")
    return why


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ai", action="store_true", help="use the AI path (needs T6)")
    ap.add_argument("--db", default=None)
    args = ap.parse_args()
    if args.ai:
        try:
            from app.ai import chat_ai  # noqa: F401
        except ImportError:
            print("AI path not available yet (T6 not built). Run without --ai.")
            return 2
    cases = json.loads((ROOT / "eval" / "cases.json").read_text())["cases"]
    path = args.db or str(Path(tempfile.mkdtemp()) / "eval.db")
    conn = db.connect(path)
    db.init_db(conn)
    seed.seed(conn)
    failed = 0
    for case in cases:
        shop = g.get_shop_by_slug(conn, case["shop"])
        if shop is None:
            result, why = {"answer": ""}, [f"unknown shop {case['shop']}"]
        else:
            result = engine.answer(shop["id"], case["question"], conn=conn)
            why = check(case, result)
        failed += bool(why)
        print(f"{'FAIL' if why else 'PASS'} {case['id']} [{case['shop']}] {case['question']}")
        if why:
            print(f"     -> {'; '.join(why)}\n     answer: {result['answer']}")
    total = len(cases)
    print(f"\n{total - failed}/{total} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
