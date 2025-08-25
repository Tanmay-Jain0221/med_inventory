# src/apply_daily_dosage.py
import sqlite3
from pathlib import Path
from datetime import date, datetime
import argparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB = PROJECT_ROOT / "db" / "inventory.sqlite"

def log_ts(run_date: str) -> str:
    # Use 20:00:00 as a fixed time for clarity (same day you requested)
    return f"{run_date} 20:00:00"

def already_ran_for(conn, run_date: str) -> bool:
    q = """
    SELECT EXISTS(
      SELECT 1 FROM stock_moves
      WHERE reason = 'daily_dose' AND date(ts) = date(?)
    )
    """
    return bool(conn.execute(q, (run_date,)).fetchone()[0])

def scrap_expired(conn, run_date: str, verbose: bool = False):
    cur = conn.cursor()
    cur.executescript("""
    CREATE TEMP TABLE IF NOT EXISTS _to_scrap (
      batch_id    INTEGER,
      medicine_id TEXT,
      qty         INTEGER
    );
    DELETE FROM _to_scrap;
    """)
    cur.execute("""
        INSERT INTO _to_scrap (batch_id, medicine_id, qty)
        SELECT batch_id, medicine_id, stock_units
        FROM batches
        WHERE stock_units > 0 AND expiry_date IS NOT NULL
          AND date(expiry_date) < date(?)
    """, (run_date,))
    cur.execute("""
        UPDATE batches
        SET stock_units = 0
        WHERE batch_id IN (SELECT batch_id FROM _to_scrap)
    """)
    cur.execute("""
        INSERT INTO stock_moves (ts, medicine_id, batch_id, qty_change, reason, note)
        SELECT ?, medicine_id, batch_id, -qty, 'expired',
               'Auto-scrap expired before ' || ?
        FROM _to_scrap
        WHERE qty > 0
    """, (log_ts(run_date), run_date))
    if verbose:
        n = conn.execute("SELECT COUNT(*) FROM _to_scrap WHERE qty > 0").fetchone()[0]
        print(f"[DEBUG] Scrapped expired batches: {n}")

def fefo_deduct(conn, run_date: str, verbose: bool = False):
    cur = conn.cursor()
    plan = cur.execute("""
        SELECT medicine_id, units_per_day
        FROM v_daily_units
        WHERE units_per_day > 0
    """).fetchall()
    if not plan:
        print("[INFO] No daily dosage > 0 found. Nothing to deduct.")
        return

    for med_id, need in plan:
        remaining = float(need)
        if verbose:
            print(f"[DEBUG] {med_id}: need {remaining}")

        # FEFO: earliest expiry first; NULL expiry last
        cur.execute("""
            SELECT batch_id, stock_units
            FROM batches
            WHERE medicine_id = ?
              AND stock_units > 0
              AND (expiry_date IS NULL OR date(expiry_date) >= date(?))
            ORDER BY (expiry_date IS NULL) ASC, date(expiry_date) ASC, batch_id ASC
        """, (med_id, run_date))

        for batch_id, stock in cur.fetchall():
            if remaining <= 0: break
            take = min(float(stock), remaining)
            if take <= 0: continue

            cur.execute("UPDATE batches SET stock_units = stock_units - ? WHERE batch_id = ?",
                        (take, batch_id))
            cur.execute("""
                INSERT INTO stock_moves (ts, medicine_id, batch_id, qty_change, reason, note)
                VALUES (?, ?, ?, ?, 'daily_dose', ?)
            """, (log_ts(run_date), med_id, batch_id, -take, f"FEFO daily deduction {run_date}"))
            remaining -= take
            if verbose:
                print(f"  - batch {batch_id}: took {take}")

        if remaining > 1e-6:
            cur.execute("""
                INSERT INTO stock_moves (ts, medicine_id, batch_id, qty_change, reason, note)
                VALUES (?, ?, NULL, 0, 'shortfall', ?)
            """, (log_ts(run_date), med_id, f"Needed {remaining} more units on {run_date}"))
            if verbose:
                print(f"  ! shortfall {remaining}")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Apply for YYYY-MM-DD (default: today)")
    parser.add_argument("--force", action="store_true", help="Run even if already applied for that date")
    parser.add_argument("--verbose", action="store_true", help="Print debug info")
    args = parser.parse_args()

    run_date = args.date or date.today().strftime("%Y-%m-%d")

    with sqlite3.connect(DB) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")

        if already_ran_for(conn, run_date) and not args.force:
            print(f"[SKIP] FEFO already applied for {run_date}. Use --force to override.")
            return

        if args.verbose:
            print(f"[DEBUG] DB: {DB}")
            print(f"[DEBUG] Run date: {run_date}")

        # 1) Scrap expired before that date
        scrap_expired(conn, run_date, verbose=args.verbose)

        # 2) Deduct FEFO for that date
        fefo_deduct(conn, run_date, verbose=args.verbose)

        conn.commit()

        print(f"[OK] FEFO daily deduction complete for {run_date}.")

        if args.verbose:
            rows = conn.execute("""
                SELECT ts, medicine_id, batch_id, qty_change, reason, note
                FROM stock_moves
                WHERE date(ts) = date(?)
                ORDER BY ts, id
            """, (run_date,)).fetchall()
            print("[DEBUG] Moves for the day:")
            for r in rows:
                print(" ", r)

if __name__ == "__main__":
    main()
