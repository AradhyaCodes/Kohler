"""Extract product rows from the Kohler price-book PDF (not included in the repo: place PriceBooK.pdf next to this file).
Install extras first: pip install -r requirements-data.txt"""
import os
import re

import pandas as pd
import pdfplumber

PDF_PATH = "PriceBooK.pdf"
PAGES = [6, 7, 8, 10, 34, 35, 36, 161, 162]   # toilets, basins, etc.

if not os.path.exists(PDF_PATH):
    raise SystemExit(f"{PDF_PATH} not found. Place the Kohler price book PDF here to regenerate the extract.")

rows = []
with pdfplumber.open(PDF_PATH) as pdf:
    for page_num in PAGES:
        table = pdf.pages[page_num - 1].extract_table()
        if not table:
            continue
        for row in table[1:]:
            if len(row) >= 4 and row[2] and row[3]:
                mrp = row[3].replace("\n", " ").replace("MRP", "").replace("`", "").strip()
                m = re.search(r"[\d,]+(\.\d+)?", mrp)
                if m:
                    rows.append({"name": (row[0] or "Kohler Fixture").replace("\n", " "),
                                 "description": (row[1] or "").replace("\n", " "),
                                 "sku": row[2].replace("\n", " ").strip(),
                                 "price_inr": float(m.group(0).replace(",", "")), "page": page_num})

df = pd.DataFrame(rows)
df.to_csv("pricebook_extract.csv", index=False)
print(f"Extracted {len(df)} products -> pricebook_extract.csv (dimensions/styles must be added manually for catalog.json)")
