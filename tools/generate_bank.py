import json, random, math
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "question_bank_generated.json"
random.seed(42)

CATS = [
    "logic_sequence",
    "arithmetic_reasoning",
    "algebra_basic",
    "percent_ratio",
    "pattern_odd_one_out",
    "verbal_analogy_simple",
]

def shuffle_options(correct, wrongs):
    opts = wrongs + [correct]
    random.shuffle(opts)
    ci = opts.index(correct)
    return opts, ci

def q_logic_sequence(idx: int):
    # Quadratic-ish / increasing difference sequences
    start = random.randint(1, 15)
    d0 = random.randint(1, 6)
    step = random.randint(1, 4)
    seq = [start]
    d = d0
    for _ in range(3):
        seq.append(seq[-1] + d)
        d += step
    # next
    next_val = seq[-1] + d
    prompt = f"Which number comes next: {seq[0]}, {seq[1]}, {seq[2]}, {seq[3]}, ?"
    wrongs = list({next_val + random.choice([-6,-4,-3,-2,2,3,4,6]) for _ in range(6)})
    wrongs = wrongs[:3]
    opts, ci = shuffle_options(next_val, wrongs)
    difficulty = 2 + (step >= 3) + (d0 >= 5)
    disc = round(1.0 + 0.1 * difficulty + random.random()*0.2, 2)
    return {
        "id": f"LS-{idx:06d}",
        "category": "logic_sequence",
        "difficulty": int(min(5, max(1, difficulty))),
        "discrimination": disc,
        "type": "mcq",
        "prompt": prompt,
        "options": [str(o) for o in opts],
        "correct_index": ci,
        "time_limit_sec": 35 if difficulty <= 3 else 45,
        "explanation": "Find the pattern in differences; they increase by a constant step."
    }

def q_arithmetic_reasoning(idx: int):
    # Short word-style arithmetic
    a = random.randint(8, 30)
    b = random.randint(3, 15)
    c = random.randint(2, 9)
    # Example: (a * b) - c
    correct = a * b - c
    prompt = f"Compute: {a} × {b} − {c}"
    wrongs = [correct + random.choice([-20,-10,-5,-2,2,5,10,20]) for _ in range(4)]
    wrongs = list(dict.fromkeys(wrongs))
    wrongs = wrongs[:3]
    opts, ci = shuffle_options(correct, wrongs)
    difficulty = 2 + (b >= 10) + (a >= 20)
    disc = round(0.95 + 0.12 * difficulty + random.random()*0.2, 2)
    return {
        "id": f"AR-{idx:06d}",
        "category": "arithmetic_reasoning",
        "difficulty": int(min(5, max(1, difficulty))),
        "discrimination": disc,
        "type": "mcq",
        "prompt": prompt,
        "options": [str(o) for o in opts],
        "correct_index": ci,
        "time_limit_sec": 20 if difficulty <= 3 else 25,
        "explanation": "Multiply first, then subtract."
    }

def q_algebra_basic(idx: int):
    # Solve x: ax + b = c
    a = random.randint(2, 9)
    x = random.randint(2, 15)
    b = random.randint(-10, 10)
    c = a * x + b
    prompt = f"Solve for x: {a}x {'+' if b>=0 else '-'} {abs(b)} = {c}"
    correct = x
    wrongs = list({x + random.choice([-4,-3,-2,2,3,4]) for _ in range(6)})
    wrongs = [w for w in wrongs if w > 0][:3]
    if len(wrongs) < 3:
        wrongs += [x+1, x+2, x-1][: (3-len(wrongs))]
    opts, ci = shuffle_options(correct, wrongs[:3])
    difficulty = 3 + (abs(b) >= 7)
    disc = round(1.05 + 0.12 * difficulty + random.random()*0.2, 2)
    return {
        "id": f"AL-{idx:06d}",
        "category": "algebra_basic",
        "difficulty": int(min(5, max(1, difficulty))),
        "discrimination": disc,
        "type": "mcq",
        "prompt": prompt,
        "options": [str(o) for o in opts],
        "correct_index": ci,
        "time_limit_sec": 30 if difficulty <= 4 else 40,
        "explanation": "Isolate x by subtracting b, then divide by a."
    }

def q_percent_ratio(idx: int):
    # Percent / ratio
    base = random.randint(50, 400)
    pct = random.choice([5,10,12,15,20,25,30,40])
    correct = int(round(base * pct / 100))
    prompt = f"What is {pct}% of {base}?"
    wrongs = list({correct + random.choice([-30,-20,-10,-5,5,10,20,30]) for _ in range(8)})
    wrongs = [w for w in wrongs if w >= 0][:3]
    opts, ci = shuffle_options(correct, wrongs)
    difficulty = 2 + (base >= 250) + (pct not in [10,20,25])
    disc = round(0.9 + 0.14 * difficulty + random.random()*0.2, 2)
    return {
        "id": f"PR-{idx:06d}",
        "category": "percent_ratio",
        "difficulty": int(min(5, max(1, difficulty))),
        "discrimination": disc,
        "type": "mcq",
        "prompt": prompt,
        "options": [str(o) for o in opts],
        "correct_index": ci,
        "time_limit_sec": 18 if difficulty <= 3 else 22,
        "explanation": "Compute base × percent / 100."
    }

def q_odd_one_out(idx: int):
    # Odd one out: choose the only number with a special property
    # Example: only prime, only multiple, only square...
    mode = random.choice(["prime", "square", "multiple3"])
    if mode == "prime":
        correct = random.choice([11,13,17,19,23,29,31])
        wrongs = random.sample([12,14,15,16,18,20,21,22,24,25,26,27,28,30,32], 3)
        prompt = "Which number is PRIME?"
    elif mode == "square":
        correct = random.choice([16,25,36,49,64,81])
        wrongs = random.sample([18,24,27,32,40,45,50,63,72,75], 3)
        prompt = "Which number is a PERFECT SQUARE?"
    else:
        correct = random.choice([12,15,18,21,24,27,30])
        wrongs = random.sample([10,11,13,14,16,17,19,20,22,23,25,26,28,29], 3)
        prompt = "Which number is a MULTIPLE OF 3?"
    opts, ci = shuffle_options(correct, wrongs)
    difficulty = 2 if mode != "prime" else 3
    disc = round(0.95 + 0.15 * difficulty + random.random()*0.2, 2)
    return {
        "id": f"OO-{idx:06d}",
        "category": "pattern_odd_one_out",
        "difficulty": int(min(5, max(1, difficulty))),
        "discrimination": disc,
        "type": "mcq",
        "prompt": prompt,
        "options": [str(o) for o in opts],
        "correct_index": ci,
        "time_limit_sec": 15 if difficulty <= 3 else 18,
        "explanation": "Identify the unique property asked in the question."
    }

def q_verbal_analogy(idx: int):
    # Simple analogy (English). If you want RU/UZ later, we can localize.
    pairs = [
        ("Hot", "Cold", "Up", "Down"),
        ("Day", "Night", "Summer", "Winter"),
        ("Buy", "Sell", "Give", "Take"),
        ("Big", "Small", "Fast", "Slow"),
        ("Start", "Finish", "Open", "Close"),
    ]
    a,b,c,d = random.choice(pairs)
    prompt = f"{a} is to {b} as {c} is to ?"
    correct = d
    wrongs = random.sample([b, a, c, "Left", "Right", "Bright", "Dark", "High", "Low"], 6)
    wrongs = [w for w in wrongs if w != correct][:3]
    opts, ci = shuffle_options(correct, wrongs)
    difficulty = 1 + random.choice([1,2])
    disc = round(0.8 + 0.12 * difficulty + random.random()*0.2, 2)
    return {
        "id": f"VA-{idx:06d}",
        "category": "verbal_analogy_simple",
        "difficulty": int(min(5, max(1, difficulty))),
        "discrimination": disc,
        "type": "mcq",
        "prompt": prompt,
        "options": opts,
        "correct_index": ci,
        "time_limit_sec": 22,
        "explanation": "Choose the word that completes the same relationship."
    }

GENS = [q_logic_sequence, q_arithmetic_reasoning, q_algebra_basic, q_percent_ratio, q_odd_one_out, q_verbal_analogy]

def generate(total=10000):
    bank = []
    counts = [0]*len(GENS)
    for i in range(total):
        gi = i % len(GENS)
        q = GENS[gi](counts[gi])
        counts[gi] += 1
        bank.append(q)
    random.shuffle(bank)
    return bank

if __name__ == "__main__":
    bank = generate(10000)
    OUT.write_text(json.dumps(bank, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Generated:", len(bank), "->", OUT)
