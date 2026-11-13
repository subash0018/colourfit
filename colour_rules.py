"""Rule-based colour matching for Colour-Fit.

Each shirt and trouser pair gets a score from 0 to 100 plus two short
sentences: why the colours work (or don't) and one styling tip.
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


def _match(shirt, trouser):
    """Return (score, reason, tip). Each sentence is short enough for one line."""
    a, b = shirt.strip().lower(), trouser.strip().lower()
    pair = frozenset((a, b))

    if pair in CLASHES:
        return 15, f"{a.title()} and {b} compete for attention.", "Try a neutral piece to calm the look."

    if pair in CLASSIC_PAIRS:
        return 95, f"{a.title()} with {b} is a classic pairing.", "Dependable for work or a casual day out."

    for family in FAMILIES.values():
        if a in family and b in family and a != b:
            return 85, "Two shades of one colour look clean.", "Neutral shoes or a belt finish the look."

    if a == b and a not in NEUTRALS:
        return 40, "Head-to-toe bold colour can feel heavy.", "Break it up with neutral shoes."

    a_neutral, b_neutral = a in NEUTRALS, b in NEUTRALS
    if a_neutral and b_neutral:
        return 80, "Neutrals are easy to wear together.", "Add one coloured accessory for interest."
    if a_neutral or b_neutral:
        return 82, "A neutral lets the bolder colour lead.", "Keep shoes and accessories simple."

    if a in WHEEL and b in WHEEL:
        gap = _wheel_gap(a, b)
        if 150 <= gap <= 180:
            return 78, "Opposite colours make a strong contrast.", "Keep accessories neutral to stay sharp."
        if gap <= 60:
            return 74, "Neighbouring colours blend smoothly.", "A smooth, easy look for everyday wear."
        return 45, "These colours may be hard to balance.", "Try a neutral shirt or trousers instead."

    return 50, "No strong rule applies. Judge by eye.", "Preview it on the avatar to decide."


def match_score(shirt, trouser):
    """Return (score 0-100, reason) for a shirt and trouser colour."""
    score, reason, _tip = _match(shirt, trouser)
    return score, reason


def find_combinations(shirts, trousers, min_score=60):
    """Rank every shirt and trouser pair, best first.

    shirts / trousers: lists of dicts (or rows) with at least 'colour'.
    Each result has: shirt, trouser, score, reason, tip.
    """
    results = []
    for s in shirts:
        for t in trousers:
            score, reason, tip = _match(s["colour"], t["colour"])
            if score >= min_score:
                results.append({"shirt": s, "trouser": t,
                                "score": score, "reason": reason, "tip": tip})
    return sorted(results, key=lambda r: r["score"], reverse=True)


if __name__ == "__main__":
    shirts = [{"id": 1, "colour": "navy"}, {"id": 2, "colour": "mustard"},
              {"id": 3, "colour": "red"}]
    trousers = [{"id": 1, "colour": "beige"}, {"id": 2, "colour": "green"},
                {"id": 3, "colour": "charcoal"}]
    for r in find_combinations(shirts, trousers):
        print(r["score"], r["shirt"]["colour"], "+", r["trouser"]["colour"])
        print("   ", r["reason"])
        print("   ", r["tip"])