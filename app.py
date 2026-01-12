# app.py
# run: cd backend
# run: python -m uvicorn app:APP --reload --host 127.0.0.1 --port 8000

import os, json, uuid, datetime, random
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from db import init_db, get_db


APP = FastAPI(title="NeoMindzLive API")

# ===================== CORS =====================
APP.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # prod'da domen bilan cheklaysiz
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================== PATHS / CONFIG =====================
BASE_DIR = os.path.dirname(__file__)

PRICE_AMOUNT = float(os.getenv("PRICE_AMOUNT", "1.49"))

# Default: generator chiqargan bank
QB_PATH = os.getenv("QUESTION_BANK_PATH", os.path.join(BASE_DIR, "question_bank_generated.json"))


def now_iso() -> str:
    return datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def safe_int(v, default=0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def row_get(row, key, default=None):
    """
    sqlite3.Row dictga o'xshaydi, lekin .get() yo'q.
    """
    try:
        if row is None:
            return default
        return row[key]
    except Exception:
        return default


# ===================== QUESTION BANK =====================
def load_question_bank() -> List[Dict[str, Any]]:
    if not os.path.exists(QB_PATH):
        return []
    try:
        with open(QB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                # faqat dict bo'lganlarini qoldiramiz
                return [x for x in data if isinstance(x, dict)]
            return []
    except Exception:
        return []


QUESTION_BANK: List[Dict[str, Any]] = load_question_bank()
QUESTION_BY_ID: Dict[str, Dict[str, Any]] = {
    q.get("id"): q for q in QUESTION_BANK if isinstance(q, dict) and q.get("id")
}


def ensure_user_id(request: Request) -> str:
    user_id = (request.headers.get("X-User-Id") or "").strip()
    if not user_id:
        raise HTTPException(400, "Missing X-User-Id header (temporary auth).")
    return user_id


def normalize_question(raw: Dict[str, Any], stage: str, fallback_level: int) -> Dict[str, Any]:
    """
    Bank formatlari turlicha bo'lishi mumkin:
      - generator: options / correct_index / category / difficulty
      - eski: choices / answer_index / section
    Biz API uchun doim shuni qaytaramiz:
      {id, prompt, choices, answer_index, difficulty, time_limit_sec, stage}
    """
    q = dict(raw or {})

    qid = q.get("id") or str(uuid.uuid4())
    prompt = q.get("prompt") or ""

    choices = q.get("choices")
    if not isinstance(choices, list):
        choices = q.get("options")
    if not isinstance(choices, list) or len(choices) < 2:
        choices = ["A", "B", "C", "D"]

    ans = q.get("answer_index")
    if ans is None:
        ans = q.get("correct_index")
    answer_index = safe_int(ans, 0)

    difficulty = safe_int(q.get("difficulty", fallback_level), fallback_level)

    # time limit
    if stage == "speed":
        time_limit_sec = safe_int(q.get("time_limit_sec", 20), 20)
    else:
        time_limit_sec = safe_int(q.get("time_limit_sec", 45), 45)

    # stage/section
    section = q.get("section") or stage

    return {
        "id": qid,
        "prompt": prompt,
        "choices": choices,
        "answer_index": answer_index,
        "difficulty": difficulty,
        "time_limit_sec": time_limit_sec,
        "stage": stage,
        "section": section,
        "category": q.get("category"),
        "discrimination": q.get("discrimination", 1.0),
    }


def demo_question(stage: str, adaptive_level: int) -> Dict[str, Any]:
    """
    Agar bank bo'sh bo'lsa yoki id topilmasa fallback.
    """
    return {
        "id": f"DEMO-{stage.upper()}-{adaptive_level}-{random.randint(1000,9999)}",
        "prompt": f"Demo question for {stage}. Choose A.",
        "choices": ["A", "B", "C", "D"],
        "answer_index": 0,
        "difficulty": adaptive_level if stage == "adaptive" else 2,
        "time_limit_sec": 25 if stage == "speed" else 60,
        "stage": stage,
        "section": stage,
        "category": "demo",
        "discrimination": 1.0,
    }


def pick_question(stage: str, adaptive_level: int) -> Dict[str, Any]:
    """
    Generator bankida "section" yo'q. Biz category/difficulty bilan tanlaymiz.
    """
    bank = QUESTION_BANK
    if not bank:
        return demo_question(stage, adaptive_level)

    CLASSIC_CATS = {
        "logic_sequence",
        "arithmetic_reasoning",
        "algebra_basic",
        "percent_ratio",
        "pattern_odd_one_out",
        "verbal_analogy_simple",
    }
    SPEED_CATS = {
        "arithmetic_reasoning",
        "percent_ratio",
        "pattern_odd_one_out",
        "verbal_analogy_simple",
    }

    candidates: List[Dict[str, Any]] = []
    for q in bank:
        diff = safe_int(q.get("difficulty", 2), 2)
        cat = (q.get("category") or "").strip()

        if stage == "adaptive":
            # adaptive: aynan current level
            if abs(diff - adaptive_level) <= 1:
                candidates.append(q)
        elif stage == "classic":
            if (cat in CLASSIC_CATS or not cat) and 2 <= diff <= 4:
                candidates.append(q)
        else:  # speed
            if (cat in SPEED_CATS or not cat) and 1 <= diff <= 3:
                candidates.append(q)

    if not candidates:
        candidates = bank

    raw = random.choice(candidates)
    return normalize_question(raw, stage, adaptive_level if stage == "adaptive" else 2)


def get_question_by_id_or_fallback(qid: str, stage: str, adaptive_level: int) -> Dict[str, Any]:
    raw = QUESTION_BY_ID.get(qid)
    if raw:
        return normalize_question(raw, stage, adaptive_level)
    return demo_question(stage, adaptive_level)


def stage_limits(stage: str) -> Dict[str, int]:
    # real test sizes
    if stage == "adaptive":
        return {"questions": 12}
    if stage == "classic":
        return {"questions": 18}
    return {"questions": 20}


# ===================== DB HELPERS (schema-safe) =====================
def table_has_column(con, table: str, col: str) -> bool:
    cur = con.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    cols = [r[1] for r in cur.fetchall()]
    return col in cols


def ensure_schema(con):
    """
    Siz ishlatayotgan maydonlar bo'lmasa, qo'shib qo'yamiz:
    - test_tokens.used_at
    - test_sessions.result_locked
    - test_sessions.unlock_token_id
    """
    cur = con.cursor()

    # test_tokens.used_at
    if table_has_column(con, "test_tokens", "used_at") is False:
        try:
            cur.execute("ALTER TABLE test_tokens ADD COLUMN used_at TEXT")
        except Exception:
            pass

    # test_sessions.result_locked
    if table_has_column(con, "test_sessions", "result_locked") is False:
        try:
            cur.execute("ALTER TABLE test_sessions ADD COLUMN result_locked INTEGER NOT NULL DEFAULT 1")
        except Exception:
            pass

    # test_sessions.unlock_token_id
    if table_has_column(con, "test_sessions", "unlock_token_id") is False:
        try:
            cur.execute("ALTER TABLE test_sessions ADD COLUMN unlock_token_id TEXT")
        except Exception:
            pass

    con.commit()


# ===================== TOKEN (unlock uchun) =====================
def create_token(con, user_id: str, paddle_txn_id: Optional[str] = None) -> str:
    token_id = str(uuid.uuid4())
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO test_tokens (id, user_id, status, created_at, paddle_txn_id, amount)
        VALUES (?, ?, 'unused', ?, ?, ?)
        """,
        (token_id, user_id, now_iso(), paddle_txn_id, PRICE_AMOUNT),
    )
    con.commit()
    return token_id


def mark_token_used(con, token_id: str):
    cur = con.cursor()
    if table_has_column(con, "test_tokens", "used_at"):
        cur.execute("UPDATE test_tokens SET status='used', used_at=? WHERE id=?", (now_iso(), token_id))
    else:
        cur.execute("UPDATE test_tokens SET status='used' WHERE id=?", (token_id,))
    con.commit()


# ===================== RESULT COMPUTE =====================
def compute_result(con, session_id: str) -> Dict[str, Any]:
    cur = con.cursor()
    cur.execute(
        """
        SELECT stage, is_correct, difficulty, time_spent_sec
        FROM test_answers
        WHERE session_id=?
        """,
        (session_id,),
    )
    rows = cur.fetchall()

    pts = {"adaptive": 0.0, "classic": 0.0, "speed": 0.0}
    max_pts = {"adaptive": 0.0, "classic": 0.0, "speed": 0.0}

    for r in rows:
        stage = r["stage"]
        if stage not in pts:
            continue

        diff = safe_int(r["difficulty"], 2)
        w = 1.0 + (diff - 1) * 0.15
        max_pts[stage] += w

        if safe_int(r["is_correct"], 0) == 1:
            pts[stage] += w
            if stage == "speed":
                t = safe_int(r["time_spent_sec"], 0)
                bonus = max(0.0, (30 - min(30, t)) / 30) * 0.2
                pts[stage] += bonus

    def norm(s):
        return 0.0 if max_pts[s] <= 0 else min(1.0, pts[s] / max_pts[s])

    final_norm = norm("adaptive") * 0.35 + norm("classic") * 0.45 + norm("speed") * 0.20
    iq = round(70 + final_norm * 60)

    if iq <= 70:
        perc = 2
    elif iq <= 85:
        perc = 16
    elif iq <= 100:
        perc = 50
    elif iq <= 110:
        perc = 75
    elif iq <= 115:
        perc = 84
    elif iq <= 120:
        perc = 91
    elif iq <= 125:
        perc = 95
    else:
        perc = 98

    return {"iq": iq, "percentile": perc, "final_norm": round(final_norm, 4)}


# ===================== API MODELS =====================
class StartResponse(BaseModel):
    session_id: str
    stage: str
    stage_index: int
    question_index: int
    question: dict


class AnswerRequest(BaseModel):
    session_id: str
    question_id: str
    chosen_index: int
    time_spent_sec: int = 0


class UnlockRequest(BaseModel):
    session_id: str
    paid: bool = True
    paddle_txn_id: Optional[str] = None


# ===================== STARTUP =====================
@APP.on_event("startup")
def _startup():
    init_db()
    with get_db() as con:
        ensure_schema(con)


# ===================== ACCESS =====================
@APP.get("/api/test/access")
def test_access(request: Request):
    user_id = ensure_user_id(request)
    return {"user_id": user_id, "price": PRICE_AMOUNT, "mode": "free_test_paid_result"}


# ===================== TEST START (FREE) =====================
@APP.post("/api/test/start", response_model=StartResponse)
def test_start(request: Request):
    user_id = ensure_user_id(request)

    with get_db() as con:
        ensure_schema(con)
        cur = con.cursor()

        cur.execute(
            """
            SELECT * FROM test_sessions
            WHERE user_id=? AND status='in_progress'
            ORDER BY started_at DESC LIMIT 1
            """,
            (user_id,),
        )
        sess = cur.fetchone()

        if sess:
            stage = sess["stage"]
            adaptive_level = safe_int(row_get(sess, "adaptive_level", 2), 2)
            q = pick_question(stage, adaptive_level)

            return StartResponse(
                session_id=sess["id"],
                stage=stage,
                stage_index=safe_int(row_get(sess, "stage_index", 1), 1),
                question_index=safe_int(row_get(sess, "question_index", 1), 1),
                question={
                    "id": q["id"],
                    "prompt": q["prompt"],
                    "choices": q["choices"],
                    "time_limit_sec": q.get("time_limit_sec", 60),
                    "stage": stage,
                    "difficulty": safe_int(q.get("difficulty", adaptive_level if stage == "adaptive" else 2), 2),
                },
            )

        # New session
        session_id = str(uuid.uuid4())
        stage = "adaptive"
        stage_index = 1
        question_index = 1
        adaptive_level = 2

        cur.execute(
            """
            INSERT INTO test_sessions
            (id, user_id, token_id, status, stage, stage_index, question_index, adaptive_level, started_at, result_locked, unlock_token_id)
            VALUES (?, ?, NULL, 'in_progress', ?, ?, ?, ?, ?, 1, NULL)
            """,
            (session_id, user_id, stage, stage_index, question_index, adaptive_level, now_iso()),
        )
        con.commit()

        q = pick_question(stage, adaptive_level)
        return StartResponse(
            session_id=session_id,
            stage=stage,
            stage_index=stage_index,
            question_index=question_index,
            question={
                "id": q["id"],
                "prompt": q["prompt"],
                "choices": q["choices"],
                "time_limit_sec": q.get("time_limit_sec", 60),
                "stage": stage,
                "difficulty": safe_int(q.get("difficulty", adaptive_level), 2),
            },
        )


# ===================== ANSWER (FREE) =====================
@APP.post("/api/test/answer")
def test_answer(request: Request, payload: AnswerRequest):
    user_id = ensure_user_id(request)

    with get_db() as con:
        ensure_schema(con)
        cur = con.cursor()

        cur.execute("SELECT * FROM test_sessions WHERE id=? AND user_id=?", (payload.session_id, user_id))
        sess = cur.fetchone()
        if not sess:
            raise HTTPException(404, "Session not found.")
        if sess["status"] != "in_progress":
            raise HTTPException(400, "Session already completed.")

        stage = sess["stage"]
        adaptive_level = safe_int(row_get(sess, "adaptive_level", 2), 2)

        # ✅ MUHIM: question_id bo'yicha savolni topamiz (random emas)
        q = get_question_by_id_or_fallback(payload.question_id, stage, adaptive_level)

        correct_index = safe_int(q.get("answer_index", 0), 0)
        difficulty = safe_int(q.get("difficulty", adaptive_level if stage == "adaptive" else 2), 2)
        is_correct = 1 if payload.chosen_index == correct_index else 0

        ans_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO test_answers
            (id, session_id, question_id, chosen_index, is_correct, stage, difficulty, time_spent_sec, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ans_id,
                payload.session_id,
                payload.question_id,
                payload.chosen_index,
                is_correct,
                stage,
                difficulty,
                int(payload.time_spent_sec),
                now_iso(),
            ),
        )

        # Adaptive update
        if stage == "adaptive":
            adaptive_level = min(5, adaptive_level + 1) if is_correct == 1 else max(1, adaptive_level - 1)

        q_index = safe_int(row_get(sess, "question_index", 1), 1) + 1
        limits = stage_limits(stage)

        # Stage finish?
        if q_index > limits["questions"]:
            if stage == "adaptive":
                stage = "classic"
                stage_index = 2
                q_index = 1
            elif stage == "classic":
                stage = "speed"
                stage_index = 3
                q_index = 1
            else:
                # finish test -> compute result -> LOCKED
                result = compute_result(con, payload.session_id)
                cur.execute(
                    """
                    UPDATE test_sessions
                    SET status='completed',
                        finished_at=?,
                        final_iq=?,
                        percentile=?,
                        result_locked=1,
                        unlock_token_id=NULL
                    WHERE id=? AND user_id=?
                    """,
                    (now_iso(), result["iq"], result["percentile"], payload.session_id, user_id),
                )
                con.commit()

                return {
                    "finished": True,
                    "result_locked": True,
                    "session_id": payload.session_id,
                    "price": PRICE_AMOUNT,
                    "message": "Test completed. Result is locked. Pay $1.49 to unlock your IQ score and report.",
                }

            cur.execute(
                """
                UPDATE test_sessions
                SET stage=?, stage_index=?, question_index=?, adaptive_level=?
                WHERE id=? AND user_id=?
                """,
                (stage, stage_index, q_index, adaptive_level, payload.session_id, user_id),
            )
        else:
            cur.execute(
                """
                UPDATE test_sessions
                SET question_index=?, adaptive_level=?
                WHERE id=? AND user_id=?
                """,
                (q_index, adaptive_level, payload.session_id, user_id),
            )

        con.commit()

        next_q = pick_question(stage, adaptive_level)

        cur.execute("SELECT stage_index FROM test_sessions WHERE id=? AND user_id=?", (payload.session_id, user_id))
        stage_index_db = safe_int(cur.fetchone()[0], 1)

        return {
            "finished": False,
            "stage": stage,
            "stage_index": stage_index_db,
            "question_index": q_index,
            "question": {
                "id": next_q["id"],
                "prompt": next_q["prompt"],
                "choices": next_q["choices"],
                "time_limit_sec": next_q.get("time_limit_sec", 60),
                "stage": stage,
                "difficulty": safe_int(next_q.get("difficulty", adaptive_level if stage == "adaptive" else 2), 2),
            },
        }


# ===================== UNLOCK RESULT (paid) =====================
@APP.post("/api/payment/unlock")
def unlock_result(request: Request, payload: UnlockRequest):
    """
    HOZIRCHA DEMO: frontend paid=true yuborsa unlock bo'ladi.
    Keyingi bosqichda Paddle webhook bilan faqat payment_succeeded bo'lsa unlock qilamiz.
    """
    user_id = ensure_user_id(request)
    if not payload.paid:
        raise HTTPException(402, "Payment required.")

    with get_db() as con:
        ensure_schema(con)
        cur = con.cursor()

        cur.execute("SELECT * FROM test_sessions WHERE id=? AND user_id=?", (payload.session_id, user_id))
        sess = cur.fetchone()
        if not sess:
            raise HTTPException(404, "Session not found.")
        if sess["status"] != "completed":
            raise HTTPException(400, "Session is not completed yet.")

        # Already unlocked?
        if safe_int(row_get(sess, "result_locked", 1), 1) == 0:
            return {"ok": True, "session_id": payload.session_id, "already_unlocked": True}

        token_id = create_token(con, user_id, paddle_txn_id=payload.paddle_txn_id or "MANUAL")
        mark_token_used(con, token_id)

        cur.execute(
            """
            UPDATE test_sessions
            SET result_locked=0, unlock_token_id=?
            WHERE id=? AND user_id=?
            """,
            (token_id, payload.session_id, user_id),
        )
        con.commit()

        return {"ok": True, "session_id": payload.session_id, "unlock_token_id": token_id}


# ===================== GET RESULT (only if unlocked) =====================
@APP.get("/api/test/result")
def get_result(request: Request, session_id: str):
    user_id = ensure_user_id(request)

    with get_db() as con:
        ensure_schema(con)
        cur = con.cursor()

        cur.execute("SELECT * FROM test_sessions WHERE id=? AND user_id=?", (session_id, user_id))
        sess = cur.fetchone()
        if not sess:
            raise HTTPException(404, "Session not found.")
        if sess["status"] != "completed":
            raise HTTPException(400, "Session is not completed yet.")

        if safe_int(row_get(sess, "result_locked", 1), 1) == 1:
            raise HTTPException(402, "Payment required. Result is locked.")

        return {
            "session_id": session_id,
            "unlocked": True,
            "iq": row_get(sess, "final_iq"),
            "percentile": row_get(sess, "percentile"),
            "message": "Unlocked result.",
        }


# ===================== STATUS =====================
@APP.get("/api/test/status")
def test_status(request: Request):
    user_id = ensure_user_id(request)
    with get_db() as con:
        ensure_schema(con)
        cur = con.cursor()
        cur.execute(
            """
            SELECT * FROM test_sessions
            WHERE user_id=?
            ORDER BY started_at DESC LIMIT 1
            """,
            (user_id,),
        )
        sess = cur.fetchone()
        return {"session": dict(sess) if sess else None}


# ===================== HEALTH =====================
@APP.get("/api/health")
def health():
    return {
        "ok": True,
        "time": now_iso(),
        "price": PRICE_AMOUNT,
        "mode": "free_test_paid_result",
        "qb_path": QB_PATH,
        "qb_exists": os.path.exists(QB_PATH),
        "bank_len": len(QUESTION_BANK),
    }