import unittest
from datetime import date

from studentflow.dates import (current_week, days_until, due_label, in_next_seven_days,
                               is_overdue, is_today, next_seven_days, parse_date)
from studentflow.planning import completion_percentage, generate_sessions, priority_score, recommend


def item(**changes):
    record = dict(id='one', title='Midterm', kind='exam', priority='normal',
                  due_date='2027-01-05', minutes=240, completed=0, created_at='2026-12-01')
    return dict(record, **changes)


class DateTests(unittest.TestCase):
    def test_calendar_boundaries(self):
        today = date(2026, 12, 31)
        self.assertTrue(is_today('2026-12-31', today))
        self.assertTrue(is_overdue('2026-12-30', today))
        self.assertEqual(days_until('2027-01-01', today), 1)
        self.assertEqual(due_label('2027-01-01', today), 'Tomorrow')
        self.assertTrue(in_next_seven_days('2027-01-06', today))
        self.assertFalse(in_next_seven_days('2027-01-07', today))
        self.assertFalse(in_next_seven_days('2026-12-30', today))
        self.assertEqual(len(next_seven_days(today)), 7)
        self.assertEqual(current_week(today)[0], date(2026, 12, 28))
        self.assertEqual(current_week(today)[-1], date(2027, 1, 3))

    def test_leap_day_and_dst_are_calendar_days(self):
        self.assertEqual(days_until('2028-03-01', date(2028, 2, 28)), 2)
        self.assertEqual(days_until('2027-03-15', date(2027, 3, 13)), 2)
        self.assertEqual(days_until('2027-11-08', date(2027, 11, 6)), 2)
        with self.assertRaises(ValueError):
            parse_date('2027-02-29')
        with self.assertRaises(ValueError):
            parse_date('01/05/2027')


class RecommendationTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2027, 1, 1)

    def test_overdue_dominates_and_closer_deadlines_gain_urgency(self):
        overdue = item(due_date='2026-12-31', priority='low', kind='study-session', minutes=5)
        due_today = item(due_date='2027-01-01', priority='high', minutes=1440)
        self.assertGreater(priority_score(overdue, self.today), priority_score(due_today, self.today))
        self.assertGreater(priority_score(item(due_date='2027-01-02'), self.today),
                           priority_score(item(due_date='2027-01-03'), self.today))

    def test_priority_type_and_workload_contribute(self):
        for high, low in [(item(priority='high'), item(priority='low')),
                          (item(kind='exam'), item(kind='assignment')),
                          (item(minutes=240), item(minutes=30))]:
            self.assertGreater(priority_score(high, self.today), priority_score(low, self.today))

    def test_ties_and_explanations_are_deterministic(self):
        a, b = item(id='a'), item(id='b')
        self.assertEqual(recommend([b, a], self.today)['item']['id'], 'a')
        self.assertEqual(recommend([a, b], self.today), recommend([b, a], self.today))
        self.assertIn('Due in 4 day(s)', recommend([a], self.today)['reason'])
        self.assertIn('240 min remaining', recommend([a], self.today)['reason'])
        self.assertIsNone(recommend([item(completed=1)], self.today))
        self.assertIsNone(recommend([item(has_active_sessions=True)], self.today))

    def test_completion_empty_and_rounding(self):
        self.assertIsNone(completion_percentage([]))
        self.assertEqual(completion_percentage([item()]), 0)
        self.assertEqual(completion_percentage([item(completed=1)]), 100)
        self.assertEqual(completion_percentage([item(completed=1), item(), item()]), 33)


class SessionDistributionTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2027, 1, 1)

    def test_total_manageable_and_deterministic(self):
        task = item(due_date='2027-01-08')
        sessions = generate_sessions(task, self.today)
        self.assertEqual(sum(session.minutes for session in sessions), 240)
        self.assertTrue(all(5 <= session.minutes <= 45 for session in sessions))
        self.assertTrue(all('2027-01-01' <= session.due_date < '2027-01-08' for session in sessions))
        self.assertEqual(sessions, generate_sessions(task, self.today))
        self.assertEqual(len({session.due_date for session in sessions}), 6)

    def test_exact_workload_for_every_supported_duration(self):
        for minutes in range(5, 1441):
            sessions = generate_sessions(item(minutes=minutes), self.today)
            self.assertEqual(sum(session.minutes for session in sessions), minutes)
            self.assertTrue(all(5 <= session.minutes <= 45 for session in sessions))

    def test_today_and_overdue(self):
        sessions = generate_sessions(item(due_date='2027-01-01'), self.today)
        self.assertTrue(all(session.due_date == '2027-01-01' for session in sessions))
        self.assertEqual(sum(session.minutes for session in sessions), 240)
        with self.assertRaisesRegex(ValueError, 'deadline has passed'):
            generate_sessions(item(due_date='2026-12-31'), self.today)

    def test_existing_workload_is_respected(self):
        sessions = generate_sessions(item(minutes=45, due_date='2027-01-03'), self.today,
                                     {'2027-01-01': 90})
        self.assertEqual(sessions[0].due_date, '2027-01-02')

    def test_bad_duration_is_rejected(self):
        for minutes in [0, -1, 1441, True, 2.5]:
            with self.subTest(minutes=minutes), self.assertRaises(ValueError):
                generate_sessions(item(minutes=minutes), self.today)
