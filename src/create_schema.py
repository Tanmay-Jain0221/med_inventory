from pathlib import Path
import sqlite3

DB_PATH = Path("db/inventory.sqlite")

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

-- SuppliersTb
CREATE TABLE IF NOT EXISTS suppliers (
  supplier_id TEXT PRIMARY KEY,
  supplier_name TEXT NOT NULL,
  lead_time INTEGER NOT NULL              -- in days
);

-- MedicinesTb
CREATE TABLE IF NOT EXISTS medicines (
  id TEXT PRIMARY KEY,                    -- medicine_id (entered from Excel)
  medicine_name TEXT NOT NULL,            -- full name of medicine
  salt TEXT,                              -- salt composition
  uses TEXT,                              -- uses of the medicine
  daily_dose REAL DEFAULT 0,              -- (optional legacy) suggested daily dose
  supplier_id TEXT,                       -- supplier reference
  reorder_level INTEGER DEFAULT 0,        -- ROL= LT * Daily dose
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (supplier_id)
    REFERENCES suppliers(supplier_id)
    ON DELETE CASCADE
);

-- BatchesTb
CREATE TABLE IF NOT EXISTS batches (
  batch_id INTEGER PRIMARY KEY AUTOINCREMENT, -- system-generated unique ID
  medicine_id TEXT NOT NULL,                  -- foreign key to medicines.id
  batch_no TEXT NOT NULL,                     -- batch number (i.e medicine_ID_batch)
  stock_units INTEGER NOT NULL CHECK (stock_units >= 0),
  expiry_date TEXT,                           -- in YYYY-MM-DD...?
  last_updated TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE,
  UNIQUE (medicine_id, batch_no)              -- prevent duplicate batch rows per medicine
);

-- DailyDosageTb
CREATE TABLE IF NOT EXISTS daily_dosage (
  medicine_id TEXT PRIMARY KEY,
  before_bf INTEGER DEFAULT 0,      -- taken before breakfast
  after_bf INTEGER DEFAULT 0,       -- taken after breakfast
  at_8pm INTEGER DEFAULT 0,         -- taken at 8 PM
  after_dinner INTEGER DEFAULT 0,   -- taken after dinner
  daily_dosage INTEGER DEFAULT 0,   -- sum of all
  FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE
);

-- for FEFO (first expired first out)
CREATE VIEW IF NOT EXISTS v_daily_units AS
SELECT
  dd.medicine_id,
  COALESCE(dd.before_bf,0)
  + COALESCE(dd.after_bf,0)
  + COALESCE(dd.at_8pm,0)
  + COALESCE(dd.after_dinner,0) AS units_per_day
FROM daily_dosage dd;

-- Stock movement log (audit trail- big words ;P)
CREATE TABLE IF NOT EXISTS stock_moves (
  id INTEGER PRIMARY KEY,
  ts TEXT NOT NULL DEFAULT (datetime('now')),
  medicine_id TEXT NOT NULL,
  batch_id INTEGER,                   -- nullable for adjustments/shortfalls
  qty_change REAL NOT NULL,           -- negative for deductions
  reason TEXT NOT NULL,               -- 'receipt','daily_dose', 'expired', 'adjustment', 'shortfall'
  note TEXT,
  FOREIGN KEY (medicine_id) REFERENCES medicines(id) ON DELETE CASCADE,
  FOREIGN KEY (batch_id)   REFERENCES batches(batch_id) ON DELETE SET NULL
);

-- Indexes for performance (FEFO ordering & lookups)
CREATE INDEX IF NOT EXISTS idx_batches_expiry ON batches (date(expiry_date), medicine_id);
CREATE INDEX IF NOT EXISTS idx_batches_med    ON batches (medicine_id);

-- Trigger: keep last_updated fresh whenever stock_units change
CREATE TRIGGER IF NOT EXISTS trg_batches_touch_last_updated
AFTER UPDATE OF stock_units ON batches
FOR EACH ROW
WHEN NEW.stock_units <> OLD.stock_units
BEGIN
  UPDATE batches
  SET last_updated = CURRENT_TIMESTAMP
  WHERE batch_id = NEW.batch_id;
END;
"""

def main():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA_SQL)
    print(f"Schema ensured at {DB_PATH.resolve()}")

if __name__ == "__main__":
    main()
