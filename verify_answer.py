"""Check every dollar figure in an agent's answer, not just the headline.

The headline comes from the tool and is reliable. The supporting numbers a model
volunteers -- total contributions, growth -- are its own arithmetic and have been
wrong by ~$900 while the headline was exact. Given the parameters, all of them
are computable, so none of this needs a judge.

    python3 verify_answer.py 6250 0.047 318 21 "the agent's reply text"
"""

import re
import sys

from retirement import future_value

TOLERANCE = 1.0  # accept whole-dollar rounding


def expected(capital, rate, monthly, years):
    """Every figure an honest answer could legitimately contain."""
    fv = future_value(capital, rate, monthly, years)
    contributed = monthly * 12 * round(years)
    return {
        "future value": fv,
        "initial capital": capital,
        "total contributions": contributed,
        "growth": fv - capital - contributed,
        "years": years,
        "monthly": monthly,
        "rate %": rate * 100,
    }


GROUPED = re.compile(r"^\d{1,3}(,\d{3})*(\.\d+)?$")


def check(capital, rate, monthly, years, text):
    """Return (ok, headline_found, [unexplained figures], [malformed tokens])."""
    legit = expected(capital, rate, monthly, years)
    found, malformed = [], []
    for m in re.findall(r"\d[\d,]*(?:\.\d+)?", text):
        m = m.rstrip(",")  # sentence punctuation, not part of the number
        # "6,911,50.47" normalises to the right value but reads as 10x too big.
        if "," in m and not GROUPED.match(m):
            malformed.append(m)
        try:
            found.append(float(m.replace(",", "")))
        except ValueError:
            pass
    headline = any(abs(n - legit["future value"]) <= TOLERANCE for n in found)
    unexplained = [
        n for n in found
        if not any(abs(n - v) <= TOLERANCE for v in legit.values())
    ]
    return headline and not unexplained and not malformed, headline, unexplained, malformed


def main():
    cap, rate, mon, yrs = (float(a) for a in sys.argv[1:5])
    text = sys.argv[5]
    ok, headline, bad, malformed = check(cap, rate, mon, yrs, text)
    print("headline:", "correct" if headline else "WRONG OR MISSING")
    if malformed:
        print("malformed digit grouping:", malformed)
    if bad:
        print("unexplained figures:", bad)
        for k, v in expected(cap, rate, mon, yrs).items():
            print(f"    {k:20} = {v:,.2f}")
    print("VERDICT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
