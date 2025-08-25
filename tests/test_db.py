from pathlib import Path
import sqlite3
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db" / "inventory.sqlite"
EXPORT_CSV = False  # set True to save CSVs in reports/
EXPIRY_WINDOW_DAYS = 60

def q(conn, sql, params=None):
    return pd.read_sql_query(sql, conn, params=params or ())

def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)

    # checks - Total stock per medicine (sums across batches)
    total_stock_sql = """
    SELECT m.id, m.medicine_name,
           COALESCE(SUM(b.stock_units), 0) AS total_stock
    FROM medicines m
    LEFT JOIN batches b ON b.medicine_id = m.id
    GROUP BY m.id, m.medicine_name
    ORDER BY m.medicine_name;
    """
    df_stock = q(conn, total_stock_sql)
    print("\n=== Total stock per medicine ===")
    print(df_stock.to_string(index=False))

    # checks - Expiring soon (next N days)
    expiring_sql = """
    SELECT m.medicine_name, b.batch_no, b.stock_units, b.expiry_date
    FROM batches b
    JOIN medicines m ON m.id = b.medicine_id
    WHERE DATE(b.expiry_date) <= DATE('now', ?)
    ORDER BY b.expiry_date;
    """
    df_expiring = q(conn, expiring_sql, (f'+{EXPIRY_WINDOW_DAYS} day',))
    print(f"\n=== Batches expiring in next {EXPIRY_WINDOW_DAYS} days ===")
    print(df_expiring.to_string(index=False) if not df_expiring.empty else "None")

    # checks - Below reorder level (compare total stock vs medicine.reorder_level)
    below_reorder_sql = """
    WITH stock AS (
      SELECT medicine_id, SUM(stock_units) AS total_stock
      FROM batches GROUP BY medicine_id
    )
    SELECT m.id, m.medicine_name,
           COALESCE(s.total_stock, 0) AS total_stock,
           m.reorder_level
    FROM medicines m
    LEFT JOIN stock s ON s.medicine_id = m.id
    WHERE COALESCE(s.total_stock,0) < m.reorder_level
    ORDER BY total_stock, m.medicine_name;
    """
    df_below = q(conn, below_reorder_sql)
    print("\n=== Medicines below reorder level ===")
    print(df_below.to_string(index=False) if not df_below.empty else "None")

    # 4) Daily dosage plan (joined for readability)
    dosage_sql = """
    SELECT m.medicine_name,
           d.before_bf, d.after_bf, d.at_8pm, d.after_dinner, d.daily_dosage
    FROM daily_dosage d
    JOIN medicines m ON m.id = d.medicine_id
    ORDER BY m.medicine_name;
    """
    df_dosage = q(conn, dosage_sql)
    print("\n=== Daily dosage plan ===")
    print(df_dosage.to_string(index=False))

    # Optional CSV export
    if EXPORT_CSV:
        out_dir = PROJECT_ROOT / "reports"
        out_dir.mkdir(exist_ok=True)
        df_stock.to_csv(out_dir / "stock_by_medicine.csv", index=False)
        df_expiring.to_csv(out_dir / "expiring_soon.csv", index=False)
        df_below.to_csv(out_dir / "below_reorder.csv", index=False)
        df_dosage.to_csv(out_dir / "daily_dosage.csv", index=False)
        print(f"\nCSV reports written to: {out_dir}")

    conn.close()

if __name__ == "__main__":
    main()
