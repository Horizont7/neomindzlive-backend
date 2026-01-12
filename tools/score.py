import math

def clamp(x, a, b): 
    return a if x < a else b if x > b else x

def score_classic(answers):
    """
    answers: list of dict:
      { "correct": bool, "difficulty": int, "discrimination": float, "time_sec": float, "time_limit_sec": int }
    """
    theta = 0.0
    for a in answers:
        diff = (a["difficulty"] - 3) / 2  # roughly -1..+1
        disc = float(a.get("discrimination", 1.0))
        correct = 1.0 if a["correct"] else 0.0
        # time factor small for classic
        theta += disc * (correct - 0.5) - 0.15 * diff

    # map theta to IQ ~ N(100,15)
    iq = 100 + theta * 7.5
    return round(clamp(iq, 55, 145))

def score_speed(answers):
    theta = 0.0
    for a in answers:
        diff = (a["difficulty"] - 3) / 2
        disc = float(a.get("discrimination", 1.0))
        correct = 1.0 if a["correct"] else 0.0
        # speed bonus (only if correct)
        t = max(0.001, float(a.get("time_sec", 999)))
        limit = float(a.get("time_limit_sec", 25))
        speed = clamp((limit - t) / limit, 0, 1)
        theta += disc * (correct - 0.5) - 0.12 * diff + (0.25 * speed if correct else 0.0)

    iq = 100 + theta * 8.5
    return round(clamp(iq, 55, 145))

def score_adaptive(theta_estimate):
    iq = 100 + theta_estimate * 15
    return round(clamp(iq, 55, 145))
