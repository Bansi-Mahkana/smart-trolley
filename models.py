from datetime import datetime
import hashlib
import hmac
import logging
import secrets
import sqlite3

try:
    from werkzeug.security import generate_password_hash as _w_gen_hash
    from werkzeug.security import check_password_hash as _w_check_hash
except ImportError:
    _w_gen_hash = None
    _w_check_hash = None


def generate_password_hash(password):
    """
    Generates a secure password hash.
    Explicitly uses 'pbkdf2:sha256' instead of 'scrypt' to avoid
    'module hashlib has no attribute scrypt' errors on platforms without OpenSSL scrypt.
    """
    if _w_gen_hash is not None:
        try:
            return _w_gen_hash(password, method='pbkdf2:sha256')
        except (AttributeError, ValueError):
            pass

    # Built-in standard library fallback using pbkdf2_hmac
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt.encode('utf-8'), 100000)
    return "pbkdf2:sha256:100000$" + salt + "$" + key.hex()


def check_password_hash(stored_hash, plain_password):
    """
    Validates a plaintext password against any supported password hash format.
    """
    if not stored_hash or not plain_password:
        return False

    stored_str = str(stored_hash)

    # 1. Check with werkzeug if available and not failing on scrypt
    if _w_check_hash is not None:
        try:
            return _w_check_hash(stored_str, plain_password)
        except (AttributeError, ValueError):
            pass

    # 2. Check custom pbkdf2:sha256
    if stored_str.startswith("pbkdf2:sha256:"):
        parts = stored_str.split('$')
        if len(parts) == 3:
            try:
                algo_iter, salt, expected_hash = parts
                iterations = int(algo_iter.split(':')[2])
                key = hashlib.pbkdf2_hmac('sha256', plain_password.encode('utf-8'), salt.encode('utf-8'), iterations)
                return hmac.compare_digest(key.hex(), expected_hash)
            except Exception:
                return False

    # 3. Check legacy sha256$ or plain sha256
    if stored_str.startswith("sha256$"):
        expected = "sha256$" + hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
        return hmac.compare_digest(stored_str, expected)

    expected_raw = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    return hmac.compare_digest(stored_str, expected_raw)


from config import Config

logger = logging.getLogger(__name__)


def get_db():
    """
    Returns an active SQLite database connection with row factory enabled,
    foreign key constraints enforced, WAL mode, and a generous timeout.
    """
    conn = sqlite3.connect(Config.DATABASE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db():
    """
    Creates all necessary database tables and populates sample products
    if the products table is empty.
    """
    conn = get_db()
    cursor = conn.cursor()

    # Create customers table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create products table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            rfid_uid TEXT UNIQUE NOT NULL,
            price REAL NOT NULL,
            category TEXT,
            weight REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Create cart_items table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS cart_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        )
    """)

    # Create transactions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            total_amount REAL NOT NULL,
            payment_method TEXT DEFAULT 'Cash',
            status TEXT DEFAULT 'completed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers (id) ON DELETE CASCADE
        )
    """)

    # Create transaction_items table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transaction_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            product_id INTEGER,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (transaction_id) REFERENCES transactions (id) ON DELETE CASCADE,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE SET NULL
        )
    """)

    # Seed sample products if table is empty
    cursor.execute("SELECT COUNT(*) AS count FROM products")
    if cursor.fetchone()['count'] == 0:
        sample_products = [
            ('Milk 500ml', 'A1:B2:C3:D4', 28.00, 'Dairy', 530),
            ('Bread', 'E5:F6:G7:H8', 45.00, 'Bakery', 400),
            ('Rice 1kg', 'I9:J0:K1:L2', 65.00, 'Grains', 1000),
            ('Biscuits', 'M3:N4:O5:P6', 30.00, 'Snacks', 200),
            ('Soap', 'Q7:R8:S9:T0', 35.00, 'Personal Care', 125),
            ('Apple (1pc)', 'U1:V2:W3:X4', 15.00, 'Fruits', 180),
            ('Chips', 'Y5:Z6:A7:B8', 20.00, 'Snacks', 100),
            ('Shampoo', 'C9:D0:E1:F2', 120.00, 'Personal Care', 250),
        ]
        cursor.executemany("""
            INSERT INTO products (name, rfid_uid, price, category, weight)
            VALUES (?, ?, ?, ?, ?)
        """, sample_products)

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Customer Functions
# ---------------------------------------------------------------------------

def create_customer(name, email, password, phone=None):
    """
    Creates a new customer record with a hashed password.
    Returns the created customer ID.
    """
    clean_name = name.strip() if name else ''
    clean_email = email.strip().lower() if email else ''
    clean_phone = phone.strip() if phone else None

    hashed_password = generate_password_hash(password)
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO customers (name, email, password, phone)
            VALUES (?, ?, ?, ?)
        """, (clean_name, clean_email, hashed_password, clean_phone))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError as e:
        logger.warning(f"Integrity error in create_customer for email '{clean_email}': {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error creating customer '{clean_email}': {e}")
        raise
    finally:
        conn.close()


def get_customer_by_email(email):
    """
    Retrieves a customer by email address (case-insensitive).
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE LOWER(email) = LOWER(?)", (email.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_customer_by_id(customer_id):
    """
    Retrieves a customer by primary key ID.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM customers WHERE id = ?", (customer_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_customers():
    """
    Returns a list of all registered customers.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, phone, created_at FROM customers ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def verify_customer_password(stored_password_hash, plain_password):
    """
    Validates a plaintext password against a stored hash.
    """
    return check_password_hash(stored_password_hash, plain_password)


# ---------------------------------------------------------------------------
# Product Functions
# ---------------------------------------------------------------------------

def get_all_products():
    """
    Returns a list of all products in the catalog.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products ORDER BY category ASC, name ASC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_product_by_rfid(rfid_uid):
    """
    Retrieves a single product matching the given RFID UID (case-insensitive).
    """
    if not rfid_uid:
        return None
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE UPPER(rfid_uid) = UPPER(?)", (rfid_uid.strip(),))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_product_by_id(product_id):
    """
    Retrieves a single product by primary key ID.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM products WHERE id = ?", (product_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def add_product(name, rfid_uid, price, category, weight=0.0):
    """
    Adds a new product to the catalog.
    Returns the new product ID.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO products (name, rfid_uid, price, category, weight)
            VALUES (?, ?, ?, ?, ?)
        """, (name.strip(), rfid_uid.strip().upper(), float(price), category.strip(), float(weight)))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_product(product_id, name, rfid_uid, price, category, weight):
    """
    Updates an existing product's details.
    Returns True if an entry was updated, False otherwise.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE products
            SET name = ?, rfid_uid = ?, price = ?, category = ?, weight = ?
            WHERE id = ?
        """, (name.strip(), rfid_uid.strip().upper(), float(price), category.strip(), float(weight), product_id))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_product(product_id):
    """
    Deletes a product by ID.
    Returns True if deleted, False otherwise.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id = ?", (product_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Cart Functions
# ---------------------------------------------------------------------------

def add_to_cart(customer_id, product_id, quantity=1):
    """
    Adds a product to the customer's cart. If the product already exists
    in the cart, increments its quantity.
    Returns the affected cart item ID.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, quantity FROM cart_items
            WHERE customer_id = ? AND product_id = ?
        """, (customer_id, product_id))
        existing_item = cursor.fetchone()

        if existing_item:
            new_qty = existing_item['quantity'] + quantity
            cursor.execute("""
                UPDATE cart_items
                SET quantity = ?
                WHERE id = ?
            """, (new_qty, existing_item['id']))
            item_id = existing_item['id']
        else:
            cursor.execute("""
                INSERT INTO cart_items (customer_id, product_id, quantity)
                VALUES (?, ?, ?)
            """, (customer_id, product_id, quantity))
            item_id = cursor.lastrowid

        conn.commit()
        return item_id
    finally:
        conn.close()


def get_cart_items(customer_id):
    """
    Retrieves all items currently in the customer's cart, joined with
    product details, calculating subtotal and total weight for each line.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                ci.id,
                ci.customer_id,
                ci.product_id,
                ci.quantity,
                ci.added_at,
                p.name,
                p.rfid_uid,
                p.price,
                p.category,
                p.weight,
                ROUND(ci.quantity * p.price, 2) AS subtotal,
                ROUND(ci.quantity * p.weight, 2) AS item_total_weight
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            WHERE ci.customer_id = ?
            ORDER BY ci.added_at ASC
        """, (customer_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def remove_from_cart(customer_id, product_id, decrement=False):
    """
    Removes a product from the customer's cart.
    If decrement is True: decrements quantity by 1 (deleting row if quantity <= 1).
    If decrement is False: removes the line item entirely.
    Returns True if an item was modified or deleted, False otherwise.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        if decrement:
            cursor.execute("""
                SELECT id, quantity FROM cart_items
                WHERE customer_id = ? AND product_id = ?
            """, (customer_id, product_id))
            item = cursor.fetchone()
            if not item:
                return False

            if item['quantity'] > 1:
                cursor.execute("""
                    UPDATE cart_items
                    SET quantity = quantity - 1
                    WHERE id = ?
                """, (item['id'],))
            else:
                cursor.execute("DELETE FROM cart_items WHERE id = ?", (item['id'],))
            conn.commit()
            return True
        else:
            cursor.execute("""
                DELETE FROM cart_items
                WHERE customer_id = ? AND product_id = ?
            """, (customer_id, product_id))
            conn.commit()
            return cursor.rowcount > 0
    finally:
        conn.close()


def clear_cart(customer_id):
    """
    Clears all items from the customer's cart.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cart_items WHERE customer_id = ?", (customer_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def get_cart_summary(customer_id):
    """
    Calculates total items, total price, and total weight for the given customer's cart.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COALESCE(SUM(ci.quantity), 0) AS total_items,
                COALESCE(SUM(ci.quantity * p.price), 0.0) AS total_price,
                COALESCE(SUM(ci.quantity * p.weight), 0.0) AS total_weight
            FROM cart_items ci
            JOIN products p ON ci.product_id = p.id
            WHERE ci.customer_id = ?
        """, (customer_id,))
        row = cursor.fetchone()
        return {
            'total_items': int(row['total_items']),
            'total_price': round(float(row['total_price']), 2),
            'total_weight': round(float(row['total_weight']), 2)
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Transaction Functions
# ---------------------------------------------------------------------------

def create_transaction(customer_id, total_amount, payment_method='Cash', items=None, created_at=None):
    """
    Creates a transaction record along with its associated line items.
    'items' is expected to be a list of dictionaries with product/cart information.
    Records the exact local timestamp when the transaction happens.
    Returns the created transaction ID.
    """
    if items is None:
        items = []

    if not created_at:
        created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transactions (customer_id, total_amount, payment_method, status, created_at)
            VALUES (?, ?, ?, 'completed', ?)
        """, (customer_id, float(total_amount), payment_method, created_at))
        transaction_id = cursor.lastrowid

        for item in items:
            product_id = item.get('product_id') or item.get('id')
            product_name = item.get('product_name') or item.get('name', 'Unknown Product')
            quantity = int(item.get('quantity') or item.get('qty', 1))
            unit_price = float(item.get('unit_price') or item.get('price', 0.0))
            subtotal = float(item.get('subtotal', round(quantity * unit_price, 2)))

            cursor.execute("""
                INSERT INTO transaction_items (
                    transaction_id, product_id, product_name, quantity, unit_price, subtotal
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (transaction_id, product_id, product_name, quantity, unit_price, subtotal))

        conn.commit()
        return transaction_id
    finally:
        conn.close()


def get_transaction_by_id(transaction_id):
    """
    Retrieves a single transaction by primary key ID, joined with customer details.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                t.*,
                c.name AS customer_name,
                c.email AS customer_email,
                c.phone AS customer_phone
            FROM transactions t
            LEFT JOIN customers c ON t.customer_id = c.id
            WHERE t.id = ?
        """, (transaction_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_customer_transactions(customer_id):
    """
    Retrieves all transactions made by a specific customer, ordered newest first.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM transactions
            WHERE customer_id = ?
            ORDER BY created_at DESC
        """, (customer_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_all_transactions():
    """
    Retrieves all transactions across the system with customer details, ordered newest first.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                t.*,
                c.name AS customer_name,
                c.email AS customer_email,
                c.phone AS customer_phone
            FROM transactions t
            LEFT JOIN customers c ON t.customer_id = c.id
            ORDER BY t.created_at DESC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_transaction_items(transaction_id):
    """
    Retrieves all item rows associated with a particular transaction.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM transaction_items
            WHERE transaction_id = ?
            ORDER BY id ASC
        """, (transaction_id,))
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_transaction_stats():
    """
    Aggregates high-level metrics: total transactions, total revenue,
    total registered customers, and total products in catalog.
    """
    conn = get_db()
    try:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) AS total_count, COALESCE(SUM(total_amount), 0.0) AS total_rev FROM transactions")
        tx_row = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) AS total_count FROM customers")
        cust_row = cursor.fetchone()

        cursor.execute("SELECT COUNT(*) AS total_count FROM products")
        prod_row = cursor.fetchone()

        return {
            'total_transactions': int(tx_row['total_count']),
            'total_revenue': round(float(tx_row['total_rev']), 2),
            'total_customers': int(cust_row['total_count']),
            'total_products': int(prod_row['total_count'])
        }
    finally:
        conn.close()
