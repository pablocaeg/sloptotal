"""Database connection management and CRUD operations for SQLite."""

import logging
import threading
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import aiosqlite

from app.config import DATABASE_PATH, DATA_DIR, DB_TIMEOUT, DB_BUSY_TIMEOUT
from app.schemas import AnalysisReport, EngineResult, Verdict

log = logging.getLogger("sloptotal.database")

# Thread-local storage for sync connections (used in ThreadPoolExecutor callbacks)
_thread_local = threading.local()

# Lock for thread-local connection cleanup
_connections_lock = threading.Lock()
_all_connections: list[sqlite3.Connection] = []


async def init_database() -> None:
    """Create database tables at startup."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log.info(f"Initializing database at {DATABASE_PATH}")

    async with aiosqlite.connect(DATABASE_PATH, timeout=DB_TIMEOUT) as db:
        # Enable WAL mode for better concurrent access
        await db.execute("PRAGMA journal_mode=WAL")
        # Enable foreign key constraints
        await db.execute("PRAGMA foreign_keys=ON")
        # Set busy timeout
        await db.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT}")

        # Create reports table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY,
                text_hash TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source TEXT NOT NULL,
                text_excerpt TEXT NOT NULL,
                word_count INTEGER NOT NULL,
                overall_score REAL DEFAULT 0.0,
                overall_verdict TEXT DEFAULT 'Scanning...',
                engines_flagged INTEGER DEFAULT 0,
                engines_total INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        # Create engine_results table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS engine_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
                engine_key TEXT NOT NULL,
                engine_name TEXT NOT NULL,
                score REAL NOT NULL,
                verdict TEXT NOT NULL,
                details TEXT NOT NULL,
                description TEXT DEFAULT '',
                UNIQUE(report_id, engine_key)
            )
        """)

        # Create scan_log table for snippet/URL/quick scan telemetry
        await db.execute("""
            CREATE TABLE IF NOT EXISTS scan_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_type TEXT NOT NULL,
                text_excerpt TEXT,
                text_hash TEXT,
                chars INTEGER,
                score REAL,
                indicator TEXT,
                confidence TEXT,
                bert REAL,
                e5 REAL,
                tmr REAL,
                fakespot REAL,
                guard_hit INTEGER DEFAULT 0,
                tier TEXT,
                source_url TEXT,
                source_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migrate scan_log: add structural analysis columns (safe if already exist)
        _structural_columns = [
            ("structural_score", "REAL"),
            ("structural_signal_count", "INTEGER"),
            ("structural_linguistic", "REAL"),
            ("structural_formulaic", "REAL"),
            ("structural_structural", "REAL"),
            ("structural_vocabulary", "REAL"),
            ("structural_readability", "REAL"),
            ("structural_sentiment", "REAL"),
            ("ml_score", "REAL"),
            ("blended", "INTEGER DEFAULT 0"),
        ]
        for col_name, col_type in _structural_columns:
            try:
                await db.execute(
                    f"ALTER TABLE scan_log ADD COLUMN {col_name} {col_type}"
                )
            except Exception:
                pass  # Column already exists

        # Create indexes
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_text_hash ON reports(text_hash)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_engine_results_report ON engine_results(report_id)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_scan_log_created ON scan_log(created_at DESC)"
        )
        await db.execute(
            "CREATE INDEX IF NOT EXISTS idx_scan_log_type ON scan_log(scan_type)"
        )

        await db.commit()
        log.info("Database initialized successfully")


async def check_database_health() -> dict[str, Any]:
    """Check database health for monitoring."""
    try:
        async with aiosqlite.connect(DATABASE_PATH, timeout=5.0) as db:
            cursor = await db.execute("SELECT COUNT(*) FROM reports")
            row = await cursor.fetchone()
            report_count = row[0] if row else 0

            cursor = await db.execute(
                "SELECT COUNT(*) FROM reports WHERE completed_at IS NOT NULL"
            )
            row = await cursor.fetchone()
            completed_count = row[0] if row else 0

            return {
                "status": "healthy",
                "total_reports": report_count,
                "completed_reports": completed_count,
                "database_path": str(DATABASE_PATH),
            }
    except Exception as e:
        log.error(f"Database health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "database_path": str(DATABASE_PATH),
        }


def cleanup_connections() -> None:
    """Close all thread-local connections. Call on shutdown."""
    with _connections_lock:
        for conn in _all_connections:
            try:
                conn.close()
            except Exception as e:
                log.warning(f"Error closing connection: {e}")
        _all_connections.clear()
    log.info("Database connections cleaned up")


@asynccontextmanager
async def get_db():
    """Async context manager for database connections."""
    db = await aiosqlite.connect(DATABASE_PATH, timeout=DB_TIMEOUT)
    db.row_factory = aiosqlite.Row
    try:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT}")
        yield db
    finally:
        await db.close()


def get_sync_connection() -> sqlite3.Connection:
    """Get thread-local sync connection for use in ThreadPoolExecutor callbacks."""
    if not hasattr(_thread_local, "connection") or _thread_local.connection is None:
        conn = sqlite3.connect(
            DATABASE_PATH,
            check_same_thread=False,
            timeout=DB_TIMEOUT,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(f"PRAGMA busy_timeout={DB_BUSY_TIMEOUT}")
        _thread_local.connection = conn
        with _connections_lock:
            _all_connections.append(conn)
    return _thread_local.connection


async def create_report(
    report_id: str,
    text_hash: str,
    source_type: str,
    source: str,
    text_excerpt: str,
    word_count: int,
    engines_total: int,
) -> None:
    """Insert a new report into the database."""
    async with get_db() as db:
        try:
            await db.execute(
                """
                INSERT INTO reports (id, text_hash, source_type, source, text_excerpt, word_count, engines_total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report_id,
                    text_hash,
                    source_type,
                    source,
                    text_excerpt,
                    word_count,
                    engines_total,
                ),
            )
            await db.commit()
            log.debug(f"Created report {report_id}")
        except sqlite3.IntegrityError as e:
            log.warning(f"Report {report_id} already exists: {e}")
            raise


async def get_report(report_id: str) -> AnalysisReport | None:
    """Fetch a report with all engine results."""
    if not report_id or len(report_id) > 12:
        return None

    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM reports WHERE id = ?", (report_id,))
        row = await cursor.fetchone()
        if not row:
            return None

        cursor = await db.execute(
            "SELECT * FROM engine_results WHERE report_id = ? ORDER BY id",
            (report_id,),
        )
        result_rows = await cursor.fetchall()

        engine_results = [
            EngineResult(
                engine_name=r["engine_name"],
                score=r["score"],
                verdict=Verdict(r["verdict"]),
                details=r["details"],
                description=r["description"] or "",
            )
            for r in result_rows
        ]

        created_at = row["created_at"]
        if isinstance(created_at, str):
            try:
                created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            except ValueError:
                created_at = datetime.utcnow()
        elif created_at is None:
            created_at = datetime.utcnow()

        return AnalysisReport(
            id=row["id"],
            source_type=row["source_type"],
            source=row["source"],
            text_excerpt=row["text_excerpt"],
            word_count=row["word_count"],
            engine_results=engine_results,
            overall_score=row["overall_score"],
            overall_verdict=row["overall_verdict"],
            engines_flagged=row["engines_flagged"],
            engines_total=row["engines_total"],
            created_at=created_at,
        )


async def get_report_by_hash(text_hash: str) -> AnalysisReport | None:
    """Cache lookup: find a completed report by text hash."""
    if not text_hash or len(text_hash) != 64:
        return None

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM reports WHERE text_hash = ? AND completed_at IS NOT NULL ORDER BY created_at DESC LIMIT 1",
            (text_hash,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return await get_report(row["id"])


async def get_pending_report_by_hash(text_hash: str) -> str | None:
    """Check if there's a pending (incomplete) report for this text hash."""
    if not text_hash or len(text_hash) != 64:
        return None

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id FROM reports WHERE text_hash = ? AND completed_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (text_hash,),
        )
        row = await cursor.fetchone()
        return row["id"] if row else None


async def get_recent_reports(limit: int = 10) -> list[AnalysisReport]:
    """Return the most recent completed reports (newest first)."""
    limit = min(max(1, limit), 100)

    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id FROM reports
            WHERE completed_at IS NOT NULL
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()

    reports = []
    for row in rows:
        report = await get_report(row["id"])
        if report:
            reports.append(report)
    return reports


async def update_report_score(
    report_id: str,
    overall_score: float,
    overall_verdict: str,
    engines_flagged: int,
) -> None:
    """Update a report's aggregate scores."""
    async with get_db() as db:
        await db.execute(
            """
            UPDATE reports
            SET overall_score = ?, overall_verdict = ?, engines_flagged = ?
            WHERE id = ?
            """,
            (overall_score, overall_verdict, engines_flagged, report_id),
        )
        await db.commit()


async def mark_report_complete(report_id: str) -> None:
    """Set completed_at timestamp to enable future cache hits."""
    async with get_db() as db:
        await db.execute(
            "UPDATE reports SET completed_at = CURRENT_TIMESTAMP WHERE id = ?",
            (report_id,),
        )
        await db.commit()
        log.debug(f"Marked report {report_id} as complete")


def insert_engine_result_sync(
    report_id: str,
    engine_key: str,
    engine_name: str,
    score: float,
    verdict: str,
    details: str,
    description: str,
) -> None:
    """Thread-safe insert of engine result (for use in ThreadPoolExecutor callbacks)."""
    conn = get_sync_connection()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO engine_results
            (report_id, engine_key, engine_name, score, verdict, details, description)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (report_id, engine_key, engine_name, score, verdict, details, description),
        )
        conn.commit()
    except sqlite3.Error as e:
        log.error(f"Failed to insert engine result for {report_id}/{engine_key}: {e}")
        raise


def update_report_score_sync(
    report_id: str,
    overall_score: float,
    overall_verdict: str,
    engines_flagged: int,
) -> None:
    """Thread-safe update of report scores (for use in ThreadPoolExecutor callbacks)."""
    conn = get_sync_connection()
    try:
        conn.execute(
            """
            UPDATE reports
            SET overall_score = ?, overall_verdict = ?, engines_flagged = ?
            WHERE id = ?
            """,
            (overall_score, overall_verdict, engines_flagged, report_id),
        )
        conn.commit()
    except sqlite3.Error as e:
        log.error(f"Failed to update report score for {report_id}: {e}")
        raise


def log_scan_sync(
    scan_type: str,
    text_excerpt: str,
    text_hash: str,
    chars: int,
    score: float,
    indicator: str,
    confidence: str,
    bert: float,
    e5: float,
    tmr: float,
    fakespot: float,
    guard_hit: bool = False,
    tier: str = "",
    source_url: str = "",
    source_id: str = "",
    # Structural analysis fields (optional)
    structural_score: float | None = None,
    structural_signal_count: int | None = None,
    structural_linguistic: float | None = None,
    structural_formulaic: float | None = None,
    structural_structural: float | None = None,
    structural_vocabulary: float | None = None,
    structural_readability: float | None = None,
    structural_sentiment: float | None = None,
    ml_score: float | None = None,
    blended: bool = False,
) -> None:
    """Log a snippet/URL/quick scan result for later analysis. Non-blocking."""
    conn = get_sync_connection()
    try:
        conn.execute(
            """
            INSERT INTO scan_log
            (scan_type, text_excerpt, text_hash, chars, score, indicator, confidence,
             bert, e5, tmr, fakespot, guard_hit, tier, source_url, source_id,
             structural_score, structural_signal_count,
             structural_linguistic, structural_formulaic, structural_structural,
             structural_vocabulary, structural_readability, structural_sentiment,
             ml_score, blended)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan_type,
                text_excerpt[:500],
                text_hash,
                chars,
                score,
                indicator,
                confidence,
                bert,
                e5,
                tmr,
                fakespot,
                int(guard_hit),
                tier,
                source_url,
                source_id,
                structural_score,
                structural_signal_count,
                structural_linguistic,
                structural_formulaic,
                structural_structural,
                structural_vocabulary,
                structural_readability,
                structural_sentiment,
                ml_score,
                int(blended),
            ),
        )
        conn.commit()
    except sqlite3.Error as e:
        log.warning(f"Failed to log scan: {e}")


async def get_scan_stats() -> dict:
    """Get scan log statistics for the API."""
    async with get_db() as db:
        cursor = await db.execute("SELECT COUNT(*) FROM scan_log")
        total = (await cursor.fetchone())[0]

        cursor = await db.execute(
            "SELECT scan_type, COUNT(*) as cnt, AVG(score) as avg_score, "
            "AVG(bert) as avg_bert, AVG(e5) as avg_e5, AVG(tmr) as avg_tmr, "
            "AVG(fakespot) as avg_fakespot, SUM(guard_hit) as guard_hits "
            "FROM scan_log GROUP BY scan_type"
        )
        rows = await cursor.fetchall()
        by_type = {
            row["scan_type"]: {
                "count": row["cnt"],
                "avg_score": round(row["avg_score"], 1) if row["avg_score"] else 0,
                "avg_bert": round(row["avg_bert"], 4) if row["avg_bert"] else 0,
                "avg_e5": round(row["avg_e5"], 4) if row["avg_e5"] else 0,
                "avg_tmr": round(row["avg_tmr"], 4) if row["avg_tmr"] else 0,
                "avg_fakespot": round(row["avg_fakespot"], 4)
                if row["avg_fakespot"]
                else 0,
                "guard_hits": row["guard_hits"] or 0,
            }
            for row in rows
        }

        # Score distribution
        cursor = await db.execute(
            "SELECT indicator, COUNT(*) as cnt FROM scan_log GROUP BY indicator"
        )
        dist = {row["indicator"]: row["cnt"] for row in await cursor.fetchall()}

        # Recent scans
        cursor = await db.execute(
            "SELECT * FROM scan_log ORDER BY created_at DESC LIMIT 50"
        )
        recent = [dict(row) for row in await cursor.fetchall()]

        return {
            "total_scans": total,
            "by_type": by_type,
            "score_distribution": dist,
            "recent": recent,
        }
