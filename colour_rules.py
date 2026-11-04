"""Rule-based colour matching for Colour-Fit.

Each pair of colours gets a score from 0 to 100 and a short reason,
so the website can rank outfits and explain why they work.
"""

# Colours that go with almost everything
NEUTRALS = {"black", "white", "grey", "charcoal", "beige", "navy", "cream", "denim"}

# Hand-picked classic pairs (order does not matter)
CLASSIC_PAIRS = {
    frozenset(p) for p in [
        ("navy", "beige"), ("navy", "white"), ("navy", "grey"),
        ("white", "olive"), ("white", "black"), ("white", "denim"),
        ("grey", "burgundy"), ("black", "red"), ("beige", "olive"),
        ("mustard", "charcoal"), ("mustard", "navy"), ("teal", "grey"),
        ("pink", "grey"), ("maroon", "beige"),
    ]
}

# Combinations that clash
CLASHES = {
    frozenset(p) for p in [
        ("red", "green"), ("orange", "pink"), ("red", "pink"),
        ("red", "orange"), ("purple", "green"), ("yellow", "pink"),
    ]
}

# Position on a simple colour wheel (degrees) for non-neutral colours
WHEEL = {
    "red": 0, "maroon": 0, "burgundy": 350, "orange": 30, "mustard": 45,
    "yellow": 55, "olive": 80, "green": 120, "teal": 175, "blue": 220,
    "purple": 280, "pink": 330,
}

# Shades that count as the same family for the monochrome rule
FAMILIES = {
    "blue": {"blue", "navy", "denim", "teal"},
    "red": {"red", "maroon", "burgundy"},
    "green": {"green", "olive"},
    "grey": {"grey", "charcoal", "black"},
    "yellow": {"yellow", "mustard", "cream"},
}


def _wheel_gap(a, b):
    gap = abs(WHEEL[a] - WHEEL[b]) % 360
    return min(gap, 360 - gap)


def match_score(shirt, trouser):
    """Return (score 0-100, reason) for a shirt and trouser colour."""
    a, b = shirt.strip().lower(), trouser.strip().lower()
    pair = frozenset((a, b))

    if pair in CLASHES:
        return 15, f"{a.title()} and {b} compete for attention."

    if pair in CLASSIC_PAIRS:
        return 95, f"{a.title()} with {b} is a classic pairing."

    for family in FAMILIES.values():
        if a in family and b in family and a != b:
            return 85, "Two shades of the same colour look clean together."

    if a == b and a not in NEUTRALS:
        return 40, "Matching a bold colour head to toe can feel heavy."

    a_neutral, b_neutral = a in NEUTRALS, b in NEUTRALS
    if a_neutral and b_neutral:
        return 80, "Neutrals are easy to wear together."
    if a_neutral or b_neutral:
        return 82, "One neutral keeps the bolder colour in focus."

    if a in WHEEL and b in WHEEL:
        gap = _wheel_gap(a, b)
        if 150 <= gap <= 180:
            return 78, "Opposite colours make a strong contrast."
        if gap <= 60:
            return 74, "Neighbouring colours blend smoothly."
        return 45, "These two colours may be hard to balance."

    return 50, "No strong rule applies. Try it and judge by eye."


def find_combinations(shirts, trousers, min_score=60):
    """Rank every shirt and trouser pair.

    shirts / trousers: lists of dicts with at least 'id' and 'colour'.
    Returns a list of dicts sorted by score, best first.
    """
    results = []
    for s in shirts:
        for t in trousers:
            score, reason = match_score(s["colour"], t["colour"])
            if score >= min_score:
                results.append({"shirt": s, "trouser": t,
                                "score": score, "reason": reason})
    return sorted(results, key=lambda r: r["score"], reverse=True)


if __name__ == "__main__":
    shirts = [{"id": 1, "colour": "navy"}, {"id": 2, "colour": "mustard"},
              {"id": 3, "colour": "red"}]
    trousers = [{"id": 1, "colour": "beige"}, {"id": 2, "colour": "green"},
                {"id": 3, "colour": "charcoal"}]
    for r in find_combinations(shirts, trousers):
        print(r["score"], r["shirt"]["colour"], "+", r["trouser"]["colour"], "-", r["reason"])
