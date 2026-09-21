"""Single-user expense tracker. Money is persisted as integer cents."""
import os
import re
import sqlite3
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

STATIC = Path(__file__).parent / 'static'


class ExpenseInput(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal('999999999.99'), decimal_places=2, allow_inf_nan=False)
    category: str = Field(min_length=1, max_length=80)
    note: str = Field(default='', max_length=500)
    date: date

    @field_validator('category')
    @classmethod
    def normalize_category(cls, value):
        value = value.strip().lower()
        if not value:
            raise ValueError('Category must not be blank')
        return value


def money(cents):
    return f'{Decimal(cents) / 100:.2f}'


def month_bounds(month):
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise HTTPException(422, 'month must use YYYY-MM')
    try:
        start = date.fromisoformat(month + '-01')
        previous = date(start.year - 1, 12, 1) if start.month == 1 else date(start.year, start.month - 1, 1)
        end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
    except ValueError:
        raise HTTPException(422, 'Invalid or unsupported month')
    return previous.isoformat(), start.isoformat(), end.isoformat()


def create_app(db_path=None):
    database = Path(db_path or os.getenv('DATABASE_PATH', 'data/expenses.db'))

    @contextmanager
    def connect():
        conn = sqlite3.connect(database, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @asynccontextmanager
    async def lifespan(app):
        database.parent.mkdir(parents=True, exist_ok=True)
        with connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY,
                amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                category TEXT NOT NULL CHECK(length(trim(category)) BETWEEN 1 AND 80),
                note TEXT NOT NULL DEFAULT '',
                date TEXT NOT NULL
            )''')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_expenses_category_date ON expenses(category, date)')
        yield

    app = FastAPI(title='Mini Spend Tracker', lifespan=lifespan)
    app.mount('/static', StaticFiles(directory=STATIC), name='static')

    def serialize(row):
        return dict(id=row['id'], amount=money(row['amount_cents']), category=row['category'], note=row['note'], date=row['date'])

    @app.get('/', include_in_schema=False)
    def home():
        return FileResponse(STATIC / 'index.html')

    @app.post('/expenses', status_code=201)
    def add_expense(expense: ExpenseInput):
        with connect() as conn:
            cursor = conn.execute('INSERT INTO expenses(amount_cents, category, note, date) VALUES (?, ?, ?, ?)',
                                  (int(expense.amount * 100), expense.category, expense.note, expense.date.isoformat()))
            row = conn.execute('SELECT * FROM expenses WHERE id = ?', (cursor.lastrowid,)).fetchone()
        return serialize(row)

    @app.get('/expenses')
    def list_expenses(category: str | None = None, start_date: date | None = None,
                      end_date: date | None = None, limit: int = Query(100, ge=1, le=500),
                      offset: int = Query(0, ge=0)):
        if start_date and end_date and start_date > end_date:
            raise HTTPException(422, 'start_date must be on or before end_date')
        clauses, params = [], []
        for condition, value in [('category = ?', category.strip().lower() if category is not None else None),
                                 ('date >= ?', start_date.isoformat() if start_date else None),
                                 ('date <= ?', end_date.isoformat() if end_date else None)]:
            if value is not None:
                clauses.append(condition)
                params.append(value)
        where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
        with connect() as conn:
            rows = conn.execute('SELECT * FROM expenses' + where + ' ORDER BY date DESC, id DESC LIMIT ? OFFSET ?',
                                params + [limit, offset]).fetchall()
        return [serialize(row) for row in rows]

    @app.get('/summary')
    def summary(month: str | None = None):
        month = month or date.today().strftime('%Y-%m')
        previous, start, end = month_bounds(month)
        with connect() as conn:
            rows = conn.execute('''SELECT category,
                SUM(CASE WHEN date >= ? THEN amount_cents ELSE 0 END) AS current,
                SUM(CASE WHEN date < ? THEN amount_cents ELSE 0 END) AS previous
                FROM expenses WHERE date >= ? AND date < ? GROUP BY category ORDER BY category''',
                                (start, start, previous, end)).fetchall()
        current = sum(row['current'] for row in rows)
        prior = sum(row['previous'] for row in rows)

        def change(now, before):
            return round((now - before) * 100 / before, 2) if before else None

        return {'month': month, 'total_spend': money(current),
                'spend_by_category': {r['category']: money(r['current']) for r in rows if r['current']},
                'previous_month_total': money(prior), 'month_over_month_change_percent': change(current, prior),
                'insights': [{'category': r['category'], 'increase_percent': change(r['current'], r['previous'])}
                             for r in rows if r['previous'] > 0 and r['current'] * 100 > r['previous'] * 120]}

    return app


app = create_app()
