import random
from math import exp

def p_correct(theta, b, a=1.0):
    # logistic model
    return 1.0 / (1.0 + exp(-a * (theta - b)))

def update_theta(theta, correct, b, a=1.0, lr=0.35):
    # gradient step for MLE-ish update
    p = p_correct(theta, b, a)
    y = 1.0 if correct else 0.0
    return theta + lr * a * (y - p)

def choose_next(bank, used_ids, theta, target_category=None):
    """
    bank: list of questions (each has difficulty 1..5, discrimination)
    theta: current estimate (approx -2..+2)
    We pick question whose difficulty b is closest to theta (mapped)
    """
    # map difficulty 1..5 to b in [-2,2]
    def b_of(q):
        d = int(q["difficulty"])
        return (d - 3) * 1.0  # -2,-1,0,1,2
    candidates = [q for q in bank if q["id"] not in used_ids]
    if target_category:
        candidates = [q for q in candidates if q["category"] == target_category] or candidates

    # choose closest b
    candidates.sort(key=lambda q: abs(b_of(q) - theta))
    top = candidates[:30] if len(candidates) > 30 else candidates
    return random.choice(top) if top else None
