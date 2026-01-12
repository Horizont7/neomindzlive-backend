# db.py
import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "neomindz.db"))


def _table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def _get_columns(cur: sqlite3.Cursor, table: str) -> dict:
    cur.execute(f"PRAGMA table_info({table})")
    # row: (cid, name, type, notnull, dflt_value, pk)
    return {r[1]: {"type": r[2], "notnull": r[3], "dflt": r[4], "pk": r[5]} for r in cur.fetchall()}


def _rebuild_test_sessions_table(con: sqlite3.Connection):
    """
    SQLite'da NOT NULL ni olib tashlab bo'lmaydi, shuning uchun
    eski test_sessions'ni yangi sxema bilan qayta yig'amiz.
    """
    cur = con.cursor()

    # Eski jadvaldan ustunlar
    cols = _get_columns(cur, "test_sessions")
    if not cols:
        return

    # Yangi jadval (FREEMIUM model)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS test_sessions_new (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,

        -- test tekin: token sessionga majburiy emas
        token_id TEXT,

        status TEXT NOT NULL,          -- in_progress | completed
        stage TEXT NOT NULL,           -- adaptive | classic | speed
        stage_index INTEGER NOT NULL,  -- 1..3
        question_index INTEGER NOT NULL,
        adaptive_level INTEGER NOT NULL DEFAULT 2,

        started_at TEXT NOT NULL,
        finished_at TEXT,
        final_iq INTEGER,
        percentile INTEGER,

        -- natija blok (pulli unlock)
        result_locked INTEGER NOT NULL DEFAULT 1,
        unlock_token_id TEXT,

        FOREIGN KEY(token_id) REFERENCES test_tokens(id),
        FOREIGN KEY(unlock_token_id) REFERENCES test_tokens(id)
    )
    """)

    # Qaysi ustunlar eski jadvalda borligini tekshirib, mos ko'chiramiz
    existing = set(cols.keys())

    # Eski jadvalda bo'lmagan yangi ustunlar uchun default qo'yiladi
    select_parts = [
        "id",
        "user_id",
        "token_id" if "token_id" in existing else "NULL AS token_id",
        "status",
        "stage",
        "stage_index",
        "question_index",
        "adaptive_level" if "adaptive_level" in existing else "2 AS adaptive_level",
        "started_at",
        "finished_at" if "finished_at" in existing else "NULL AS finished_at",
        "final_iq" if "final_iq" in existing else "NULL AS final_iq",
        "percentile" if "percentile" in existing else "NULL AS percentile",
        "result_locked" if "result_locked" in existing else "1 AS result_locked",
        "unlock_token_id" if "unlock_token_id" in existing else "NULL AS unlock_token_id",
    ]

    cur.execute(f"""
    INSERT INTO test_sessions_new (
        id, user_id, token_id, status, stage, stage_index, question_index, adaptive_level,
        started_at, finished_at, final_iq, percentile, result_locked, unlock_token_id
    )
    SELECT {", ".join(select_parts)}
    FROM test_sessions
    """)

    cur.execute("DROP TABLE test_sessions")
    cur.execute("ALTER TABLE test_sessions_new RENAME TO test_sessions")


def init_db():
    with sqlite3.connect(DB_PATH) as con:
        cur = con.cursor()

        # 1) Tokens (to'lov bo'lganda yoziladi)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS test_tokens (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,

            -- token faqat "unlock" uchun ishlatiladi
            status TEXT NOT NULL,          -- unused | used
            created_at TEXT NOT NULL,
            used_at TEXT,

            paddle_txn_id TEXT,
            amount REAL NOT NULL DEFAULT 1.49
        )
        """)

        # 2) Sessions (test tekin + natija locked)
        if not _table_exists(cur, "test_sessions"):
            cur.execute("""
            CREATE TABLE IF NOT EXISTS test_sessions (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                token_id TEXT,

                status TEXT NOT NULL,          -- in_progress | completed
                stage TEXT NOT NULL,           -- adaptive | classic | speed
                stage_index INTEGER NOT NULL,  -- 1..3
                question_index INTEGER NOT NULL,
                adaptive_level INTEGER NOT NULL DEFAULT 2,

                started_at TEXT NOT NULL,
                finished_at TEXT,
                final_iq INTEGER,
                percentile INTEGER,

                result_locked INTEGER NOT NULL DEFAULT 1,
                unlock_token_id TEXT,

                FOREIGN KEY(token_id) REFERENCES test_tokens(id),
                FOREIGN KEY(unlock_token_id) REFERENCES test_tokens(id)
            )
            """)
        else:
            # Eski jadval bo'lsa: token_id NOT NULL bo'lishi mumkin => rebuild qilamiz
            cols = _get_columns(cur, "test_sessions")
            token_notnull = cols.get("token_id", {}).get("notnull", 0) == 1

            # Yangi ustunlar yo'q bo'lsa ham rebuild eng toza yo'l
            need_new_cols = ("result_locked" not in cols) or ("unlock_token_id" not in cols)
            if token_notnull or need_new_cols:
                _rebuild_test_sessions_table(con)

        # 3) Answers
        if not _table_exists(cur, "test_answers"):
            cur.execute("""
            CREATE TABLE IF NOT EXISTS test_answers (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                question_id TEXT NOT NULL,
                chosen_index INTEGER NOT NULL,
                is_correct INTEGER NOT NULL,
                stage TEXT NOT NULL,
                difficulty INTEGER NOT NULL,
                time_spent_sec INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                FOREIGN KEY(session_id) REFERENCES test_sessions(id)
            )
            """)

        con.commit()


@contextmanager
def get_db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()
