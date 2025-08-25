import pandas as pd
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXCEL = PROJECT_ROOT / "data" / "inventory.xlsx"
DB    = PROJECT_ROOT / "db"   / "inventory.sqlite"

def upsert_table(df, table, conn, pk_cols):
    """Delete-by-PK then fresh insert (simple, deterministic upsert)."""
    placeholders = ",".join("?" for _ in df.columns)
    cols_csv = ",".join(df.columns)
    with conn:
        if len(df):
            where = " OR ".join("(" + " AND ".join(f"{c}=?" for c in pk_cols) + ")" for _ in range(len(df)))
            vals = []
            for _, row in df[pk_cols].iterrows():
                vals.extend(row.tolist())
            conn.execute(f"DELETE FROM {table} WHERE {where}", vals)
        conn.executemany(f"INSERT INTO {table} ({cols_csv}) VALUES ({placeholders})",
                         df.itertuples(index=False, name=None))

def main():
    x = pd.ExcelFile(EXCEL)

    suppliers = pd.read_excel(x, "SuppliersTb")
    medicines = pd.read_excel(x, "MedicinesTb")
    batches   = pd.read_excel(x, "BatchesTb")
    dosage    = pd.read_excel(x, "DailyDosageTb")

    # Drop trailing empty Excel columns
    for df in (suppliers, medicines, batches, dosage):
        df.drop(columns=[c for c in df.columns if str(c).startswith("Unnamed")],
                inplace=True, errors="ignore")

   
    # SuppliersTb
    if "supplier_id" in suppliers.columns:
        suppliers["supplier_id"] = suppliers["supplier_id"].astype(str).str.strip()

    # MedicinesTb
    if "id" in medicines.columns:
        medicines["id"] = medicines["id"].astype(str).str.strip()

    # BatchesTb
    batches["medicine_id"] = batches["medicine_id"].astype(str).str.strip()
    batches["batch_no"]    = batches["batch_no"].astype(str).str.strip()

    # Ensure integer, non-negative stock
    batches["stock_units"] = (
    pd.to_numeric(batches["stock_units"], errors="coerce")
      .fillna(0).astype(int)
)
    batches["stock_units"] = batches["stock_units"].clip(lower=0)

    # Date cleanup to ISO format (YYYY-MM-DD)
    for c in ("expiry_date", "last_updated"):
        if c in batches.columns:
            batches[c] = pd.to_datetime(batches[c], errors="coerce").dt.strftime("%Y-%m-%d")

    # Avoid duplicate (medicine_id, batch_no) rows in the input
    batches = batches.drop_duplicates(subset=["medicine_id","batch_no"], keep="last")

    # Prepare batches insert (exclude autoincrement batch_id; let trigger manage last_updated)
    batch_cols = ["medicine_id", "batch_no", "stock_units", "expiry_date"]
    batches_ins = batches[batch_cols].copy()

    # DailyDosageTb (creating type of slots)
    slot_cols = ["before_bf","after_bf","at_8pm","after_dinner"]
    for c in slot_cols:
        if c in dosage.columns:
            dosage[c] = pd.to_numeric(dosage[c], errors="coerce").fillna(0).astype(int)
        else:
            dosage[c] = 0
    # If daily_dosage column exists, keep it consistent with the sum of slots
    dosage["daily_dosage"] = dosage[slot_cols].sum(axis=1).astype(int)

    # Write to inventory.sqlite
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys=ON;")

    upsert_table(
        suppliers[["supplier_id","supplier_name","lead_time"]],
        "suppliers", conn, ["supplier_id"]
    )

    upsert_table(
        medicines[["id","medicine_name","salt","uses","daily_dose","supplier_id","reorder_level"]],
        "medicines", conn, ["id"]
    )

    upsert_table(
        batches_ins,
        "batches", conn, ["medicine_id","batch_no"]
    )

    upsert_table(
        dosage[["medicine_id","before_bf","after_bf","at_8pm","after_dinner","daily_dosage"]],
        "daily_dosage", conn, ["medicine_id"]
    )

    # Brief counts
    for t in ("suppliers","medicines","batches","daily_dosage"):
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t}: {n}")

    conn.close()

if __name__ == "__main__":
    main()
