"""Guard against drift between our baked filing-status table and the onboarding API.

Run:  python utils/check_state_filing_status.py

`utils/state_filing_status.py` is a transcription of `parseStateFilingStatus()` in
`StateTaxWithholdingValidator.java`. The Java lives outside this repo, so the copy
can rot -- and it rots silently: a label the API dropped still looks accepted to
us, so we hand the client a file the import then rejects, and a label the API
added still looks invalid, so we make the user map a value that was already fine.

This re-parses the Java when it is on disk and reports every difference. Where the
Java is not present (most machines) it says so and exits 0 -- it cannot check what
it cannot read, and failing there would just teach people to ignore it.

Set UZIO_ONBOARDING_SRC to the onboarding-service directory if yours is elsewhere.

Three things the parser has to survive, all of which broke an earlier attempt:
  * `case "HI" : // Hawaii`  -- a space before the colon, which silently folded
    every Hawaii label into Georgia's block
  * `case "SINGLE", "MARRIED, AT SINGLE RATE":` -- a Java 14 multi-label case (NE)
  * `case "AZ": ... return "2.0";` -- Arizona returns percentages, not XX_ENUM
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.state_filing_status import ACCEPTED, _depunct  # noqa: E402

REL_JAVA = os.path.join(
    "src", "main", "java", "com", "uzio", "onboarding", "validator",
    "StateTaxWithholdingValidator.java",
)

CANDIDATE_ROOTS = [
    os.environ.get("UZIO_ONBOARDING_SRC", ""),
    r"C:\Users\rohit.kaushik\Downloads\Claude Core\onboarding\onboarding-service",
    r"C:\Users\shobhit.sharma\Downloads\Uzio Code\onboarding\onboarding-service",
]

STATE_CASE = re.compile(r'^case\s+"([A-Z]{2})"\s*:\s*(//.*)?$')
INNER_CASE = re.compile(r'^case\s+(".*")\s*:\s*$')
RETURN = re.compile(r'^return\s+"([^"]*)";\s*$')
LABELS = re.compile(r'"((?:[^"\\]|\\.)*)"')


def find_java():
    for root in CANDIDATE_ROOTS:
        if not root:
            continue
        path = os.path.join(root, REL_JAVA)
        if os.path.exists(path):
            return path
    return None


def method_body(lines, signature):
    start = next((i for i, l in enumerate(lines) if signature in l), None)
    if start is None:
        return None
    depth, seen, body = 0, False, []
    for line in lines[start:]:
        body.append(line)
        depth += line.count("{") - line.count("}")
        seen = seen or "{" in line
        if seen and depth <= 0:
            break
    return body


def parse(body):
    """state -> {label: enum}, in the Java's spelling."""
    table, state, pending = {}, None, []
    for i, raw in enumerate(body):
        s = raw.strip()
        m = STATE_CASE.match(s)
        if m:
            nxt = next((x.strip() for x in body[i + 1:] if x.strip()), "")
            if nxt.startswith("switch (upperFilingStatus)"):
                state = m.group(1)
                table.setdefault(state, {})
                pending = []
                continue
        if state is None:
            continue
        m = INNER_CASE.match(s)
        if m:
            pending.extend(LABELS.findall(m.group(1)))
            continue
        m = RETURN.match(s)
        if m and pending:
            for label in pending:
                table[state][label] = m.group(1)
            pending = []
            continue
        if s.startswith("break;"):
            pending = []
    return {k: v for k, v in table.items() if v}


def check_ambiguity():
    """Two labels may collapse together only if they mean the same thing.

    `canonical_label` repairs a punctuation mismatch by picking the label that
    matches once punctuation is ignored. Several states list the same status
    twice with and without a comma ("MARRIED, AT SINGLE RATE" / "MARRIED AT
    SINGLE RATE"); both map to one enum, so picking either is cosmetic. Two
    collapsing labels with DIFFERENT enums would make that repair a coin flip,
    and the tool would silently pick a filing status the user never chose.
    """
    problems = 0
    for state, pairs in ACCEPTED.items():
        seen = {}
        for label, enum in pairs:
            if not label:
                continue
            key = _depunct(label)
            if key in seen and seen[key][1] != enum:
                problems += 1
                print("AMBIGUOUS {}  {!r} -> {} and {!r} -> {} differ only by "
                      "punctuation but mean different things"
                      .format(state, seen[key][0], seen[key][1], label, enum))
            seen.setdefault(key, (label, enum))
    return problems


def main():
    problems = check_ambiguity()

    java = find_java()
    if not java:
        print("SKIP      the onboarding Java is not on this machine, so the baked")
        print("          table cannot be checked against it.")
        print("          Set UZIO_ONBOARDING_SRC=<...>/onboarding-service to enable.")
        print()
        if problems:
            print("{} ambiguous label pair(s) in the baked table.".format(problems))
            return 1
        print("Baked table is internally consistent "
              "({} states, {} labels).".format(
                  len(ACCEPTED), sum(len(v) for v in ACCEPTED.values())))
        return 0

    lines = open(java, encoding="utf-8", errors="replace").read().splitlines()
    body = method_body(lines, "default String parseStateFilingStatus(")
    if body is None:
        print("MISMATCH  parseStateFilingStatus() not found in {}".format(java))
        print("          The method was renamed or moved -- re-transcribe the table.")
        return 1

    live = parse(body)
    ours = {st: dict(pairs) for st, pairs in ACCEPTED.items()}

    for state in sorted(set(ours) - set(live)):
        problems += 1
        print("MISMATCH  {} is in our table but the API no longer has a case for it"
              .format(state))
    for state in sorted(set(live) - set(ours)):
        problems += 1
        print("MISMATCH  {} is in the API but missing from our table ({} labels)"
              .format(state, len(live[state])))

    for state in sorted(set(ours) & set(live)):
        o, n = ours[state], live[state]
        for label in sorted(set(o) - set(n)):
            problems += 1
            print("MISMATCH  {}  ours only : {!r} -> {}".format(state, label, o[label]))
        for label in sorted(set(n) - set(o)):
            problems += 1
            print("MISMATCH  {}  API only  : {!r} -> {}".format(state, label, n[label]))
        for label in sorted(set(o) & set(n)):
            if o[label] != n[label]:
                problems += 1
                print("MISMATCH  {}  {!r} maps to {} for us, {} in the API"
                      .format(state, label, o[label], n[label]))

    print()
    print("checked against {}".format(java))
    if problems:
        print("{} difference(s) -- re-transcribe utils/state_filing_status.py "
              "before shipping.".format(problems))
        return 1
    print("Baked table matches the API ({} states, {} labels, {} enums)."
          .format(len(live), sum(len(v) for v in live.values()),
                  len({e for v in live.values() for e in v.values()})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
