import os
from pathlib import Path
from typing import Optional, Dict
from flask import Flask, render_template, request
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import webbrowser

# ─── App & Database Configuration ───────────────────────────────────────
app = Flask(__name__)
BASE_DIR     = Path(__file__).parent
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    f"sqlite:///{BASE_DIR / 'inventory.db'}"
)
app.config['SQLALCHEMY_DATABASE_URI']        = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ─── Models ─────────────────────────────────────────────────────────────
class InventoryItem(db.Model):
    size  = db.Column(db.String, primary_key=True)
    count = db.Column(db.Integer, nullable=False)

# ─── Ensure DB Tables Exist & Seed Defaults (Import Time) ─────────────
with app.app_context():
    db.create_all()
    if InventoryItem.query.count() == 0:
        defaults = [('20oz', 40), ('16oz', 60), ('12oz', 5)]
        for size, bundles in defaults:
            db.session.add(InventoryItem(size=size, count=bundles * 50))
        db.session.commit()

# ─── Sales Summary Utilities ─────────────────────────────────────────────
VALID_SIZES = ['20oz', '16oz', '12oz', 'regular']
SALES_FILE  = BASE_DIR / 'item-sales-summary-2025-04-17-2025-04-18.csv'

def normalize_size(size: str) -> Optional[str]:
    s = str(size).lower().replace('.', '').replace(' ', '')
    if '20oz' in s:
        return '20oz'
    if '16oz' in s:
        return '16oz'
    if '12oz' in s:
        return '12oz'
    if 'regular' in s:
        return 'regular'
    return None

def get_sales_summary() -> Dict[str, int]:
    # Guard if CSV missing
    if not SALES_FILE.exists():
        return {}
    df = pd.read_csv(
        SALES_FILE,
        skiprows=1,
        header=None,
        names=['Item Variation', 'Items Sold']
    )
    df['Item Variation'] = df['Item Variation'].fillna('').astype(str)
    pattern = '|'.join(VALID_SIZES)
    df = df[df['Item Variation'].str.contains(pattern, na=False)]
    df['Item Variation'] = (
        df['Item Variation']
          .str.lower()
          .str.replace(r'\s+', '', regex=True)
          .str.replace(r'\.', '', regex=True)
          .map(normalize_size)
    )
    return df.groupby('Item Variation')['Items Sold'].sum().to_dict()

def apply_sales_to_db(sales: Dict[str, int]) -> None:
    for size, sold in sales.items():
        item = InventoryItem.query.get(size)
        if item:
            item.count = max(item.count - int(sold), 0)
    db.session.commit()

# ─── Flask Routes ───────────────────────────────────────────────────────
@app.route('/', methods=['GET', 'POST'])
def index():
    message = None
    # Handle manual adjustments
    if request.method == 'POST' and 'action' in request.form:
        size   = request.form.get('size')
        qty    = request.form.get('quantity', type=int, default=0)
        action = request.form.get('action')
        item   = InventoryItem.query.get(size)
        if item is not None:
            delta = qty if action == 'add' else -qty
            item.count = max(item.count + delta, 0)
            db.session.commit()
            message = f"{'Added' if action=='add' else 'Subtracted'} {qty} of {size}."
    # Apply latest sales
    sales_summary = get_sales_summary()
    apply_sales_to_db(sales_summary)
    # Load current inventory
    inventory = {it.size: it.count for it in InventoryItem.query.all()}
    return render_template(
        'index.html',
        inventory=inventory,
        sales=sales_summary,
        message=message
    )

# ─── Launch the App ─────────────────────────────────────────────────────
if __name__ == '__main__':
    url    = 'http://127.0.0.1:5000'
    chrome = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
    if os.path.exists(chrome):
        webbrowser.get(chrome).open(url)
    app.run(host='0.0.0.0', port=5000, debug=True)
