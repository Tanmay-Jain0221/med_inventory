import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from datetime import date, datetime

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB = PROJECT_ROOT / "db" / "inventory.sqlite"
APPLY_SCRIPT = PROJECT_ROOT / "src" / "apply_daily_dosage.py"

APP_PASSWORD = os.getenv("STREAMLIT_APP_PASSWORD", "").strip()

def check_auth():
    if not APP_PASSWORD:
        return True  # no password set → open
    with st.sidebar:
        st.markdown("Login")
        pw = st.text_input("Password", type="password")
        if st.button("Unlock"):
            if pw == APP_PASSWORD:
                st.session_state["_auth_ok"] = True
            else:
                st.error("Wrong password")
    return st.session_state.get("_auth_ok", False)

@st.cache_data(ttl=30)
def q(sql, params=()):
    with sqlite3.connect(DB) as conn:
        conn.row_factory = sqlite3.Row
        return pd.read_sql_query(sql, conn, params=params)

def exec_sql(sql, params=()):
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        cur.execute(sql, params)
        conn.commit()
    st.cache_data.clear()  # invalidate cached reads

def exec_script(sql_script):
    with sqlite3.connect(DB) as conn:
        cur = conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON;")
        cur.executescript(sql_script)
        conn.commit()
    st.cache_data.clear()

# page layout & structure
st.set_page_config(page_title="Med Inventory", layout="wide")

st.title("Medicine Inventory Dashboard")

if not check_auth():
    st.stop()

st.caption(f"DB: {DB}")

tab_overview, tab_alerts, tab_meds, tab_batches, tab_moves, tab_actions = st.tabs(
    ["Overview", "Alerts", "Medicines", "Batches (FEFO)", "Stock Moves", "Actions"]
)

# Overview
with tab_overview:
    c1, c2, c3, c4 = st.columns(4)
    total_meds = q("SELECT COUNT(*) AS n FROM medicines")["n"][0]
    total_batches = q("SELECT COUNT(*) AS n FROM batches")["n"][0]
    total_stock = q("SELECT COALESCE(SUM(stock_units),0) AS n FROM batches")["n"][0]
    dosage_rows = q("""
      SELECT COUNT(*) AS n
      FROM v_daily_units
      WHERE units_per_day > 0
    """)["n"][0]
    c1.metric("Medicines", total_meds)
    c2.metric("Batches", total_batches)
    c3.metric("Units in stock", int(total_stock))
    c4.metric("Daily plan meds", dosage_rows)

    st.subheader("Below reorder level (all meds)")
    low = q("""
      SELECT m.id, m.medicine_name,
             COALESCE(SUM(b.stock_units),0) AS total_stock,
             m.reorder_level
      FROM medicines m
      LEFT JOIN batches b ON b.medicine_id = m.id
      GROUP BY m.id, m.medicine_name, m.reorder_level
      HAVING total_stock <= m.reorder_level
      ORDER BY total_stock ASC, m.medicine_name
    """)
    st.dataframe(low, use_container_width=True)

# Alerts Page
with tab_alerts:
    st.subheader("Low stock (only daily meds; alert at < 1.5× reorder)")
    alerts = q("""
      SELECT
        m.id, m.medicine_name,
        COALESCE(SUM(b.stock_units), 0) AS total_stock,
        m.reorder_level,
        v.units_per_day,
        ROUND(1.5 * m.reorder_level, 2) AS alert_level,
        ROUND(COALESCE(SUM(b.stock_units),0) / NULLIF(v.units_per_day,0), 1) AS days_cover
      FROM medicines m
      JOIN v_daily_units v ON v.medicine_id = m.id
      LEFT JOIN batches b   ON b.medicine_id = m.id
      GROUP BY m.id, m.medicine_name, m.reorder_level, v.units_per_day
      HAVING v.units_per_day > 0
         AND m.reorder_level > 0
         AND total_stock < (1.5 * m.reorder_level)
      ORDER BY total_stock ASC, m.medicine_name;
    """)
    st.dataframe(alerts, use_container_width=True)

# All Medicines List
with tab_meds:
    st.subheader("Medicines")
    meds = q("""
      SELECT id, medicine_name, salt, uses, reorder_level
      FROM medicines
      ORDER BY medicine_name
    """)
    st.dataframe(meds, use_container_width=True)

# Batches (FEFO)
with tab_batches:
    st.subheader("Batches in FEFO order")
    colf1, colf2 = st.columns(2)
    med_filter = colf1.text_input("Filter by medicine_id (optional)")
    only_in_stock = colf2.checkbox("Only show batches with stock > 0", value=True)

    where = []
    params = []
    if med_filter.strip():
        where.append("medicine_id = ?")
        params.append(med_filter.strip())
    if only_in_stock:
        where.append("stock_units > 0")
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    fefo = q(f"""
      SELECT medicine_id, batch_no, expiry_date, stock_units
      FROM batches
      {where_sql}
      ORDER BY (expiry_date IS NULL) ASC, date(expiry_date) ASC, batch_id ASC
    """, params)
    st.dataframe(fefo, use_container_width=True)

# Stock Moves
with tab_moves:
    st.subheader("Recent Stock Movements")
    reason = st.selectbox("Reason", ["(all)","receipt","daily_dose","expired","adjustment","shortfall"])
    base = "SELECT ts, medicine_id, batch_id, qty_change, reason, note FROM stock_moves"
    if reason == "(all)":
        sql = f"{base} ORDER BY ts DESC, id DESC LIMIT 500"
        moves = q(sql)
    else:
        sql = f"{base} WHERE reason = ? ORDER BY ts DESC, id DESC LIMIT 500"
        moves = q(sql, (reason,))
    st.dataframe(moves, use_container_width=True)

# -Actions-
with tab_actions:
    st.subheader("Receive stock")
    with st.form("receive_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([1,1,1,1])
        med = c1.text_input("medicine_id")
        batch = c2.text_input("batch_no")
        qty = c3.number_input("quantity (+)", min_value=0, value=0, step=1)
        exp = c4.text_input("expiry_date (YYYY-MM-DD)", value="")
        submitted = st.form_submit_button("Receive")
        if submitted:
            try:
                # UPSERT: increase stock if batch exists
                exec_sql("""
                  INSERT INTO batches (medicine_id, batch_no, stock_units, expiry_date)
                  VALUES (?, ?, ?, NULLIF(?, ''))
                  ON CONFLICT(medicine_id, batch_no)
                  DO UPDATE SET stock_units = stock_units + excluded.stock_units,
                                expiry_date = COALESCE(excluded.expiry_date, expiry_date)
                """, (med.strip(), batch.strip(), int(qty), exp.strip()))
                # Log it
                exec_script(f"""
                  INSERT INTO stock_moves (medicine_id, batch_id, qty_change, reason, note)
                  SELECT '{med.strip()}', batch_id, {int(qty)}, 'receipt', 'Streamlit receive'
                  FROM batches WHERE medicine_id='{med.strip()}' AND batch_no='{batch.strip()}';
                """)
                st.success(f"Received {int(qty)} of {med} / {batch}")
            except Exception as e:
                st.error(f"Failed: {e}")

    st.divider()
    st.subheader("Adjust batch to exact quantity")
    # Build selectors
    batch_df = q("""
      SELECT batch_id, medicine_id || ' | ' || batch_no AS label, stock_units
      FROM batches
      ORDER BY medicine_id, batch_no
    """)
    if not batch_df.empty:
        id_to_label = dict(zip(batch_df["batch_id"], batch_df["label"]))
        id_to_stock = dict(zip(batch_df["batch_id"], batch_df["stock_units"]))
        sel = st.selectbox("Pick batch", options=list(id_to_label.keys()),
                           format_func=lambda x: f"{id_to_label[x]} (now {id_to_stock[x]})")
        new_qty = st.number_input("Set quantity to", min_value=0, value=int(id_to_stock[sel]), step=1)
        note = st.text_input("Note", value="Streamlit adjustment")
        if st.button("Apply adjustment"):
            try:
                # compute diff for audit
                old_qty = int(id_to_stock[sel])
                diff = int(new_qty) - old_qty
                exec_sql("UPDATE batches SET stock_units=? WHERE batch_id=?", (int(new_qty), int(sel)))
                exec_sql("""
                  INSERT INTO stock_moves (medicine_id, batch_id, qty_change, reason, note)
                  SELECT medicine_id, batch_id, ?, 'adjustment', ?
                  FROM batches WHERE batch_id=?
                """, (diff, note, int(sel)))
                st.success(f"Batch set to {int(new_qty)} (Δ {diff})")
            except Exception as e:
                st.error(f"Failed: {e}")
    else:
        st.info("No batches found.")

    st.divider()
    st.subheader("Apply daily FEFO for a date")
    run_date = st.date_input("Date to apply", value=date.today(), format="YYYY-MM-DD")
    force = st.checkbox("Force even if already applied", value=False)
    if st.button("Run FEFO now"):
        try:
            # Calls existing FEFO script
            args = [sys.executable, str(APPLY_SCRIPT), "--date", run_date.strftime("%Y-%m-%d")]
            if force:
                args.append("--force")
            res = subprocess.run(args, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
            if res.returncode == 0:
                st.success("Finished FEFO.")
                st.text(res.stdout[-2000:])
                st.cache_data.clear()
            else:
                st.error("FEFO script failed.")
                st.code(res.stderr or res.stdout)
        except Exception as e:
            st.error(f"Failed to run FEFO: {e}")
