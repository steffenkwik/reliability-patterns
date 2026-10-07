"""Independent SQLite specimen using synthetic events; no payment integration.

Assumption: the caller has already authenticated and validated the event source.
This module demonstrates transactional effects, not webhook signature checking.
"""
from dataclasses import dataclass
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class SettledEvent:
    event_id: str
    order_id: str
    amount: int


class EventConflict(ValueError):
    """An event identity was reused with different contents."""


class InvalidOrder(ValueError):
    """The synthetic order does not exist or its amount does not match."""


class EventStore:
    def __init__(self, path: str | Path):
        self.path = str(path)

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        db.execute('PRAGMA foreign_keys = ON')
        return db

    def initialize(self) -> None:
        db = self.connect()
        try:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY,
                    expected_amount INTEGER NOT NULL CHECK(expected_amount > 0)
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL REFERENCES orders(id),
                    amount INTEGER NOT NULL CHECK(amount > 0)
                );
                CREATE TABLE IF NOT EXISTS grants (
                    order_id TEXT PRIMARY KEY REFERENCES orders(id)
                );
            ''')
        finally:
            db.close()

    def add_order(self, order_id: str, amount: int) -> None:
        self._validate(SettledEvent('seed', order_id, amount))
        db = self.connect()
        try:
            db.execute('INSERT INTO orders VALUES (?, ?)', (order_id, amount))
        finally:
            db.close()

    @staticmethod
    def _validate(event: SettledEvent) -> None:
        for identity in (event.event_id, event.order_id):
            if not isinstance(identity, str) or not identity.strip() or len(identity) > 128:
                raise ValueError('Identifiers must be nonempty strings up to 128 characters.')
        if type(event.amount) is not int or event.amount <= 0:
            raise ValueError('Amount must be a positive integer; booleans are not amounts.')

    def apply(self, event: SettledEvent) -> str:
        """Atomically record an event and grant once for its order.

        Returns applied, duplicate-event, or already-granted. Distinct authentic
        event IDs for the same order are recorded without creating another grant.
        """
        self._validate(event)
        db = self.connect()
        try:
            # Acquire SQLite's write reservation before read/check/write. Every
            # contender gets a new connection; the database mediates contention.
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT order_id, amount FROM events WHERE id = ?',
                                  (event.event_id,)).fetchone()
            if previous is not None:
                if previous != (event.order_id, event.amount):
                    raise EventConflict('Event identity conflicts with the stored event.')
                db.execute('COMMIT')
                return 'duplicate-event'
            order = db.execute('SELECT expected_amount FROM orders WHERE id = ?',
                               (event.order_id,)).fetchone()
            if order is None or order[0] != event.amount:
                raise InvalidOrder('Unknown order or mismatched amount.')
            db.execute('INSERT INTO events VALUES (?, ?, ?)',
                       (event.event_id, event.order_id, event.amount))
            grant = db.execute('''INSERT INTO grants(order_id) VALUES (?)
                                  ON CONFLICT(order_id) DO NOTHING''', (event.order_id,))
            outcome = 'applied' if grant.rowcount == 1 else 'already-granted'
            db.execute('COMMIT')
            return outcome
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
        finally:
            db.close()

    def counts(self) -> tuple[int, int]:
        db = self.connect()
        try:
            return (db.execute('SELECT count(*) FROM events').fetchone()[0],
                    db.execute('SELECT count(*) FROM grants').fetchone()[0])
        finally:
            db.close()
