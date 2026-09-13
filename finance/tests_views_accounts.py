"""Exhaustive regression suite for finance/views/accounts.py.

Proves both correct behavior (access control, stats math, report recalc via
signals) and fault tolerance: garbage dates, non-numeric amounts, empty
payloads, missing pks and invalid enum values must render or redirect
gracefully — never a 500 on user input.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from finance.models import (
    Category, Company, Counterparty, DailyReport, Transaction, User,
)

PASSWORD = 'pass12345'


def make_user(username, role, **kwargs):
    return User.objects.create_user(username=username, password=PASSWORD, role=role, **kwargs)


def expected_stats(income, expense):
    """Build the {income, expense, diff} shape the views compute."""
    income = {k: Decimal(str(v)) for k, v in income.items()}
    expense = {k: Decimal(str(v)) for k, v in expense.items()}
    diff = {k: income[k] - expense[k] for k in income}
    return {'income': income, 'expense': expense, 'diff': diff}


class AccountsTestMixin:
    """Shared users and seeding helpers. All usernames carry the vac_ prefix."""

    def setUp(self):
        super().setUp()
        self.boss = make_user('vac_boss', 'boss')
        self.cashier = make_user('vac_cashier', 'cashier')
        self.operator = make_user('vac_operator', 'operator')

    def make_report(self, operator=None, type='income', is_closed=True, **kwargs):
        return DailyReport.objects.create(
            operator=operator or self.operator, type=type, is_closed=is_closed,
            date=timezone.now().date(), category='vac-cat', **kwargs,
        )

    def make_tx(self, report=None, type='income', payment_type='cash', click=None,
                usd=None, uzs=None, rub=None, eur=None, operator=None, date=None):
        return Transaction.objects.create(
            date=date or timezone.now(), type=type, payment_type=payment_type,
            click=click, amount_usd=usd, amount_uzs=uzs, amount_rub=rub,
            amount_eur=eur, description='desc', counterparty='vac counterparty',
            operator=operator or self.operator, report=report,
        )

    def day_params(self):
        today = timezone.now().date().isoformat()
        return {'from': today, 'to': today}


class FinancePageAccessTests(AccountsTestMixin, TestCase):
    """Access matrix of the finance page: boss/cashier/superuser in, everyone else out."""

    def test_anon_redirected_to_login(self):
        response = self.client.get(reverse('finance_page'))
        self.assertRedirects(response, reverse('login'))

    def test_operator_redirected_to_login(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse('finance_page'))
        self.assertRedirects(response, reverse('login'))

    def test_boss_gets_200(self):
        self.client.force_login(self.boss)
        self.assertEqual(self.client.get(reverse('finance_page')).status_code, 200)

    def test_cashier_gets_200(self):
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.get(reverse('finance_page')).status_code, 200)

    def test_superuser_gets_200(self):
        superuser = User.objects.create_superuser('vac_super', None, PASSWORD)
        self.client.force_login(superuser)
        self.assertEqual(self.client.get(reverse('finance_page')).status_code, 200)


class FinancePageStatsTests(AccountsTestMixin, TestCase):
    """noncash_stats / all_stats math: exact numbers, cash only in all_stats."""

    def setUp(self):
        super().setUp()
        # confirmed income: click1, 100k UZS + 10 USD
        conf_income = self.make_report(type='income', is_closed=True)
        self.make_tx(conf_income, type='income', payment_type='click', click='click1',
                     uzs=Decimal('100000'), usd=Decimal('10'))
        # confirmed expense: cash 30k UZS (cash must stay out of noncash_stats)
        conf_expense = self.make_report(type='expense', is_closed=True)
        self.make_tx(conf_expense, type='expense', payment_type='cash',
                     uzs=Decimal('30000'))
        # pending income: terminal 5 USD + 2 EUR
        pend_income = self.make_report(type='income', is_closed=False)
        self.make_tx(pend_income, type='income', payment_type='terminal',
                     usd=Decimal('5'), eur=Decimal('2'))
        # pending expense: bank 20k UZS
        pend_expense = self.make_report(type='expense', is_closed=False)
        self.make_tx(pend_expense, type='expense', payment_type='bank',
                     uzs=Decimal('20000'))
        self.client.force_login(self.boss)

    def get_stats(self):
        response = self.client.get(reverse('finance_page'), self.day_params())
        return response.context['noncash_stats'], response.context['all_stats']

    def test_noncash_stats_excludes_cash_and_matches_seed_exactly(self):
        zero = {'total_usd': 0, 'total_uzs': 0, 'total_rub': 0, 'total_eur': 0}
        noncash, _ = self.get_stats()
        # combined = confirmed + pending; the cash expense stays out
        self.assertEqual(
            noncash['combined'],
            expected_stats(
                income={'total_usd': 15, 'total_uzs': 100000, 'total_rub': 0, 'total_eur': 2},
                expense={'total_usd': 0, 'total_uzs': 20000, 'total_rub': 0, 'total_eur': 0},
            ),
        )
        self.assertEqual(
            noncash['pending'],
            expected_stats(
                income={'total_usd': 5, 'total_uzs': 0, 'total_rub': 0, 'total_eur': 2},
                expense={'total_usd': 0, 'total_uzs': 20000, 'total_rub': 0, 'total_eur': 0},
            ),
        )

    def test_all_stats_includes_cash_and_matches_seed_exactly(self):
        _, all_stats = self.get_stats()
        self.assertEqual(
            all_stats['combined'],
            expected_stats(
                income={'total_usd': 15, 'total_uzs': 100000, 'total_rub': 0, 'total_eur': 2},
                expense={'total_usd': 0, 'total_uzs': 50000, 'total_rub': 0, 'total_eur': 0},
            ),
        )
        # confirmed-only slice: 100k income vs 30k cash expense
        self.assertEqual(
            all_stats['income'],
            {'total_usd': Decimal('10'), 'total_uzs': Decimal('100000'),
             'total_rub': Decimal('0'), 'total_eur': Decimal('0')},
        )
        self.assertEqual(
            all_stats['expense'],
            {'total_usd': Decimal('0'), 'total_uzs': Decimal('30000'),
             'total_rub': Decimal('0'), 'total_eur': Decimal('0')},
        )
        # cash tx is in all but not in noncash combined expense
        self.assertEqual(all_stats['combined']['expense']['total_uzs'], Decimal('50000'))


class FinancePageIncomePostTests(AccountsTestMixin, TestCase):
    """Income modal submission: success path, click keying, graceful failures
    reopening the income modal instead of crashing."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.cashier)
        Counterparty.objects.get_or_create(name='Vac Manba', defaults={'group': 'income'})

    def post_income(self, **overrides):
        payload = {
            'kind': 'income', 'counterparty': 'Vac Manba', 'purpose': 'foyda',
            'amount_usd': '10', 'amount_uzs': '100000', 'amount_rub': '', 'amount_eur': '',
            'payment_type': 'terminal', 'click': '', 'comment': '',
        }
        payload.update(overrides)
        return self.client.post(reverse('finance_page'), payload)

    def test_valid_income_redirects_and_creates_transaction(self):
        response = self.post_income()
        self.assertRedirects(response, reverse('finance_page'))
        tx = Transaction.objects.filter(type='income').latest('pk')
        self.assertEqual(tx.amount_usd, Decimal('10'))
        self.assertEqual(tx.amount_uzs, Decimal('100000'))
        self.assertEqual(tx.operator, self.cashier)
        self.assertEqual(tx.report.category, 'Vac Manba')
        self.assertEqual(tx.report.desc, 'Maqsad: foyda')

    def test_click_income_stores_click_value_and_report_detail_keys(self):
        self.post_income(payment_type='click', click='click1')
        tx = Transaction.objects.filter(type='income').latest('pk')
        self.assertEqual(tx.click, 'click1')
        self.assertEqual(tx.report.usd_detail, {'click1': 10.0})
        self.assertEqual(tx.report.uzs_detail, {'click1': 100000.0})
        self.assertEqual(tx.report.total_usd, Decimal('10'))
        self.assertTrue(tx.report.is_closed)

    def test_terminal_income_needs_no_click_value(self):
        self.post_income(payment_type='terminal')
        tx = Transaction.objects.filter(type='income').latest('pk')
        self.assertIsNone(tx.click)
        self.assertEqual(tx.report.usd_detail, {'terminal': 10.0})

    def test_invalid_income_reopens_income_modal_without_creating_tx(self):
        before = Transaction.objects.count()
        response = self.post_income(counterparty='', amount_uzs='abc')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "x-data=\"{ open: true }\"")
        self.assertEqual(response.context['failed_modal'], 'income')
        self.assertEqual(Transaction.objects.count(), before)

    def test_empty_post_redirects_without_creating_tx(self):
        before = Transaction.objects.count()
        response = self.client.post(reverse('finance_page'), {})
        self.assertRedirects(response, reverse('finance_page'))
        self.assertEqual(Transaction.objects.count(), before)

    def test_unicode_income_counterparty_is_accepted(self):
        response = self.post_income(
            counterparty='__new__', other_counterparty='Отличное дело')
        self.assertRedirects(response, reverse('finance_page'))
        self.assertTrue(
            Counterparty.objects.filter(name='Отличное дело', group='income').exists())
        self.assertEqual(
            Transaction.objects.filter(counterparty='Отличное дело').count(), 1)


class FinancePageExpensePostTests(AccountsTestMixin, TestCase):
    """Expense modal submission: success path, graceful failures reopening the
    expense modal, negative/zero amounts never 500."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.cashier)
        Category.objects.get_or_create(name='vac xarajat', defaults={'group': 'expense'})

    def post_expense(self, **overrides):
        payload = {
            'kind': 'expense', 'category': 'vac xarajat', 'exp_type': 'expense',
            'amount_uzs': '50000', 'amount_usd': '', 'amount_rub': '', 'amount_eur': '',
            'payment_type': 'cash', 'click': '', 'description': '',
        }
        payload.update(overrides)
        return self.client.post(reverse('finance_page'), payload)

    def test_valid_expense_redirects_and_creates_transaction(self):
        response = self.post_expense()
        self.assertRedirects(response, reverse('finance_page'))
        tx = Transaction.objects.filter(type='expense').latest('pk')
        self.assertEqual(tx.amount_uzs, Decimal('50000'))
        self.assertFalse(tx.report.is_closed)
        self.assertTrue(tx.report.desc.startswith('Maqsad: chiqim'))

    def test_invalid_expense_reopens_expense_modal_without_creating_tx(self):
        before = Transaction.objects.count()
        response = self.post_expense(exp_type='', amount_uzs='garbage')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "x-data=\"{ open: true }\"")
        self.assertEqual(response.context['failed_modal'], 'expense')
        self.assertEqual(Transaction.objects.count(), before)

    def test_missing_category_with_garbage_amount_stays_graceful(self):
        before = Transaction.objects.count()
        response = self.post_expense(category='', amount_uzs='!!!')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Transaction.objects.count(), before)

    def test_negative_amount_is_handled_without_500(self):
        response = self.post_expense(amount_uzs='-5000')
        self.assertRedirects(response, reverse('finance_page'))
        tx = Transaction.objects.filter(type='expense').latest('pk')
        self.assertEqual(tx.amount_uzs, Decimal('-5000'))

    def test_zero_only_submission_is_handled_without_500(self):
        response = self.post_expense(amount_uzs='0')
        self.assertRedirects(response, reverse('finance_page'))
        tx = Transaction.objects.filter(type='expense').latest('pk')
        self.assertEqual(tx.amount_uzs, Decimal('0'))


class DashboardGarbageDateTests(AccountsTestMixin, TestCase):
    """Malformed from/to/report_date query strings must render (200), never 500."""

    def test_finance_page_survives_garbage_dates(self):
        self.client.force_login(self.boss)
        self.assertEqual(
            self.client.get(reverse('finance_page'), {'from': 'garbage'}).status_code, 200)
        self.assertEqual(
            self.client.get(reverse('finance_page'), {'to': '9999-99-99'}).status_code, 200)

    def test_boss_dashboard_survives_garbage_dates(self):
        self.client.force_login(self.boss)
        response = self.client.get(reverse('boss_dashboard'), {'from': 'garbage', 'to': ''})
        self.assertEqual(response.status_code, 200)

    def test_cashier_dashboard_survives_garbage_dates(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse('cashier_dashboard'), {'to': 'not-a-date'})
        self.assertEqual(response.status_code, 200)

    def test_operator_dashboard_survives_garbage_dates(self):
        self.client.force_login(self.operator)
        for params in ({'report_date': 'garbage'}, {'from': 'x', 'to': 'y'}):
            response = self.client.get(reverse('operator_dashboard'), params)
            self.assertEqual(response.status_code, 200)


class TransactionViewTests(AccountsTestMixin, TestCase):
    """Edit transaction page: render, guarded updates, report totals recalc via
    signals, and fault tolerance for garbage amounts."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.boss)
        self.report = self.make_report(type='income', is_closed=True)
        self.tx = self.make_tx(self.report, type='income', payment_type='click',
                               click='click1', uzs=Decimal('100000'))

    def url(self):
        return reverse('transaction', args=[self.tx.pk])

    def test_get_renders_for_boss(self):
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['transaction'].pk, self.tx.pk)

    def test_get_missing_pk_redirects_to_transaction_list(self):
        response = self.client.get(reverse('transaction', args=[999999]))
        self.assertRedirects(response, reverse('transaction_list'))

    def test_post_updates_amount_and_report_totals_recalculate(self):
        response = self.client.post(self.url(), {
            'payment_type': 'terminal', 'click': '',
            'amount_usd': '', 'amount_uzs': '250000', 'amount_rub': '', 'amount_eur': '',
        })
        self.assertRedirects(response, reverse('transaction_list'))
        self.tx.refresh_from_db()
        self.report.refresh_from_db()
        self.assertEqual(self.tx.amount_uzs, Decimal('250000'))
        self.assertEqual(self.report.total_uzs, Decimal('250000'))
        self.assertEqual(self.report.uzs_detail, {'terminal': 250000.0})

    def test_post_click_payment_stores_click_value_as_detail_key(self):
        self.client.post(self.url(), {
            'payment_type': 'click', 'click': 'click2',
            'amount_usd': '', 'amount_uzs': '5000', 'amount_rub': '', 'amount_eur': '',
        })
        self.tx.refresh_from_db()
        self.report.refresh_from_db()
        self.assertEqual(self.tx.click, 'click2')
        self.assertEqual(self.report.uzs_detail, {'click2': 5000.0})

    def test_zero_amount_stored_as_falsy(self):
        self.client.post(self.url(), {
            'payment_type': 'cash', 'click': '',
            'amount_usd': '0', 'amount_uzs': '', 'amount_rub': '', 'amount_eur': '',
        })
        self.tx.refresh_from_db()
        self.assertFalse(self.tx.amount_usd)
        self.assertIsNone(self.tx.amount_uzs)

    def test_garbage_amount_rerenders_with_errors_and_changes_nothing(self):
        before = (self.tx.amount_usd, self.tx.amount_uzs, self.tx.amount_rub)
        response = self.client.post(self.url(), {
            'payment_type': 'cash', 'click': '',
            'amount_usd': 'abc', 'amount_uzs': '12.5', 'amount_rub': 'x!', 'amount_eur': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('amount_usd', response.context['form'].errors)
        self.assertIn('amount_rub', response.context['form'].errors)
        self.tx.refresh_from_db()
        self.assertEqual((self.tx.amount_usd, self.tx.amount_uzs, self.tx.amount_rub), before)

    def test_huge_decimal_over_column_limit_rerenders_without_500(self):
        response = self.client.post(self.url(), {
            'payment_type': 'cash', 'click': '',
            'amount_usd': '123456789012345.67', 'amount_uzs': '', 'amount_rub': '',
            'amount_eur': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('amount_usd', response.context['form'].errors)

    def test_max_boundary_decimal_is_still_accepted(self):
        response = self.client.post(self.url(), {
            'payment_type': 'cash', 'click': '',
            'amount_usd': '9999999999999.99', 'amount_uzs': '', 'amount_rub': '',
            'amount_eur': '',
        })
        self.assertRedirects(response, reverse('transaction_list'))
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.amount_usd, Decimal('9999999999999.99'))

    def test_missing_payment_type_is_a_form_error(self):
        response = self.client.post(self.url(), {
            'click': '', 'amount_usd': '', 'amount_uzs': '7', 'amount_rub': '',
            'amount_eur': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('payment_type', response.context['form'].errors)
        self.tx.refresh_from_db()
        self.assertEqual(self.tx.payment_type, 'click')

    def test_click_payment_without_card_is_a_form_error(self):
        response = self.client.post(self.url(), {
            'payment_type': 'click', 'click': '', 'amount_uzs': '7',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('click', response.context['form'].errors)

    def test_post_missing_pk_redirects_to_transaction_list(self):
        response = self.client.post(reverse('transaction', args=[999999]), {})
        self.assertRedirects(response, reverse('transaction_list'))


class TransactionDeleteViewTests(AccountsTestMixin, TestCase):
    """Deleting transactions keeps report totals equal to the sum of remaining
    transactions, removes empty reports, and is boss-only."""

    def setUp(self):
        super().setUp()

    def test_access_boss_302_cashier_operator_403_anon_login(self):
        report = self.make_report()
        tx = self.make_tx(report)
        url = reverse('transaction_delete', args=[tx.pk])
        self.client.force_login(self.cashier)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.operator)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.logout()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('login')))
        self.client.force_login(self.boss)
        self.assertRedirects(self.client.post(url), reverse('transaction_list'))

    def test_delete_with_remaining_tx_recalculates_report_and_drops_orphan_key(self):
        report = self.make_report(type='income', is_closed=True)
        click_tx = self.make_tx(report, payment_type='click', click='click1',
                                uzs=Decimal('100000'), usd=Decimal('10'))
        self.make_tx(report, payment_type='terminal', uzs=Decimal('50000'))
        self.client.force_login(self.boss)
        response = self.client.post(reverse('transaction_delete', args=[click_tx.pk]))
        self.assertRedirects(response, reverse('transaction_list'))
        report.refresh_from_db()
        self.assertEqual(report.total_uzs, Decimal('50000'))
        self.assertEqual(report.total_usd, Decimal('0'))
        self.assertEqual(report.uzs_detail, {'terminal': 50000.0})
        self.assertNotIn('click1', report.uzs_detail or {})

    def test_deleting_last_tx_deletes_empty_report(self):
        report = self.make_report()
        tx = self.make_tx(report, uzs=Decimal('40000'))
        self.client.force_login(self.boss)
        self.client.post(reverse('transaction_delete', args=[tx.pk]))
        self.assertFalse(DailyReport.objects.filter(pk=report.pk).exists())
        self.assertFalse(Transaction.objects.filter(pk=tx.pk).exists())

    def test_other_tx_remains_so_report_is_kept(self):
        report = self.make_report()
        gone = self.make_tx(report, uzs=Decimal('40000'))
        kept = self.make_tx(report, uzs=Decimal('60000'))
        self.client.force_login(self.boss)
        self.client.post(reverse('transaction_delete', args=[gone.pk]))
        self.assertTrue(DailyReport.objects.filter(pk=report.pk).exists())
        self.assertTrue(Transaction.objects.filter(pk=kept.pk).exists())

    def test_tx_without_report_deletes_cleanly(self):
        tx = self.make_tx(report=None, uzs=Decimal('1'))
        self.client.force_login(self.boss)
        response = self.client.post(reverse('transaction_delete', args=[tx.pk]))
        self.assertRedirects(response, reverse('transaction_list'))
        self.assertFalse(Transaction.objects.filter(pk=tx.pk).exists())

    def test_missing_pk_redirects_without_crash(self):
        self.client.force_login(self.boss)
        response = self.client.post(reverse('transaction_delete', args=[999999]))
        self.assertRedirects(response, reverse('transaction_list'))


class UserListCreateViewTests(AccountsTestMixin, TestCase):
    """Boss-only user management: listing and creation with hashed passwords."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.boss)

    def test_get_lists_users(self):
        response = self.client.get(reverse('users'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.operator, response.context['users'])

    def test_post_valid_creates_user_with_hashed_password_and_company(self):
        response = self.client.post(reverse('users'), {
            'username': 'vac_newcashier', 'role': 'cashier',
            'password': 'pw1234567', 'company_name': 'Vac Co',
        })
        self.assertRedirects(response, reverse('users'))
        user = User.objects.filter(username='vac_newcashier').first()
        self.assertIsNotNone(user)
        self.assertNotEqual(user.password, 'pw1234567')
        self.assertTrue(user.check_password('pw1234567'))
        self.assertEqual(user.company.name, 'Vac Co')

    def test_post_invalid_re_renders_without_creating(self):
        before = User.objects.count()
        response = self.client.post(reverse('users'), {
            'username': 'vac_broken', 'role': 'cashier', 'password': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), before)

    def test_post_duplicate_username_re_renders_without_creating(self):
        before = User.objects.count()
        response = self.client.post(reverse('users'), {
            'username': 'vac_operator', 'role': 'operator', 'password': 'pw1234567',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), before)

    def test_post_apostrophe_username_is_rejected_gracefully(self):
        before = User.objects.count()
        response = self.client.post(reverse('users'), {
            "username": "o'g'li_user", 'role': 'operator', 'password': 'pw1234567',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), before)

    def test_post_unicode_username_is_accepted(self):
        response = self.client.post(reverse('users'), {
            'username': 'vac_оператор', 'role': 'operator', 'password': 'pw1234567',
        })
        self.assertRedirects(response, reverse('users'))
        self.assertTrue(User.objects.filter(username='vac_оператор').exists())


class UserUpdateViewTests(AccountsTestMixin, TestCase):
    """Boss user edit: valid update changes username/password/company; missing
    or unknown user_id redirects without crashing or creating ghost users."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.boss)

    def test_valid_post_updates_username_password_and_company(self):
        response = self.client.post(reverse('user_update'), {
            'user_id': self.operator.pk, 'username': 'vac_operator_renamed',
            'new_password': 'newpass123', 'company_name': 'Vac Co',
        })
        self.assertRedirects(response, reverse('users'))
        self.operator.refresh_from_db()
        self.assertEqual(self.operator.username, 'vac_operator_renamed')
        self.assertTrue(self.operator.check_password('newpass123'))
        self.assertEqual(self.operator.company.name, 'Vac Co')

    def test_missing_user_id_redirects_without_creating_users(self):
        before = User.objects.count()
        response = self.client.post(reverse('user_update'), {
            'username': 'vac_ghosty', 'new_password': 'x', 'company_name': '',
        })
        self.assertRedirects(response, reverse('users'))
        self.assertEqual(User.objects.count(), before)

    def test_unknown_user_id_redirects_without_creating_ghost_user(self):
        before = User.objects.count()
        response = self.client.post(reverse('user_update'), {
            'user_id': 999999, 'username': 'vac_ghost', 'new_password': 'x',
            'company_name': '',
        })
        self.assertRedirects(response, reverse('users'))
        self.assertEqual(User.objects.count(), before)
        self.assertFalse(User.objects.filter(username='vac_ghost').exists())

    def test_whitespace_company_name_does_not_500(self):
        response = self.client.post(reverse('user_update'), {
            'user_id': self.operator.pk, 'username': self.operator.username,
            'new_password': '', 'company_name': '   ',
        })
        self.assertRedirects(response, reverse('users'))
        self.operator.refresh_from_db()
        # blank name must not create an empty Company
        self.assertIsNone(self.operator.company)
        self.assertFalse(Company.objects.filter(name='').exists())


class UserDeleteViewTests(AccountsTestMixin, TestCase):
    """Boss user deletion: operators go, bosses stay, bad pks and GET are safe."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.boss)

    def test_operator_without_data_is_deleted(self):
        victim = make_user('vac_victim', 'operator')
        self.client.post(reverse('user_delete', args=[victim.pk]))
        self.assertFalse(User.objects.filter(pk=victim.pk).exists())

    def test_operator_with_transactions_is_deactivated_not_deleted(self):
        victim = make_user('vac_victim', 'operator')
        Transaction.objects.create(
            type='income', payment_type='cash', description='', counterparty='x',
            operator=victim, date=timezone.now(), amount_uzs=Decimal('10'),
        )
        self.client.post(reverse('user_delete', args=[victim.pk]))
        victim.refresh_from_db()
        self.assertFalse(victim.is_active)
        self.assertEqual(Transaction.objects.filter(operator=victim).count(), 1)

    def test_boss_cannot_delete_self(self):
        self.client.post(reverse('user_delete', args=[self.boss.pk]))
        self.assertTrue(User.objects.filter(pk=self.boss.pk).exists())

    def test_boss_target_is_not_deleted(self):
        target = make_user('vac_boss2', 'boss')
        self.client.post(reverse('user_delete', args=[target.pk]))
        self.assertTrue(User.objects.filter(pk=target.pk).exists())

    def test_missing_pk_redirects_without_crash(self):
        response = self.client.post(reverse('user_delete', args=[999999]))
        self.assertRedirects(response, reverse('users'))

    def test_get_is_not_allowed_and_deletes_nothing(self):
        victim = make_user('vac_getvictim', 'operator')
        response = self.client.get(reverse('user_delete', args=[victim.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(User.objects.filter(pk=victim.pk).exists())


class HomeViewTests(TestCase):
    """Home routes each role to its own dashboard; anonymous goes to login."""

    def setUp(self):
        self.boss = make_user('vac_home_boss', 'boss')
        self.cashier = make_user('vac_home_cashier', 'cashier')
        self.operator = make_user('vac_home_operator', 'operator')

    def test_anon_redirects_to_login(self):
        response = self.client.get(reverse('home'))
        self.assertRedirects(response, reverse('login'))

    def test_each_role_redirects_to_its_dashboard(self):
        for user, dashboard in [
            (self.boss, 'boss_dashboard'),
            (self.cashier, 'cashier_dashboard'),
            (self.operator, 'operator_dashboard'),
        ]:
            with self.subTest(role=user.role):
                self.client.force_login(user)
                self.assertRedirects(self.client.get(reverse('home')), reverse(dashboard))


class AuthFlowTests(AccountsTestMixin, TestCase):
    """Login stores the chosen shift in the session; logout logs out and
    redirects to login."""

    def test_login_post_stores_shift_in_session(self):
        response = self.client.post(reverse('login'), {
            'username': 'vac_boss', 'password': PASSWORD, 'shift': '2',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_user(self.client), self.boss)
        self.assertEqual(self.client.session['shift'], '2')

    def test_login_without_shift_sets_no_shift_key(self):
        self.client.post(reverse('login'), {'username': 'vac_boss', 'password': PASSWORD})
        self.assertNotIn('shift', self.client.session)

    def test_logout_get_logs_out_and_redirects_to_login(self):
        self.client.force_login(self.boss)
        response = self.client.get(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)


class AccessMatrixTests(AccountsTestMixin, TestCase):
    """Smoke matrix: expected GET status for every named URL per role."""

    MATRIX = {
        'boss_dashboard': {'boss': 200, 'cashier': 403, 'operator': 403},
        'cashier_dashboard': {'boss': 403, 'cashier': 200, 'operator': 403},
        'operator_dashboard': {'boss': 403, 'cashier': 403, 'operator': 200},
        'finance_page': {'boss': 200, 'cashier': 200, 'operator': 302},
        'users': {'boss': 200, 'cashier': 403, 'operator': 403},
        'transaction_list': {'boss': 200, 'cashier': 403, 'operator': 403},
        'boss_reports': {'boss': 200, 'cashier': 403, 'operator': 403},
        'cashier_reports': {'boss': 403, 'cashier': 200, 'operator': 403},
        'operator_reports': {'boss': 403, 'cashier': 403, 'operator': 200},
        'expenses_list': {'boss': 403, 'cashier': 200, 'operator': 403},
        'incomes_list': {'boss': 403, 'cashier': 200, 'operator': 403},
        'operator_transactions': {'boss': 403, 'cashier': 403, 'operator': 200},
        'change_stat': {'boss': 405, 'cashier': 403, 'operator': 403},
    }

    def assert_roles(self, user, expected_by_url):
        self.client.force_login(user)
        for url_name, expected in self.MATRIX.items():
            with self.subTest(url=url_name, role=user.role):
                response = self.client.get(reverse(url_name))
                self.assertEqual(
                    response.status_code, expected[user.role],
                    f'{url_name} as {user.role}: got {response.status_code}, '
                    f'expected {expected[user.role]}',
                )

    def test_boss_role_statuses(self):
        self.assert_roles(self.boss, self.MATRIX)

    def test_cashier_role_statuses(self):
        self.assert_roles(self.cashier, self.MATRIX)

    def test_operator_role_statuses(self):
        self.assert_roles(self.operator, self.MATRIX)

    def test_anon_gets_login_redirect_everywhere(self):
        for url_name in self.MATRIX:
            with self.subTest(url=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 302, url_name)
                self.assertTrue(response.url.startswith(reverse('login')), url_name)
