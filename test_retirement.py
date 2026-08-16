"""Self-check: closed form must match a naive month-by-month simulation.

randomized_check.sh verifies the agent relays the tool's number faithfully, but
derives truth from future_value itself -- so a bug in the formula passes both
sides. This is the independent implementation that closes that gap.

    python3 test_retirement.py
"""

from retirement import future_value


def simulate(capital, rate, monthly, years):
    """Same conventions, no annuity formula: grow, then contribute, monthly."""
    r = rate / 12
    for _ in range(round(years * 12)):
        capital = capital * (1 + r) + monthly
    return capital


def main():
    cases = [
        (10000, 0.07, 500, 30),   # the textbook case
        (0, 0.05, 250, 10),       # no starting capital
        (5000, 0.0, 100, 7),      # zero rate (separate branch)
        (1234, 0.1187, 0, 23),    # no contributions
        (88000, 0.011, 1450, 41), # long horizon, awkward values
    ]
    for c in cases:
        assert abs(future_value(*c) - simulate(*c)) < 1e-6, c

    assert future_value(9000, 0.07, 500, 0) == 9000        # nothing invested yet
    assert future_value(0, 0.0, 100, 2) == 2400            # zero rate, no growth
    assert future_value(100, 0.07, 0, 5) > 100             # grows without contributions

    print(f"ok: {len(cases)} differential + 3 invariants")


if __name__ == "__main__":
    main()
