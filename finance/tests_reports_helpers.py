"""Regression suite for the daily-report views (finance/views/reports.py)
and the money-stats helpers (finance/views/helpers.py).

Two goals:
  1. Pin correct behavior: cash-only stats scope, Stat.default_* correction,
     int() truncation of the diff, confirmed/pending split, date-window
     inclusivity, role scoping and the shared filter set (q / type /
     category / from-to).
  2. Prove fault tolerance ("hamma xatolarga bardoshli"): garbage GET
     params, empty values and weird data must render gracefully (200/302),
     never raise a 500.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal

from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from finance.models import (
    Category, Company, DailyReport, Stat, StatTypes, Transaction, User,
)
from finance.views.helpers import compute_money_stats, preserve_filters

PASSWORD = 'pass12345'


def noon_utc(day):
    """Aware datetime at 12:00 UTC on `day` — noon UTC always falls on the
    same calendar date in Asia/Tashkent (UTC+5), so date__date filters are
    stable no matter when the suite runs."""
    return datetime(day.year, day.month, day.day, 12, 0, tzinfo=dt_timezone.utc)


def today():
    """'Today' exactly the way the owned views compute it (naive local)."""
    return datetime.today().date()


class ReportsTestMixin:
    """Small seed helpers; every user is prefixed with rpt_."""

    def make_user(self, username, role, company=None):
        return User.objects.create_user(
            username=f'rpt_{username}', password=PASSWORD, role=role, company=company,
        )

    def make_report(self, operator, **kwargs):
        defaults = dict(
            type='income', date=timezone.now().date(), category='almashdi',
            is_closed=False, total_uzs=Decimal('1000'),
        )
        defaults.update(kwargs)
        return DailyReport.objects.create(operator=operator, **defaults)

    def make_tx(self, operator, **kwargs):
        defaults = dict(
            type='income', payment_type='cash', amount_uzs=Decimal('1000'),
            counterparty='Test', date=timezone.now(),
        )
        defaults.update(kwargs)
        return Transaction.objects.create(operator=operator, **defaults)


class PreserveFiltersTests(TestCase):
    """preserve_filters builds the redirect back to the filtered list page
    from the `current_qs` hidden POST field."""

    def test_with_current_qs_returns_base_plus_qs(self):
        request = RequestFactory().post('/', {'current_qs': 'from=2026-01-01&to=2026-01-31&q=x'})
        self.assertEqual(
            preserve_filters(request, '/reports/boss/'),
            '/reports/boss/?from=2026-01-01&to=2026-01-31&q=x',
        )

    def test_without_current_qs_returns_bare_base(self):
        request = RequestFactory().post('/', {})
        self.assertEqual(preserve_filters(request, '/reports/boss/'), '/reports/boss/')

    def test_empty_current_qs_returns_bare_base(self):
        request = RequestFactory().post('/', {'current_qs': ''})
        self.assertEqual(preserve_filters(request, '/reports/cashier/'), '/reports/cashier/')

    def test_current_qs_with_unicode_and_special_chars_preserved_verbatim(self):
        qs = "q=O%27tkir&x=1%262%3D3"
        request = RequestFactory().post('/', {'current_qs': qs})
        self.assertEqual(preserve_filters(request, '/reports/boss/'), f'/reports/boss/?{qs}')


class ComputeMoneyStatsScopeTests(ReportsTestMixin, TestCase):
    """compute_money_stats counts ONLY payment_type='cash' transactions;
    click/terminal/bank money is invisible to it."""

    def setUp(self):
        self.operator = self.make_user('scope_op', 'operator')
        closed = self.make_report(self.operator, is_closed=True)
        self.make_tx(self.operator, report=closed, type='income', payment_type='cash',
                     amount_uzs=Decimal('100000'))
        # Non-cash income must be invisible to the stats.
        self.make_tx(self.operator, report=closed, type='income', payment_type='click',
                     click='click1', amount_uzs=Decimal('50000'))
        self.make_tx(self.operator, report=closed, type='income', payment_type='terminal',
                     amount_usd=Decimal('10'))
        self.make_tx(self.operator, report=closed, type='income', payment_type='bank',
                     amount_eur=Decimal('7'))
        self.make_tx(self.operator, report=closed, type='expense', payment_type='cash',
                     amount_uzs=Decimal('30000'))
        self.make_tx(self.operator, report=closed, type='expense', payment_type='bank',
                     amount_uzs=Decimal('7000'))

    def test_income_counts_only_cash(self):
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['income'].total_uzs, Decimal('100000'))

    def test_expense_counts_only_cash(self):
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['expense'].total_uzs, Decimal('30000'))

    def test_noncash_currencies_stay_zero(self):
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['income'].total_usd, Decimal('0'))
        self.assertEqual(stats['confirmed']['income'].total_eur, Decimal('0'))
        self.assertEqual(stats['confirmed']['expense'].total_uzs, Decimal('30000'))


class ComputeMoneyStatsSplitTests(ReportsTestMixin, TestCase):
    """Confirmed vs pending split by report.is_closed; combined = corrected
    confirmed + pending per currency."""

    def setUp(self):
        self.operator = self.make_user('split_op', 'operator')
        closed = self.make_report(self.operator, is_closed=True)
        open_r = self.make_report(self.operator, is_closed=False)
        self.make_tx(self.operator, report=closed, amount_uzs=Decimal('100000'),
                     amount_usd=Decimal('50'))
        self.make_tx(self.operator, report=open_r, amount_uzs=Decimal('40000'),
                     amount_usd=Decimal('10'))

    def test_confirmed_uses_only_closed_reports(self):
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['income'].total_uzs, Decimal('100000'))
        self.assertEqual(stats['confirmed']['income'].total_usd, Decimal('50'))

    def test_pending_uses_only_open_reports(self):
        stats = compute_money_stats()
        self.assertEqual(stats['pending']['income']['total_uzs'], Decimal('40000'))
        self.assertEqual(stats['pending']['income']['total_usd'], Decimal('10'))

    def test_combined_is_confirmed_plus_pending(self):
        stats = compute_money_stats()
        self.assertEqual(stats['combined']['income']['total_uzs'], Decimal('140000'))
        self.assertEqual(stats['combined']['income']['total_usd'], Decimal('60'))

    def test_combined_uses_default_corrected_confirmed(self):
        Stat.objects.create(type=StatTypes.INCOME, default_uzs=Decimal('10000'))
        stats = compute_money_stats()
        # confirmed = 100000 raw - 10000 default = 90000; combined += 40000 pending
        self.assertEqual(stats['confirmed']['income'].total_uzs, Decimal('90000'))
        self.assertEqual(stats['combined']['income']['total_uzs'], Decimal('130000'))


class ComputeMoneyStatsCorrectionTests(ReportsTestMixin, TestCase):
    """Stat.default_* is a manual correction subtracted from the confirmed
    raw totals; repeated computation must be idempotent (no drift)."""

    def setUp(self):
        self.operator = self.make_user('corr_op', 'operator')
        closed = self.make_report(self.operator, is_closed=True)
        self.make_tx(self.operator, report=closed, amount_uzs=Decimal('5000'))
        self.make_tx(self.operator, report=closed, type='expense', amount_uzs=Decimal('1200'))

    def test_income_total_is_raw_minus_default(self):
        Stat.objects.create(type=StatTypes.INCOME, default_uzs=Decimal('1000'))
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['income'].total_uzs, Decimal('4000'))

    def test_expense_total_is_raw_minus_default(self):
        Stat.objects.create(type=StatTypes.EXPENSE, default_uzs=Decimal('200'))
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['expense'].total_uzs, Decimal('1000'))

    def test_repeated_calls_are_idempotent(self):
        Stat.objects.create(type=StatTypes.INCOME, default_uzs=Decimal('1000'))
        first = compute_money_stats()
        second = compute_money_stats()
        self.assertEqual(
            first['confirmed']['income'].total_uzs, second['confirmed']['income'].total_uzs,
        )
        self.assertEqual(second['confirmed']['income'].total_uzs, Decimal('4000'))
        self.assertEqual(Stat.objects.filter(type=StatTypes.INCOME).count(), 1)


class ComputeMoneyStatsDiffPrecisionTests(ReportsTestMixin, TestCase):
    """The diff stat keeps cents: income - expense is exact, then the default
    correction is subtracted."""

    def setUp(self):
        self.operator = self.make_user('trunc_op', 'operator')

    def test_positive_fractional_diff_is_exact(self):
        self.make_tx(self.operator, report=self.make_report(self.operator, is_closed=True),
                     amount_uzs=Decimal('100.75'))
        self.make_tx(self.operator, report=self.make_report(self.operator, is_closed=True),
                     type='expense', amount_uzs=Decimal('0.25'))
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['diff'].total_uzs, Decimal('100.50'))

    def test_negative_diff_is_exact(self):
        self.make_tx(self.operator, report=self.make_report(self.operator, is_closed=True),
                     amount_uzs=Decimal('0.25'))
        self.make_tx(self.operator, report=self.make_report(self.operator, is_closed=True),
                     type='expense', amount_uzs=Decimal('11.00'))
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['diff'].total_uzs, Decimal('-10.75'))

    def test_diff_default_correction_applied(self):
        Stat.objects.create(type=StatTypes.BALANCE, default_uzs=Decimal('5'))
        self.make_tx(self.operator, report=self.make_report(self.operator, is_closed=True),
                     amount_uzs=Decimal('100.75'))
        self.make_tx(self.operator, report=self.make_report(self.operator, is_closed=True),
                     type='expense', amount_uzs=Decimal('0.25'))
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['diff'].total_uzs, Decimal('95.50'))


class ComputeMoneyStatsEmptyDbTests(ReportsTestMixin, TestCase):
    """With an empty database every figure is zero, the Stat rows are
    auto-created and nothing is None."""

    def test_all_zeros_no_none(self):
        stats = compute_money_stats()
        for branch in ('confirmed', 'pending', 'combined'):
            for key in ('income', 'expense', 'diff'):
                for cur in ('uzs', 'usd', 'rub', 'eur'):
                    node = stats[branch][key]
                    value = node[f'total_{cur}'] if isinstance(node, dict) else getattr(node, f'total_{cur}')
                    self.assertIsNotNone(value, f'{branch}/{key}/{cur} is None')
                    self.assertEqual(value, 0, f'{branch}/{key}/{cur} not zero')
                    if branch == 'confirmed':
                        self.assertIsInstance(value, Decimal)

    def test_stat_rows_auto_created(self):
        compute_money_stats()
        self.assertEqual(Stat.objects.count(), 3)
        for stat_type in (StatTypes.INCOME, StatTypes.EXPENSE, StatTypes.BALANCE):
            self.assertTrue(Stat.objects.filter(type=stat_type).exists())


class ComputeMoneyStatsDateRangeTests(ReportsTestMixin, TestCase):
    """The date window is inclusive on both ends (date__date__range)."""

    def setUp(self):
        self.operator = self.make_user('range_op', 'operator')
        d_from = today() - timedelta(days=7)
        d_to = today()
        for day, amount in (
            (d_from - timedelta(days=1), Decimal('90')),   # before window
            (d_from, Decimal('10')),                        # first day -> counted
            (d_to, Decimal('50')),                          # last day -> counted
            (d_to + timedelta(days=1), Decimal('70')),      # after window
        ):
            closed = self.make_report(self.operator, is_closed=True)
            self.make_tx(self.operator, report=closed, amount_uzs=amount,
                         date=noon_utc(day))
        self.d_from, self.d_to = d_from, d_to

    def test_boundaries_inclusive(self):
        stats = compute_money_stats(date_from=self.d_from, date_to=self.d_to)
        self.assertEqual(stats['confirmed']['income'].total_uzs, Decimal('60'))

    def test_outside_transactions_exist_for_control(self):
        # Sanity: the two out-of-window transactions really exist.
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['income'].total_uzs, Decimal('220'))


class ReportListDateWindowTests(ReportsTestMixin, TestCase):
    """BossReportsView date window is inclusive on both boundary days."""

    def setUp(self):
        self.boss = self.make_user('window_boss', 'boss')
        self.operator = self.make_user('window_op', 'operator')
        d_from = today() - timedelta(days=7)
        d_to = today()
        self.r_before = self.make_report(self.operator, date=d_from - timedelta(days=1))
        self.r_first = self.make_report(self.operator, date=d_from)
        self.r_last = self.make_report(self.operator, date=d_to)
        self.r_after = self.make_report(self.operator, date=d_to + timedelta(days=1))
        self.url = reverse('boss_reports')

    def get(self, params=None):
        self.client.force_login(self.boss)
        return self.client.get(self.url, params or {})

    def test_default_window_covers_last_seven_days(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        reports = list(response.context['reports'])
        self.assertIn(self.r_first, reports)
        self.assertIn(self.r_last, reports)
        self.assertNotIn(self.r_before, reports)
        self.assertNotIn(self.r_after, reports)

    def test_explicit_window_boundaries_inclusive(self):
        response = self.get({'from': self.r_first.date.isoformat(),
                             'to': self.r_last.date.isoformat()})
        reports = list(response.context['reports'])
        self.assertIn(self.r_first, reports)
        self.assertIn(self.r_last, reports)
        self.assertNotIn(self.r_before, reports)
        self.assertNotIn(self.r_after, reports)


class BossReportsFilterTests(ReportsTestMixin, TestCase):
    """The shared filter set on the boss listing: type, q (case-insensitive
    across operator username / company / category), multi-category, counts."""

    def setUp(self):
        self.boss = self.make_user('filter_boss', 'boss')
        self.company = Company.objects.create(name='Bekzod Savdo')
        self.op_almashdi = self.make_user('almashdi_op', 'operator')
        self.op_company = self.make_user('company_op', 'operator', company=self.company)
        self.op_plain = self.make_user('plain_op', 'operator')
        d = today() - timedelta(days=1)
        self.r_user = self.make_report(self.op_almashdi, date=d, category='chikako zavod',
                                       total_uzs=Decimal('100'))
        self.r_company = self.make_report(self.op_company, date=d, category='jasur un',
                                          total_uzs=Decimal('200'))
        self.r_category = self.make_report(self.op_plain, date=d, category='almashdi',
                                           total_uzs=Decimal('300'))
        self.r_expense = self.make_report(self.op_plain, date=d, type='expense',
                                          category='mssb xarajat', total_uzs=Decimal('400'))
        self.r_closed = self.make_report(self.op_plain, date=d, category='olma',
                                         is_closed=True, total_uzs=Decimal('500'))
        self.url = reverse('boss_reports')

    def get(self, params=None):
        self.client.force_login(self.boss)
        return self.client.get(self.url, params or {})

    def test_type_param_filters(self):
        response = self.get({'type': 'expense'})
        reports = list(response.context['reports'])
        self.assertEqual(reports, [self.r_expense])

    def test_q_matches_operator_username_case_insensitively(self):
        response = self.get({'q': 'ALMASHDI'})
        reports = list(response.context['reports'])
        self.assertIn(self.r_user, reports)
        self.assertNotIn(self.r_company, reports)

    def test_q_matches_company_name_case_insensitively(self):
        response = self.get({'q': 'BEKZOD'})
        reports = list(response.context['reports'])
        self.assertIn(self.r_company, reports)
        self.assertNotIn(self.r_user, reports)

    def test_q_matches_category_case_insensitively(self):
        response = self.get({'q': 'Chikako'})
        reports = list(response.context['reports'])
        self.assertIn(self.r_user, reports)
        self.assertNotIn(self.r_category, reports)

    def test_q_unicode_apostrophe_word(self):
        company = Company.objects.create(name="O'qituvchi Savdo")
        op = self.make_user('apostrophe_op', 'operator', company=company)
        report = self.make_report(op, date=today() - timedelta(days=1), category='olma')
        response = self.get({'q': "O'QIT"})
        self.assertIn(report, list(response.context['reports']))

    def test_category_multi_select(self):
        response = self.get({'category': ['chikako zavod', 'jasur un']})
        reports = list(response.context['reports'])
        self.assertIn(self.r_user, reports)
        self.assertIn(self.r_company, reports)
        self.assertNotIn(self.r_category, reports)
        self.assertNotIn(self.r_expense, reports)

    def test_totals_sum_only_visible_reports(self):
        response = self.get({'type': 'expense'})
        self.assertEqual(response.context['totals']['total_uzs'], Decimal('400'))

    def test_totals_zero_when_nothing_matches(self):
        response = self.get({'q': 'hech qanday mos kelmaydigan soz'})
        self.assertEqual(list(response.context['reports']), [])
        self.assertEqual(response.context['totals']['total_uzs'], 0)
        self.assertEqual(response.context['totals']['total_usd'], 0)

    def test_pending_and_confirmed_counts_split(self):
        response = self.get()
        self.assertEqual(response.context['pending_count'], 4)
        self.assertEqual(response.context['confirmed_count'], 1)

    def test_garbage_type_param_renders_empty_list(self):
        # Fault tolerance (characterization): unknown type just matches nothing.
        response = self.get({'type': 'banana'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['reports']), [])


class ReportsRoleScopeTests(ReportsTestMixin, TestCase):
    """Role scoping: boss sees everything, cashier only income reports,
    operator only its own reports; access is enforced per role."""

    def setUp(self):
        self.boss = self.make_user('scope_boss', 'boss')
        self.cashier = self.make_user('scope_cashier', 'cashier')
        self.op_a = self.make_user('scope_op_a', 'operator')
        self.op_b = self.make_user('scope_op_b', 'operator')
        d = today() - timedelta(days=1)
        self.income_report = self.make_report(self.op_a, date=d, type='income')
        self.expense_report = self.make_report(self.op_a, date=d, type='expense')
        self.other_report = self.make_report(self.op_b, date=d, type='income')

    def test_boss_sees_all_report_types(self):
        self.client.force_login(self.boss)
        response = self.client.get(reverse('boss_reports'))
        reports = list(response.context['reports'])
        self.assertIn(self.income_report, reports)
        self.assertIn(self.expense_report, reports)

    def test_cashier_sees_only_income_reports(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse('cashier_reports'))
        reports = list(response.context['reports'])
        self.assertIn(self.income_report, reports)
        self.assertNotIn(self.expense_report, reports)

    def test_operator_sees_only_own_reports(self):
        self.client.force_login(self.op_a)
        response = self.client.get(reverse('operator_reports'))
        reports = list(response.context['reports'])
        self.assertIn(self.income_report, reports)
        self.assertNotIn(self.other_report, reports)

    def test_anonymous_redirects_to_login(self):
        for name in ('boss_reports', 'cashier_reports', 'operator_reports'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302, name)

    def test_operator_forbidden_on_boss_reports(self):
        self.client.force_login(self.op_a)
        response = self.client.get(reverse('boss_reports'))
        self.assertEqual(response.status_code, 403)

    def test_cashier_forbidden_on_operator_reports(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse('operator_reports'))
        self.assertEqual(response.status_code, 403)


class OperatorReportsViewTests(ReportsTestMixin, TestCase):
    """Operator extras: unreported_count, the 3-day expiry boundary and the
    report_date defaulting."""

    def setUp(self):
        self.operator = self.make_user('extra_op', 'operator')
        self.other = self.make_user('extra_other', 'operator')
        self.client.force_login(self.operator)
        self.url = reverse('operator_reports')

    def test_unreported_count_counts_only_own_unreported_on_report_date(self):
        d = today() - timedelta(days=1)
        self.make_tx(self.operator, type='income', payment_type='cash',
                     amount_uzs=Decimal('1'), date=noon_utc(d))                       # counted
        self.make_tx(self.operator, type='income', payment_type='cash',
                     amount_uzs=Decimal('2'), date=noon_utc(d - timedelta(days=1)))   # other day
        reported = self.make_report(self.operator, date=d, is_closed=True)
        self.make_tx(self.operator, type='income', payment_type='cash',
                     amount_uzs=Decimal('3'), report=reported, date=noon_utc(d))      # has report
        self.make_tx(self.other, type='income', payment_type='cash',
                     amount_uzs=Decimal('4'), date=noon_utc(d))                       # other operator
        response = self.client.get(self.url, {'report_date': d.isoformat()})
        self.assertEqual(response.context['unreported_count'], 1)

    def test_is_expired_false_exactly_three_days_ago(self):
        response = self.client.get(self.url, {
            'report_date': (today() - timedelta(days=3)).isoformat(),
        })
        self.assertFalse(response.context['is_expired'])

    def test_is_expired_true_four_days_ago(self):
        response = self.client.get(self.url, {
            'report_date': (today() - timedelta(days=4)).isoformat(),
        })
        self.assertTrue(response.context['is_expired'])

    def test_report_date_defaults_to_to_param(self):
        response = self.client.get(self.url, {'to': '2026-08-15'})
        self.assertEqual(response.context['report_date'], '2026-08-15')

    def test_report_date_defaults_to_today_without_params(self):
        response = self.client.get(self.url)
        self.assertEqual(response.context['report_date'], response.context['to'])
        self.assertEqual(response.context['report_date'], today().isoformat())


class ReportsFaultToleranceTests(ReportsTestMixin, TestCase):
    """Garbage GET params must render gracefully (200 with sane fallbacks),
    never a 500. Desired behavior — written test-first against views that
    strpyn parsed user input directly."""

    def setUp(self):
        self.boss = self.make_user('ft_boss', 'boss')
        self.cashier = self.make_user('ft_cashier', 'cashier')
        self.operator = self.make_user('ft_op', 'operator')
        d = today() - timedelta(days=1)
        self.report = self.make_report(self.operator, date=d, total_uzs=Decimal('777'))
        self.default_from = (today() - timedelta(days=7)).isoformat()
        self.default_to = today().isoformat()

    def boss_get(self, params):
        self.client.force_login(self.boss)
        return self.client.get(reverse('boss_reports'), params)

    def test_boss_garbage_from_falls_back_to_default_window(self):
        response = self.boss_get({'from': 'banana'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['from'], self.default_from)
        self.assertEqual(response.context['to'], self.default_to)
        self.assertIn(self.report, list(response.context['reports']))

    def test_boss_garbage_to_falls_back_to_today(self):
        response = self.boss_get({'to': 'not-a-date'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['to'], self.default_to)
        self.assertIn(self.report, list(response.context['reports']))

    def test_boss_impossible_calendar_date_falls_back(self):
        response = self.boss_get({'from': '2026-02-30'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['from'], self.default_from)

    def test_boss_whitespace_only_from_falls_back(self):
        response = self.boss_get({'from': '   '})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['from'], self.default_from)

    def test_boss_from_is_float_like_string_falls_back(self):
        response = self.boss_get({'from': '3.14'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['from'], self.default_from)

    def test_boss_garbage_from_keeps_valid_to(self):
        valid_to = (today() - timedelta(days=1)).isoformat()
        response = self.boss_get({'from': 'banana', 'to': valid_to})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['from'], self.default_from)
        self.assertEqual(response.context['to'], valid_to)
        self.assertIn(self.report, list(response.context['reports']))

    def test_boss_garbage_to_keeps_valid_from(self):
        valid_from = (today() - timedelta(days=2)).isoformat()
        response = self.boss_get({'from': valid_from, 'to': '<script>'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['from'], valid_from)
        self.assertEqual(response.context['to'], self.default_to)
        self.assertIn(self.report, list(response.context['reports']))

    def test_cashier_garbage_from_renders_200(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse('cashier_reports'), {'from': '%%%'})
        self.assertEqual(response.status_code, 200)

    def test_operator_garbage_report_date_falls_back_to_to(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse('operator_reports'), {'report_date': 'garbage'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['report_date'], response.context['to'])
        self.assertFalse(response.context['is_expired'])

    def test_operator_garbage_report_date_prefers_valid_to_param(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse('operator_reports'), {
            'report_date': 'garbage', 'to': '2026-08-15',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['report_date'], '2026-08-15')

    def test_operator_garbage_to_falls_back(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse('operator_reports'), {'to': 'banana'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['to'], self.default_to)
        self.assertEqual(response.context['report_date'], self.default_to)

    def test_reversed_date_window_renders_empty(self):
        # Characterization: from > to is not an error, just an empty window.
        response = self.boss_get({'from': self.default_to, 'to': self.default_from})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['reports']), [])
        self.assertEqual(response.context['totals']['total_uzs'], 0)

    def test_post_to_report_list_is_405_not_500(self):
        self.client.force_login(self.boss)
        response = self.client.post(reverse('boss_reports'), {'from': 'banana'})
        self.assertEqual(response.status_code, 405)


class ComputeMoneyStatsHugeAmountsTests(ReportsTestMixin, TestCase):
    """Amounts at the field's max_digits=15 boundary flow through the stats
    without overflow or precision surprises."""

    def test_max_digits_amount_sums_exactly(self):
        operator = self.make_user('huge_op', 'operator')
        closed = self.make_report(operator, is_closed=True)
        self.make_tx(operator, report=closed, amount_uzs=Decimal('99999999999.99'))
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['income'].total_uzs, Decimal('99999999999.99'))
        self.assertEqual(stats['combined']['income']['total_uzs'], Decimal('99999999999.99'))
