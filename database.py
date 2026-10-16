
import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path('bot.db')


def connect():
    c = sqlite3.connect(DB_PATH, timeout=15)
    c.execute('PRAGMA foreign_keys=ON')
    return c


def _ensure_col(c, table, name, decl):
    cols = [r[1] for r in c.execute(f'PRAGMA table_info({table})')]
    if name not in cols:
        c.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')


def init_db():
    c = connect()
    q = c.cursor()

    q.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT DEFAULT "",
            first_name TEXT DEFAULT "",
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            last_active TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    q.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            username TEXT DEFAULT "",
            receiver TEXT NOT NULL,
            stars INTEGER NOT NULL DEFAULT 0,
            price REAL NOT NULL DEFAULT 0,
            status TEXT DEFAULT "waiting",
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            product_type TEXT DEFAULT "stars",
            premium_months INTEGER DEFAULT 0,
            receipt_file_id TEXT DEFAULT "",
            gram_amount REAL DEFAULT 0,
            gram_wallet TEXT DEFAULT ""
        )
    """)

    # Исправлено: нельзя добавлять столбец с DEFAULT CURRENT_TIMESTAMP
    # в существующую таблицу через ALTER TABLE.
    _ensure_col(c, 'users', 'last_active', 'TEXT')
    _ensure_col(c, 'users', 'created_at', 'TEXT')

    # Заполняем даты для существующих пользователей.
    q.execute("""
        UPDATE users
        SET created_at = CURRENT_TIMESTAMP
        WHERE created_at IS NULL OR created_at = ''
    """)

    q.execute("""
        UPDATE users
        SET last_active = COALESCE(created_at, CURRENT_TIMESTAMP)
        WHERE last_active IS NULL OR last_active = ''
    """)

    order_columns = [
        ('product_type', 'TEXT DEFAULT "stars"'),
        ('premium_months', 'INTEGER DEFAULT 0'),
        ('receipt_file_id', 'TEXT DEFAULT ""'),
        ('gram_amount', 'REAL DEFAULT 0'),
        ('gram_wallet', 'TEXT DEFAULT ""')
    ]

    for name, decl in order_columns:
        _ensure_col(c, 'orders', name, decl)

    q.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    q.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    """)

    q.execute("""
        CREATE TABLE IF NOT EXISTS button_styles (
            button_key TEXT PRIMARY KEY,
            style TEXT NOT NULL DEFAULT "default"
        )
    """)

    q.execute("""
        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            discount INTEGER NOT NULL,
            usage_limit INTEGER DEFAULT 0,
            uses INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    q.execute("""
        CREATE TABLE IF NOT EXISTS promo_uses (
            code TEXT,
            user_id INTEGER,
            used_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY(code, user_id)
        )
    """)

    q.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            user_id INTEGER PRIMARY KEY,
            rating INTEGER NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    q.execute("""
        CREATE TABLE IF NOT EXISTS required_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            value TEXT NOT NULL,
            title TEXT NOT NULL
        )
    """)

    q.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            stars INTEGER PRIMARY KEY,
            price INTEGER NOT NULL
        )
    """)

    defaults = {
        'stars_rate': '1.32',
        'premium_3': '399',
        'premium_6': '749',
        'premium_12': '1399',
        'gram_markup': '10',
        'gram_balance': '0',
        'gram_enabled': '1',
        'gram_payment_wallet': '',
        'payment_card': '',
        'payment_bank': '',
        'payment_name': ''
    }

    for k, v in defaults.items():
        q.execute(
            'INSERT OR IGNORE INTO settings(key, value) VALUES(?, ?)',
            (k, v)
        )

    for stars, price in [
        (50, 66),
        (100, 132),
        (250, 330),
        (500, 660),
        (1000, 1320)
    ]:
        q.execute(
            'INSERT OR IGNORE INTO prices(stars, price) VALUES(?, ?)',
            (stars, price)
        )

    # Перенос старых реквизитов в новые настройки.
    q.execute("""
        CREATE TABLE IF NOT EXISTS payment_details (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    for old_key, new_key in [
        ('card', 'payment_card'),
        ('bank', 'payment_bank'),
        ('recipient', 'payment_name')
    ]:
        old = q.execute(
            'SELECT value FROM payment_details WHERE key = ?',
            (old_key,)
        ).fetchone()

        current = q.execute(
            'SELECT value FROM settings WHERE key = ?',
            (new_key,)
        ).fetchone()

        if old and old[0] and (not current or not current[0]):
            q.execute(
                'UPDATE settings SET value = ? WHERE key = ?',
                (old[0], new_key)
            )

    c.commit()
    c.close()


def _get(k, default=''):
    c = connect()
    r = c.execute(
        'SELECT value FROM settings WHERE key = ?',
        (k,)
    ).fetchone()
    c.close()
    return r[0] if r else default


def _set(k, v):
    c = connect()
    c.execute("""
        INSERT INTO settings(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """, (k, str(v)))
    c.commit()
    c.close()


def add_user(user_id, username, first_name):
    c = connect()
    c.execute("""
        INSERT INTO users(user_id, username, first_name, last_active)
        VALUES(?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            username = excluded.username,
            first_name = excluded.first_name,
            last_active = CURRENT_TIMESTAMP
    """, (user_id, username or '', first_name or ''))
    c.commit()
    c.close()


def touch_user(user_id):
    c = connect()
    c.execute(
        'UPDATE users SET last_active = CURRENT_TIMESTAMP WHERE user_id = ?',
        (user_id,)
    )
    c.commit()
    c.close()


def count_users():
    c = connect()
    n = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    c.close()
    return n


def get_all_users():
    c = connect()
    r = c.execute(
        'SELECT user_id, username, first_name FROM users'
    ).fetchall()
    c.close()
    return r


def get_stars_rate():
    return float(_get('stars_rate', '1.32'))


def set_stars_rate(v):
    _set('stars_rate', float(v))


def get_premium_price(months):
    return float(_get(f'premium_{int(months)}', '399'))


def set_premium_price(months, price):
    _set(f'premium_{int(months)}', float(price))


def get_gram_markup():
    return float(_get('gram_markup', '10'))


def set_gram_markup(v):
    _set('gram_markup', float(v))


def get_gram_balance():
    return float(_get('gram_balance', '0'))


def set_gram_balance(v):
    _set('gram_balance', float(v))


def get_gram_enabled():
    return _get('gram_enabled', '1') in ('1', 'true', 'True')


def set_gram_enabled(v):
    _set('gram_enabled', '1' if v else '0')


def get_gram_payment_wallet():
    return _get('gram_payment_wallet', '')


def set_gram_payment_wallet(v):
    _set('gram_payment_wallet', v)


def get_payment_card():
    return _get('payment_card', '')


def set_payment_card(v):
    _set('payment_card', v)


def get_payment_bank():
    return _get('payment_bank', '')


def set_payment_bank(v):
    _set('payment_bank', v)


def get_payment_name():
    return _get('payment_name', '')


def set_payment_name(v):
    _set('payment_name', v)


def get_button_style(k):
    return _get('button_style_' + k, 'default')


def set_button_style(k, v):
    _set('button_style_' + k, v)


def add_admin(uid):
    c = connect()
    c.execute(
        'INSERT OR IGNORE INTO admins(user_id) VALUES(?)',
        (uid,)
    )
    c.commit()
    c.close()


def remove_admin(uid):
    c = connect()
    c.execute('DELETE FROM admins WHERE user_id = ?', (uid,))
    c.commit()
    c.close()


def get_admins():
    c = connect()
    r = [
        x[0]
        for x in c.execute('SELECT user_id FROM admins').fetchall()
    ]
    c.close()
    return r


def is_admin(uid):
    return uid in get_admins()


def create_order(
    user_id, username, receiver, stars, price,
    product_type='stars', premium_months=0,
    gram_amount=0, gram_wallet=''
):
    c = connect()
    q = c.cursor()

    if product_type == 'gram':
        balance = float(_get('gram_balance', '0'))
        if gram_amount > balance:
            c.close()
            return None
        _set('gram_balance', balance - float(gram_amount))

    q.execute("""
        INSERT INTO orders(
            user_id, username, receiver, stars, price, status,
            product_type, premium_months, gram_amount, gram_wallet
        )
        VALUES(?, ?, ?, ?, ?, "waiting", ?, ?, ?, ?)
    """, (
        user_id,
        username or '',
        receiver,
        int(stars or 0),
        float(price),
        product_type or 'stars',
        int(premium_months or 0),
        float(gram_amount or 0),
        gram_wallet or ''
    ))

    oid = q.lastrowid
    c.commit()
    c.close()
    return oid


def get_order(order_id):
    c = connect()
    r = c.execute("""
        SELECT user_id, username, receiver, stars, price, status,
               created_at, product_type, premium_months,
               receipt_file_id, gram_amount, gram_wallet
        FROM orders WHERE id = ?
    """, (order_id,)).fetchone()
    c.close()
    return r


def get_all_orders():
    c = connect()
    r = c.execute("""
        SELECT id, user_id, username, receiver, stars, price, status,
               created_at, product_type, premium_months,
               receipt_file_id, gram_amount, gram_wallet
        FROM orders ORDER BY id DESC
    """).fetchall()
    c.close()
    return r


def set_receipt(order_id, file_id):
    c = connect()
    c.execute(
        'UPDATE orders SET receipt_file_id = ? WHERE id = ?',
        (file_id, order_id)
    )
    c.commit()
    c.close()


def complete_order(order_id):
    c = connect()
    c.execute("""
        UPDATE orders SET status = "completed"
        WHERE id = ? AND status = "waiting"
    """, (order_id,))
    c.commit()
    c.close()


def cancel_order(order_id):
    c = connect()
    row = c.execute("""
        SELECT product_type, gram_amount, status
        FROM orders WHERE id = ?
    """, (order_id,)).fetchone()

    if row and row[2] == 'waiting' and row[0] == 'gram':
        _set(
            'gram_balance',
            float(_get('gram_balance', '0')) + float(row[1] or 0)
        )

    c.execute("""
        UPDATE orders SET status = "cancelled"
        WHERE id = ? AND status = "waiting"
    """, (order_id,))

    c.commit()
    c.close()


def count_orders():
    c = connect()
    n = c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
    c.close()
    return n


def count_completed_orders():
    c = connect()
    n = c.execute(
        'SELECT COUNT(*) FROM orders WHERE status = "completed"'
    ).fetchone()[0]
    c.close()
    return n


def count_active_today():
    c = connect()
    n = c.execute("""
        SELECT COUNT(*) FROM users
        WHERE date(last_active) = date('now')
    """).fetchone()[0]
    c.close()
    return n


def count_active_week():
    c = connect()
    n = c.execute("""
        SELECT COUNT(*) FROM users
        WHERE datetime(last_active) >= datetime('now', '-7 days')
    """).fetchone()[0]
    c.close()
    return n


# Промокоды.
# Формат результата сохранён для совместимости с админ-панелью.
def create_promo(code, discount, usage_limit=0):
    c = connect()
    c.execute("""
        INSERT INTO promo_codes(
            code, discount, usage_limit, uses, enabled
        )
        VALUES(?, ?, ?, 0, 1)
        ON CONFLICT(code) DO UPDATE SET
            discount = excluded.discount,
            usage_limit = excluded.usage_limit,
            enabled = 1
    """, (code.upper(), int(discount), int(usage_limit)))
    c.commit()
    c.close()


def get_promo(code):
    c = connect()
    r = c.execute("""
        SELECT code, discount, usage_limit, uses, uses
        FROM promo_codes
        WHERE code = ? AND enabled = 1
    """, (code.upper(),)).fetchone()
    c.close()
    return r


def use_promo(code, user_id):
    c = connect()
    cur = c.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO promo_uses(code, user_id)
        VALUES(?, ?)
    """, (code.upper(), user_id))

    if cur.rowcount:
        cur.execute(
            'UPDATE promo_codes SET uses = uses + 1 WHERE code = ?',
            (code.upper(),)
        )

    c.commit()
    c.close()


def list_promos():
    c = connect()
    r = c.execute("""
        SELECT code, discount, usage_limit, uses, uses
        FROM promo_codes
        WHERE enabled = 1
        ORDER BY code
    """).fetchall()
    c.close()
    return r


def delete_promo(code):
    c = connect()
    c.execute('DELETE FROM promo_codes WHERE code = ?', (code.upper(),))
    c.execute('DELETE FROM promo_uses WHERE code = ?', (code.upper(),))
    c.commit()
    c.close()


def add_rating(user_id, rating):
    c = connect()
    c.execute("""
        INSERT INTO ratings(user_id, rating)
        VALUES(?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            rating = excluded.rating,
            updated_at = CURRENT_TIMESTAMP
    """, (user_id, int(rating)))
    c.commit()
    c.close()


def get_user_rating(user_id):
    c = connect()
    r = c.execute(
        'SELECT rating FROM ratings WHERE user_id = ?',
        (user_id,)
    ).fetchone()
    c.close()
    return r[0] if r else None


def get_rating_stats():
    c = connect()
    r = c.execute(
        'SELECT COALESCE(AVG(rating), 0), COUNT(*) FROM ratings'
    ).fetchone()
    c.close()
    return float(r[0]), int(r[1])


def add_required_item(kind, value, title):
    c = connect()
    c.execute("""
        INSERT INTO required_items(kind, value, title)
        VALUES(?, ?, ?)
    """, (kind, value, title))
    c.commit()
    c.close()


def get_required_items():
    c = connect()
    r = c.execute("""
        SELECT kind, value, title
        FROM required_items ORDER BY id
    """).fetchall()
    c.close()
    return r


def delete_required_item(index):
    c = connect()
    row = c.execute("""
        SELECT id FROM required_items
        ORDER BY id LIMIT 1 OFFSET ?
    """, (index,)).fetchone()

    if row:
        c.execute('DELETE FROM required_items WHERE id = ?', (row[0],))

    c.commit()
    c.close()


# Совместимость со старым кодом.
def init():
    init_db()


init_db()
