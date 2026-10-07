from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sqlite3
import tempfile
import unittest

from event_store import EventConflict, EventStore, InvalidOrder, SettledEvent


class EventStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = EventStore(Path(self.temp.name) / 'synthetic.db')
        self.store.initialize()
        self.store.add_order('demo-order', 100)
        self.event = SettledEvent('demo-event', 'demo-order', 100)

    def test_first_event_grants_once(self):
        self.assertEqual(self.store.apply(self.event), 'applied')
        self.assertEqual(self.store.counts(), (1, 1))

    def test_repeated_delivery_is_idempotent(self):
        self.store.apply(self.event)
        for _ in range(10):
            self.assertEqual(self.store.apply(self.event), 'duplicate-event')
        self.assertEqual(self.store.counts(), (1, 1))

    def test_distinct_events_for_one_order_do_not_double_grant(self):
        self.store.apply(self.event)
        self.assertEqual(self.store.apply(SettledEvent('another-event', 'demo-order', 100)),
                         'already-granted')
        self.assertEqual(self.store.counts(), (2, 1))

    def test_changed_payload_cannot_reuse_event_identity(self):
        self.store.apply(self.event)
        with self.assertRaises(EventConflict):
            self.store.apply(SettledEvent('demo-event', 'demo-order', 999))
        self.assertEqual(self.store.counts(), (1, 1))

    def test_identity_cannot_be_reused_for_a_different_order(self):
        self.store.add_order('other-order', 100)
        self.store.apply(self.event)
        with self.assertRaises(EventConflict):
            self.store.apply(SettledEvent('demo-event', 'other-order', 100))
        self.assertEqual(self.store.counts(), (1, 1))

    def test_unknown_order_does_not_record_an_event(self):
        with self.assertRaises(InvalidOrder):
            self.store.apply(SettledEvent('event', 'unknown', 100))
        self.assertEqual(self.store.counts(), (0, 0))

    def test_amount_mismatch_does_not_record_an_event(self):
        with self.assertRaises(InvalidOrder):
            self.store.apply(SettledEvent('event', 'demo-order', 101))
        self.assertEqual(self.store.counts(), (0, 0))

    def test_invalid_values_are_rejected(self):
        for event in [SettledEvent('', 'demo-order', 100),
                      SettledEvent('x', ' ', 100),
                      SettledEvent('x', 'demo-order', -1),
                      SettledEvent('x', 'demo-order', True),
                      SettledEvent('x', 'demo-order', 1.5)]:
            with self.subTest(event=event), self.assertRaises(ValueError):
                self.store.apply(event)
        self.assertEqual(self.store.counts(), (0, 0))

    def test_grant_failure_rolls_back_event_and_allows_retry(self):
        db = self.store.connect()
        try:
            db.execute('''CREATE TRIGGER fail_grant BEFORE INSERT ON grants
                          BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END''')
        finally:
            db.close()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.apply(self.event)
        self.assertEqual(self.store.counts(), (0, 0))
        db = self.store.connect()
        try:
            db.execute('DROP TRIGGER fail_grant')
        finally:
            db.close()
        self.assertEqual(self.store.apply(self.event), 'applied')
        self.assertEqual(self.store.counts(), (1, 1))

    def test_concurrent_redeliveries_use_separate_connections(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(self.store.apply, [self.event] * 32))
        self.assertEqual(outcomes.count('applied'), 1)
        self.assertEqual(outcomes.count('duplicate-event'), 31)
        self.assertEqual(self.store.counts(), (1, 1))

    def test_concurrent_distinct_events_still_grant_once(self):
        events = [SettledEvent(f'event-{i}', 'demo-order', 100) for i in range(32)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(self.store.apply, events))
        self.assertEqual(outcomes.count('applied'), 1)
        self.assertEqual(outcomes.count('already-granted'), 31)
        self.assertEqual(self.store.counts(), (32, 1))

    def test_reopening_store_preserves_deduplication(self):
        self.store.apply(self.event)
        reopened = EventStore(self.store.path)
        self.assertEqual(reopened.apply(self.event), 'duplicate-event')
        self.assertEqual(reopened.counts(), (1, 1))


if __name__ == '__main__':
    unittest.main()
