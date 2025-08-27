# Med Inventory

A simple medicine inventory management system using **Python** and **SQLite**.  
It keeps track of medicines, batches, expiry dates and daily usage, following the **First Expiry, First Out (FEFO)** method.  
Data is ingested from Excel and viewed either through SQL or a small Streamlit dashboard.

---

## Features
- Set up the database schema with suppliers, medicines, batches, and dosage.
- Import data directly from `inventory.xlsx`.
- Automatically reduce stock based on daily dosage, using FEFO.
- Optional Streamlit dashboard to check current stock, low-stock alerts, expiries, and movements.

---

## Project Structure

```
med_inventory/
├── data/
│ └── inventory.xlsx 				# Excel file (source data)
├── db/
│ └── inventory.sqlite 			# SQLite database (not tracked in git)
├── docs/							# Screenshots
├── src/
│ ├── create_schema.py 			# Create tables and schema
│ ├── ingest_excel.py 				# Load data from Excel
│ ├── apply_daily_dosage.py 		# Daily FEFO stock deduction
│ └── app.py 						# Streamlit dashboard
├── tests/							# Tests
├── requirements.txt
└── README.md
```
---

## Setup

1. Clone the repository:
	```bash
   	git clone https://github.com/Tanmay-Jain0221/med_inventory.git
   	cd med_inventory

2. Create a virtual environment and activate it:
   	python -m venv .venv
   	
	### Windows
   	.venv\Scripts\activate

3. Install requirements:
	pip install -r requirements.txt

---

## Usage

1. Create the database schema.py
	python src\create_schema.py

2. Import data from Excel:
	python src\ingest_excel.py

3. Apply daily dosage (FEFO method)
	python src\apply_daily_dosage.py

   For a specific date:  #can be done from dashboard as well
	python src\apply_daily_dosage.py --date YYYY-MM-DD --force --verbose

4. Run the dashboard:
	streamlit run src\app.py

   Then open 'http://localhost:8501' in your browser.

---

## Screenshots

```docs/
│
│	### Terminal Proof
│ └── terminal_create_schema.png 		(Schema)  
│ └── terminal_ingest_excel.png  		(Ingest)
│ └── terminal_apply_daily_dosage.png  (FEFO)
│ └── terminal_streamlit_run.png		(Stock Moves)
│
│	### Database (DB Browser)
│ └── db_schema.png 			        (Schema) 
│ └── db_medicines_table.png		    (Medicines)
│ └── db_daily_dosage_table.png		    (Daily Dosage)
│ └── db_stock_moves_after_fefo.png	    (Stock Moves)
│
│	### Dashboard (Streamlit)
│ └── dashboard_medicines.png			(Medicines)
│ └── dashboard_batches.png			    (Batches)
│ └── dashboard_stock_moves.png		    (Stock Moves)
│ └── dashboard_actions_1.png			(Actions- Adjust Batch to exact quantity)
│ └── dashboard_actions_2.png			(Actions- Apply Daily FEFO for a date)
│
│	### Excel (data source)
│ └── excel_batches.png				(Batches)
│ └── excel_daily_dosage.png		(Daily Dosage)
│ └── excel_medicines.png			(Medicines)