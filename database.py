import sqlite3

DB_NAME = "paypredict.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name       TEXT NOT NULL,
            email           TEXT NOT NULL UNIQUE,
            password_hash   TEXT NOT NULL,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            locked_until    TEXT,
            created_at      TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id   INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            customer_name TEXT NOT NULL,
            email         TEXT NOT NULL,
            phone         TEXT NOT NULL,
            UNIQUE (user_id, email),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            invoice_number TEXT NOT NULL,
            customer_id    INTEGER NOT NULL,
            invoice_amount REAL NOT NULL,
            issue_date     TEXT NOT NULL,
            due_date       TEXT NOT NULL,
            payment_status TEXT NOT NULL DEFAULT 'Pending',
            paid_date      TEXT,
            created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, invoice_number),
            FOREIGN KEY (user_id) REFERENCES users(user_id),
            FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS prediction_history (
            prediction_id            INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_id               INTEGER NOT NULL,
            risk_level               TEXT NOT NULL,
            late_payment_probability REAL NOT NULL,
            prediction_date          TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invoice_id) REFERENCES invoices(invoice_id)
        )
    """)

    conn.commit()
    conn.close()
    print("Database ready ho gaya.")


if __name__ == "__main__":
    init_db()