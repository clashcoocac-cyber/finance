from datetime import timedelta
from decimal import Decimal

from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from finance.models import User, Transaction, DailyReport, Stat, StatTypes, Counterparty, Category

TODAY = None  # set per-test via helpers to keep every datetime tz-aware


def today():
    return timezone.now().date()


def dt_on(d, hour=12):
    """TZ-aware datetime on date d (USE_TZ is on; date__date lookups match)."""
    return timezone.make_aware(
        __import__('datetime').datetime.combine(d, __import__('datetime').time(hour, 0))
    )


def last_str_from(response):
    return [str(m) for m in get_messages(response.wsgi_request)][-1]


def make_tx(operator, **kw):
    """Transaction factory: valid defaults, overrides via kwargs."""
    params = dict(
        type='income',
        payment_type='cash',
        description='test',
        operator=operator,
        counterparty='klient',
        date=timezone.now(),
        amount_uzs=Decimal('1000'),
    )
    params.update(kw)
    return Transaction.objects.create(**params)


class OperatorTransactionsAccessTests(TestCase):
    """Operator's own transaction list: role access rules."""

    def setUp(self):
        self.url = reverse('operator_transactions')
        self.boss = User.objects.create_user(username='vtx_boss_acc', password='pass12345', role='boss')
        self.cashier = User.objects.create_user(username='vtx_cashier_acc', password='pass12345', role='cashier')
        self.operator = User.objects.create_user(username='vtx_op_acc', password='pass12345', role='operator')

    def test_operator_gets_200(self):
        self.client.force_login(self.operator)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_boss_gets_403(self):
        self.client.force_login(self.boss)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_cashier_gets_403(self):
        self.client.force_login(self.cashier)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_anon_redirected_to_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)


class OperatorTransactionsFilterTests(TestCase):
    """Filters and counters on the operator transaction page."""

    def setUp(self):
        self.url = reverse('operator_transactions')
        self.operator = User.objects.create_user(username='vtx_op_filt', password='pass12345', role='operator')
        self.client.force_login(self.operator)
        self.d = today()
        self.tx = make_tx(self.operator, counterparty='Ali Valiyev', comment='kontoraga xarid',
                          date=dt_on(self.d, 10))

    def test_q_matches_counterparty(self):
        response = self.client.get(self.url, {'q': 'ali vali'})
        self.assertContains(response, 'Ali Valiyev')

    def test_q_matches_description(self):
        response = self.client.get(self.url, {'q': 'xarid'})
        self.assertContains(response, 'kontoraga xarid')

    def test_q_no_match_empty_list(self):
        response = self.client.get(self.url, {'q': 'hech narsa topsin'})
        self.assertNotContains(response, 'Ali Valiyev')

    def test_counterparty_filter(self):
        response = self.client.get(self.url, {'counterparty': 'vali'})
        self.assertContains(response, 'Ali Valiyev')

    def test_payment_type_filter_excludes_other(self):
        response = self.client.get(self.url, {'payment_type': 'cash'})
        self.assertContains(response, 'Ali Valiyev')
        response = self.client.get(self.url, {'payment_type': 'terminal'})
        self.assertNotContains(response, 'Ali Valiyev')

    def test_from_to_window_inclusive(self):
        make_tx(self.operator, counterparty='kecha mijoz', date=dt_on(self.d - timedelta(days=1), 10))
        response = self.client.get(self.url, {
            'from': (self.d - timedelta(days=1)).strftime('%Y-%m-%d'),
            'to': self.d.strftime('%Y-%m-%d'),
        })
        self.assertContains(response, 'kecha mijoz')
        response = self.client.get(self.url, {
            'from': self.d.strftime('%Y-%m-%d'),
            'to': self.d.strftime('%Y-%m-%d'),
        })
        self.assertNotContains(response, 'kecha mijoz')

    def test_unreported_count_counts_only_unreported_of_report_date(self):
        make_tx(self.operator, date=dt_on(self.d, 11))  # same date, unreported
        make_tx(self.operator, date=dt_on(self.d - timedelta(days=1), 11))  # other date
        rep = DailyReport.objects.create(operator=self.operator, type='income', date=self.d, category='c')
        make_tx(self.operator, report=rep)  # same date but reported
        html = self.client.get(self.url, {'report_date': self.d.strftime('%Y-%m-%d')}).content.decode()
        self.assertIn('2 ta amaliyot hisobotga kiritilmagan', html)
        html = self.client.get(self.url, {'report_date': (self.d - timedelta(days=1)).strftime('%Y-%m-%d')}).content.decode()
        self.assertIn('1 ta amaliyot hisobotga kiritilmagan', html)


class OperatorTransactionsGarbageInputTests(TestCase):
    """Garbage GET params must fall back gracefully, never 500."""

    def setUp(self):
        self.url = reverse('operator_transactions')
        self.operator = User.objects.create_user(username='vtx_op_gar', password='pass12345', role='operator')
        self.client.force_login(self.operator)
        make_tx(self.operator)

    def test_garbage_from_falls_back_to_report_date(self):
        response = self.client.get(self.url, {'report_date': today().strftime('%Y-%m-%d'), 'from': 'haha'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'klient')

    def test_garbage_to_falls_back_to_report_date(self):
        response = self.client.get(self.url, {'report_date': today().strftime('%Y-%m-%d'), 'to': 'haha'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'klient')

    def test_garbage_report_date_falls_back_to_today(self):
        response = self.client.get(self.url, {'report_date': 'haha'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'klient')


class TransactionCreateViewTests(TestCase):
    """Add-transaction modal form POST: success, validation, role access."""

    def setUp(self):
        self.url = reverse('transaction_create')
        self.operator = User.objects.create_user(username='vtx_op_cr', password='pass12345', role='operator')
        self.cashier = User.objects.create_user(username='vtx_cashier_cr', password='pass12345', role='cashier')
        Counterparty.objects.create(name='Ali Vali', group='person')
        self.client.force_login(self.operator)

    def valid_data(self, **over):
        data = {
            'counterparty': 'Ali Vali', 'other_counterparty': '',
            'payment_type': 'cash', 'click': '',
            'amount_uzs': '150000', 'amount_usd': '', 'amount_rub': '', 'amount_eur': '',
            'comment': "do'kondan",
        }
        data.update(over)
        return data

    def test_valid_post_redirects_with_report_date_param(self):
        response = self.client.post(self.url + '?report_date=2026-09-10', self.valid_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('operator_transactions') + '?report_date=2026-09-10')
        tx = Transaction.objects.get()
        self.assertEqual(timezone.localtime(tx.date).strftime('%Y-%m-%d'), '2026-09-10')
        self.assertEqual(tx.operator, self.operator)

    def test_invalid_post_rerenders_with_errors_and_no_transaction(self):
        response = self.client.post(self.url, self.valid_data(payment_type='nope'))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    def test_empty_post_rerenders_no_transaction(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Transaction.objects.exists())

    def test_non_numeric_amount_rejected(self):
        self.client.post(self.url, self.valid_data(amount_uzs='abc'))
        self.assertFalse(Transaction.objects.exists())

    def test_negative_amount_does_not_crash(self):
        # characterization: the form has no min_value, so a negative amount is
        # accepted and stored — must never 500
        response = self.client.post(self.url, self.valid_data(amount_uzs='-500'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Transaction.objects.get().amount_uzs, Decimal('-500'))

    def test_huge_decimal_rejected_by_max_digits(self):
        self.client.post(self.url, self.valid_data(amount_uzs='1' * 14))
        self.assertFalse(Transaction.objects.exists())

    def test_whitespace_only_counterparty_rejected(self):
        self.client.post(self.url, self.valid_data(counterparty='__new__', other_counterparty='   '))
        self.assertFalse(Transaction.objects.exists())

    def test_apostrophe_and_unicode_names_accepted(self):
        self.client.post(self.url, self.valid_data(
            counterparty="__new__", other_counterparty="To'yxona 'Alpha' — Ўзбек"))
        tx = Transaction.objects.get()
        self.assertEqual(tx.counterparty, "To'yxona 'Alpha' — Ўзбек")

    def test_cashier_forbidden(self):
        self.client.force_login(self.cashier)
        response = self.client.post(self.url, self.valid_data())
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Transaction.objects.exists())


class BulkConfirmReportsTests(TestCase):
    """Boss confirms expenses only; cashier confirms income only."""

    def setUp(self):
        self.url = reverse('bulk_confirm_reports')
        self.boss = User.objects.create_user(username='vtx_boss_bc', password='pass12345', role='boss')
        self.cashier = User.objects.create_user(username='vtx_cashier_bc', password='pass12345', role='cashier')
        self.operator = User.objects.create_user(username='vtx_op_bc', password='pass12345', role='operator')
        d = today()
        self.income_rep = DailyReport.objects.create(operator=self.operator, type='income', date=d, category='c')
        self.expense_rep = DailyReport.objects.create(operator=self.operator, type='expense', date=d, category='c')
        self.xarajat_rep = DailyReport.objects.create(operator=self.operator, type='xarajat', date=d, category='c')

    def test_boss_confirms_expense_and_xarajat_never_income(self):
        self.client.force_login(self.boss)
        response = self.client.post(self.url, {
            'report_ids': [self.income_rep.pk, self.expense_rep.pk, self.xarajat_rep.pk]})
        self.assertEqual(response.status_code, 302)
        self.income_rep.refresh_from_db()
        self.expense_rep.refresh_from_db()
        self.xarajat_rep.refresh_from_db()
        self.assertFalse(self.income_rep.is_closed)
        self.assertTrue(self.expense_rep.is_closed)
        self.assertTrue(self.xarajat_rep.is_closed)

    def test_cashier_confirms_income_only(self):
        self.client.force_login(self.cashier)
        self.client.post(self.url, {
            'report_ids': [self.income_rep.pk, self.expense_rep.pk, self.xarajat_rep.pk]})
        self.income_rep.refresh_from_db()
        self.expense_rep.refresh_from_db()
        self.xarajat_rep.refresh_from_db()
        self.assertTrue(self.income_rep.is_closed)
        self.assertFalse(self.expense_rep.is_closed)
        self.assertFalse(self.xarajat_rep.is_closed)

    def test_operator_forbidden(self):
        self.client.force_login(self.operator)
        response = self.client.post(self.url, {'report_ids': [self.income_rep.pk]})
        self.assertEqual(response.status_code, 403)
        self.income_rep.refresh_from_db()
        self.assertFalse(self.income_rep.is_closed)

    def test_empty_report_ids_redirects_without_error(self):
        self.client.force_login(self.boss)
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('boss_reports'))

    def test_garbage_id_strings_no_crash(self):
        self.client.force_login(self.boss)
        response = self.client.post(self.url, {'report_ids': ['abc', f'{self.expense_rep.pk}', '999999']})
        self.assertEqual(response.status_code, 302)
        self.expense_rep.refresh_from_db()
        self.assertTrue(self.expense_rep.is_closed)

    def test_garbage_id_alone_does_nothing(self):
        self.client.force_login(self.boss)
        response = self.client.post(self.url, {'report_ids': ['abc']})
        self.assertEqual(response.status_code, 302)
        self.expense_rep.refresh_from_db()
        self.assertFalse(self.expense_rep.is_closed)

    def test_current_qs_preserved_in_redirect(self):
        self.client.force_login(self.cashier)
        response = self.client.post(self.url, {
            'report_ids': [self.income_rep.pk],
            'current_qs': 'from=2026-01-01&category=almashdi',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('from=2026-01-01', response.url)
        self.assertIn('category=almashdi', response.url)


class CloseCashRegisterTests(TestCase):
    """Kassani yopish: bundles one operator's unreported txs of one date."""

    def setUp(self):
        self.url = reverse('close_cash_register')
        self.operator = User.objects.create_user(username='vtx_op_ccr', password='pass12345', role='operator')
        self.client.force_login(self.operator)

    def close(self, date_str=None):
        q = f'?report_date={date_str}' if date_str else ''
        return self.client.post(self.url + q)

    def test_bundles_only_unreported_txs_of_selected_date_for_this_operator(self):
        d = today()
        make_tx(self.operator, date=dt_on(d, 10), amount_uzs=Decimal('1000'))
        make_tx(self.operator, date=dt_on(d, 11), amount_uzs=Decimal('2000'))
        other_op = User.objects.create_user(username='vtx_op_ccr2', password='pass12345', role='operator')
        make_tx(other_op, date=dt_on(d, 10), amount_uzs=Decimal('5000'))
        make_tx(self.operator, date=dt_on(d - timedelta(days=1), 10), amount_uzs=Decimal('5000'))
        # already reported tx on the same date: must NOT be bundled again
        old_rep = DailyReport.objects.create(
            operator=self.operator, type='income', date=d - timedelta(days=1), category='c')
        make_tx(self.operator, date=dt_on(d, 12), amount_uzs=Decimal('3000'), report=old_rep)
        self.close(d.strftime('%Y-%m-%d'))
        rep = DailyReport.objects.get(operator=self.operator, date=d)
        self.assertEqual(rep.total_uzs, Decimal('3000'))

    def mk_report(self, d):
        return DailyReport.objects.create(operator=self.operator, type='income', date=d, category='c')

    def test_second_close_adds_nothing(self):
        d = today()
        make_tx(self.operator, date=dt_on(d, 10), amount_uzs=Decimal('1000'))
        self.close(d.strftime('%Y-%m-%d'))
        make_tx(self.operator, date=dt_on(d, 11), amount_uzs=Decimal('2000'))
        self.close(d.strftime('%Y-%m-%d'))
        rep = DailyReport.objects.get(operator=self.operator, date=d)
        self.assertEqual(rep.total_uzs, Decimal('3000'))
        self.assertEqual(rep.transaction_set.count(), 2)

    def test_txs_get_report_assigned(self):
        d = today()
        tx = make_tx(self.operator, date=dt_on(d, 10))
        self.close(d.strftime('%Y-%m-%d'))
        tx.refresh_from_db()
        self.assertIsNotNone(tx.report)

    def test_totals_per_currency(self):
        d = today()
        make_tx(self.operator, date=dt_on(d, 10), amount_uzs=Decimal('1000.50'),
                amount_usd=Decimal('10'), amount_rub=Decimal('5'), amount_eur=Decimal('2'))
        self.close(d.strftime('%Y-%m-%d'))
        rep = DailyReport.objects.get(operator=self.operator, date=d)
        self.assertEqual(rep.total_uzs, Decimal('1000.50'))
        self.assertEqual(rep.total_usd, Decimal('10'))
        self.assertEqual(rep.total_rub, Decimal('5'))
        self.assertEqual(rep.total_eur, Decimal('2'))

    def test_detail_keys_by_payment_type_and_click(self):
        d = today()
        make_tx(self.operator, date=dt_on(d, 10), payment_type='click', click='click1', amount_uzs=Decimal('100'))
        make_tx(self.operator, date=dt_on(d, 11), payment_type='click', click='click2', amount_uzs=Decimal('200'))
        make_tx(self.operator, date=dt_on(d, 12), payment_type='terminal', amount_uzs=Decimal('300'))
        make_tx(self.operator, date=dt_on(d, 13), payment_type='bank', amount_uzs=Decimal('400'))
        self.close(d.strftime('%Y-%m-%d'))
        rep = DailyReport.objects.get(operator=self.operator, date=d)
        self.assertEqual(rep.uzs_detail, {'click1': 100, 'click2': 200, 'terminal': 300, 'bank': 400})

    def test_merges_with_preexisting_report_details(self):
        d = today()
        rep = DailyReport.objects.create(operator=self.operator, type='income', date=d, category='c',
                                         uzs_detail={'cash': 5})
        make_tx(self.operator, date=dt_on(d, 10), amount_uzs=Decimal('7'))
        self.close(d.strftime('%Y-%m-%d'))
        rep.refresh_from_db()
        self.assertEqual(rep.uzs_detail, {'cash': 12})

    def test_comment_copied_from_first_tx_with_one(self):
        d = today()
        make_tx(self.operator, date=dt_on(d, 10), comment=None)
        make_tx(self.operator, date=dt_on(d, 11), comment=' birinchi sharh')
        self.close(d.strftime('%Y-%m-%d'))
        rep = DailyReport.objects.get(operator=self.operator, date=d)
        self.assertEqual(rep.comment, ' birinchi sharh')

    def test_reclose_after_confirmation_reopens(self):
        d = today()
        make_tx(self.operator, date=dt_on(d, 10), amount_uzs=Decimal('1000'))
        self.close(d.strftime('%Y-%m-%d'))
        rep = DailyReport.objects.get(operator=self.operator, date=d)
        rep.is_closed = True
        rep.save()
        make_tx(self.operator, date=dt_on(d, 11), amount_uzs=Decimal('1000'))
        self.close(d.strftime('%Y-%m-%d'))
        rep.refresh_from_db()
        self.assertFalse(rep.is_closed)

    def test_no_unreported_redirects_without_report(self):
        d = today()
        response = self.close(d.strftime('%Y-%m-%d'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(DailyReport.objects.exists())

    def test_garbage_report_date_falls_back_to_today(self):
        d = today()
        make_tx(self.operator, date=dt_on(d, 10), amount_uzs=Decimal('1000'))
        self.close('haha')
        self.assertTrue(DailyReport.objects.filter(operator=self.operator, date=d).exists())

    def test_session_shift_stored_on_first_creation(self):
        d = today()
        session = self.client.session
        session['shift'] = 3
        session.save()
        make_tx(self.operator, date=dt_on(d, 10))
        self.close(d.strftime('%Y-%m-%d'))
        rep = DailyReport.objects.get(operator=self.operator, date=d)
        self.assertEqual(rep.operator_shift, 3)

    def test_another_operator_same_date_untouched(self):
        d = today()
        other = User.objects.create_user(username='vtx_op_ccr3', password='pass12345', role='operator')
        make_tx(self.operator, date=dt_on(d, 10), amount_uzs=Decimal('1000'))
        make_tx(other, date=dt_on(d, 10), amount_uzs=Decimal('9000'))
        self.close(d.strftime('%Y-%m-%d'))
        rep = DailyReport.objects.get(operator=self.operator, date=d)
        self.assertEqual(rep.total_uzs, Decimal('1000'))
        other_tx = Transaction.objects.get(operator=other)
        self.assertIsNone(other_tx.report)

    def test_missing_amount_fields_treated_as_zero(self):
        d = today()
        make_tx(self.operator, date=dt_on(d, 10), amount_uzs=Decimal('1000'), amount_usd=None)
        self.close(d.strftime('%Y-%m-%d'))
        rep = DailyReport.objects.get(operator=self.operator, date=d)
        self.assertEqual(rep.total_usd, Decimal('0'))


class ExpensesPageViewTests(TestCase):
    """Chiqim page: cashier-only, creates expense/xarajat reports."""

    def setUp(self):
        self.url = reverse('expenses_list')
        self.cashier = User.objects.create_user(username='vtx_cashier_exp', password='pass12345', role='cashier')
        self.boss = User.objects.create_user(username='vtx_boss_exp', password='pass12345', role='boss')
        self.operator = User.objects.create_user(username='vtx_op_exp', password='pass12345', role='operator')

    def test_cashier_gets_200(self):
        self.client.force_login(self.cashier)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_boss_403(self):
        self.client.force_login(self.boss)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_operator_403(self):
        self.client.force_login(self.operator)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def post_valid(self, date_str='2026-09-10'):
        return self.client.post(self.url + f'?date={date_str}', {
            'category': 'chikako zavod', 'new_category': '',
            'amount_uzs': '50000', 'amount_usd': '', 'amount_rub': '', 'amount_eur': '',
            'payment_type': 'cash', 'click': '', 'description': 'oylik',
            'exp_type': 'expense',
        })

    def test_valid_post_redirects_with_date_and_creates_report(self):
        self.client.force_login(self.cashier)
        response = self.post_valid()
        self.assertEqual(response.status_code, 302)
        self.assertIn('?date=2026-09-10', response.url)
        rep = DailyReport.objects.get(date='2026-09-10')
        self.assertEqual(rep.type, 'expense')
        self.assertFalse(rep.is_closed)

    def test_invalid_post_rerenders_with_error_no_report(self):
        self.client.force_login(self.cashier)
        response = self.client.post(self.url, {
            'category': '', 'amount_uzs': '100', 'payment_type': 'cash',
            'description': '', 'exp_type': 'expense',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DailyReport.objects.exists())
        self.assertTrue(any('tekshiring' in str(m) for m in get_messages(response.wsgi_request)))

    def test_listing_filtered_to_expense_types_of_date(self):
        self.client.force_login(self.cashier)
        d = today()
        DailyReport.objects.create(operator=self.cashier, type='expense', date=d, category='a')
        DailyReport.objects.create(operator=self.cashier, type='xarajat', date=d, category='b')
        DailyReport.objects.create(operator=self.cashier, type='income', date=d, category='c')
        DailyReport.objects.create(operator=self.cashier, type='expense', date=d - timedelta(days=1), category='d')
        html = self.client.get(self.url + f'?date={d.strftime("%Y-%m-%d")}').content.decode()
        self.assertIn('a', html)
        self.assertIn('b', html)
        self.assertNotIn('>c<', html)
        self.assertNotIn('>d<', html)


class IncomesPageViewTests(TestCase):
    """Kirim page: cashier-only, operator-scoped listing."""

    def setUp(self):
        self.url = reverse('incomes_list')
        self.cashier = User.objects.create_user(username='vtx_cashier_inc', password='pass12345', role='cashier')
        self.operator = User.objects.create_user(username='vtx_op_inc', password='pass12345', role='operator')
        Counterparty.objects.get_or_create(name='Almashdi', defaults={'group': 'income'})
        self.client.force_login(self.cashier)

    def post_valid(self, date_str='2026-09-10'):
        return self.client.post(self.url + f'?date={date_str}', {
            'counterparty': 'Almashdi', 'other_counterparty': '', 'purpose': 'foyda',
            'amount_uzs': '70000', 'amount_usd': '', 'amount_rub': '', 'amount_eur': '',
            'payment_type': 'cash', 'click': '', 'comment': '',
        })

    def test_valid_post_redirects_with_date_creates_income_report(self):
        response = self.post_valid()
        self.assertEqual(response.status_code, 302)
        self.assertIn('?date=2026-09-10', response.url)
        rep = DailyReport.objects.get(date='2026-09-10')
        self.assertEqual(rep.type, 'income')
        self.assertTrue(rep.is_closed)

    def test_invalid_post_rerenders_no_report(self):
        response = self.client.post(self.url, {
            'counterparty': '', 'payment_type': 'cash', 'comment': '',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DailyReport.objects.exists())

    def test_boss_403_per_mixin(self):
        # the code guards with CashierRequiredMixin — boss is not a cashier
        boss = User.objects.create_user(username='vtx_boss_inc', password='pass12345', role='boss')
        self.client.force_login(boss)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_listing_scoped_to_request_user_only(self):
        d = today()
        DailyReport.objects.create(operator=self.cashier, type='income', date=d, category='meniki')
        DailyReport.objects.create(operator=self.operator, type='income', date=d, category='boshqaniki')
        html = self.client.get(self.url + f'?date={d.strftime("%Y-%m-%d")}').content.decode()
        self.assertIn('meniki', html)
        self.assertNotIn('boshqaniki', html)


class TransactionListTests(TestCase):
    """Boss-only full transaction list: window, search, categories, totals."""

    def setUp(self):
        self.url = reverse('transaction_list')
        self.boss = User.objects.create_user(username='vtx_boss_tl', password='pass12345', role='boss')
        self.cashier = User.objects.create_user(username='vtx_cashier_tl', password='pass12345', role='cashier')
        self.operator = User.objects.create_user(username='vtx_op_tl', password='pass12345', role='operator')
        self.op2 = User.objects.create_user(username='vtx_op2_tl', password='pass12345', role='operator')
        self.client.force_login(self.boss)

    def test_boss_only(self):
        self.client.force_login(self.cashier)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.operator)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_default_window_last_7_days_includes_today(self):
        make_tx(self.operator, counterparty='bugungi', amount_uzs=Decimal('100'), date=dt_on(today(), 10))
        make_tx(self.operator, counterparty='eski', amount_uzs=Decimal('900'),
                date=dt_on(today() - timedelta(days=8), 10))
        response = self.client.get(self.url)
        self.assertContains(response, 'bugungi')
        self.assertNotContains(response, 'eski')

    def test_explicit_from_to_inclusive_of_to_day(self):
        d = today()
        make_tx(self.operator, counterparty='kechki', amount_uzs=Decimal('100'),
                date=dt_on(d, 23))
        make_tx(self.operator, counterparty='ertangi', amount_uzs=Decimal('100'),
                date=dt_on(d + timedelta(days=1), 10))
        response = self.client.get(self.url, {
            'from': d.strftime('%Y-%m-%d'), 'to': d.strftime('%Y-%m-%d')})
        self.assertContains(response, 'kechki')
        self.assertNotContains(response, 'ertangi')

    def test_q_matches_operator_username(self):
        d = today()
        make_tx(self.operator, counterparty='mijoz_a', date=dt_on(d, 10))
        make_tx(self.op2, counterparty='mijoz_b', date=dt_on(d, 10))
        response = self.client.get(self.url, {'q': 'vtx_op2_tl'})
        self.assertContains(response, 'mijoz_b')
        self.assertNotContains(response, 'mijoz_a')

    def test_q_matches_company_name(self):
        from finance.models import Company
        company = Company.objects.create(name='Chikako Zavod')
        self.operator.company = company
        self.operator.save()
        d = today()
        make_tx(self.operator, counterparty='mijoz_a', date=dt_on(d, 10))
        make_tx(self.op2, counterparty='mijoz_b', date=dt_on(d, 10))
        response = self.client.get(self.url, {'q': 'chikako'})
        self.assertContains(response, 'mijoz_a')
        self.assertNotContains(response, 'mijoz_b')

    def test_q_matches_report_category(self):
        d = today()
        rep = DailyReport.objects.create(operator=self.operator, type='expense', date=d, category='elektr')
        make_tx(self.operator, counterparty='mijoz_a', report=rep, date=dt_on(d, 10))
        make_tx(self.op2, counterparty='mijoz_b', date=dt_on(d, 10))
        response = self.client.get(self.url, {'q': 'elektr'})
        self.assertContains(response, 'mijoz_a')
        self.assertNotContains(response, 'mijoz_b')

    def test_multi_category_filter(self):
        d = today()
        rep1 = DailyReport.objects.create(operator=self.operator, type='expense', date=d, category='elektr')
        rep2 = DailyReport.objects.create(operator=self.operator, type='expense', date=d, category='suv')
        rep3 = DailyReport.objects.create(operator=self.operator, type='expense', date=d, category='gaz')
        make_tx(self.operator, counterparty='elektr tx', report=rep1, date=dt_on(d, 10))
        make_tx(self.operator, counterparty='suv tx', report=rep2, date=dt_on(d, 11))
        make_tx(self.operator, counterparty='gaz tx', report=rep3, date=dt_on(d, 12))
        response = self.client.get(self.url, {'category': ['elektr', 'suv']})
        self.assertContains(response, 'elektr tx')
        self.assertContains(response, 'suv tx')
        self.assertNotContains(response, 'gaz tx')

    def test_totals_reflect_filtered_set(self):
        d = today()
        make_tx(self.operator, counterparty='mijoz_a', amount_uzs=Decimal('100'), amount_usd=Decimal('5'),
                date=dt_on(d, 10))
        make_tx(self.op2, counterparty='mijoz_b', amount_uzs=Decimal('700'), amount_usd=Decimal('50'),
                date=dt_on(d, 10))
        response = self.client.get(self.url, {'q': 'mijoz_a'})
        self.assertEqual(response.context['total_uzs'], Decimal('100'))
        self.assertEqual(response.context['total_usd'], Decimal('5'))

    def test_empty_result_totals_zero(self):
        d = today()
        make_tx(self.operator, counterparty='mijoz_a', date=dt_on(d, 10))
        response = self.client.get(self.url, {'q': 'nomatch'})
        self.assertEqual(response.context['total_uzs'], 0)
        self.assertEqual(response.context['total_usd'], 0)

    def test_garbage_dates_500_bug(self):
        d = today()
        make_tx(self.operator, counterparty='mijoz_a', date=dt_on(d, 10))
        response = self.client.get(self.url, {'from': 'haha'})
        self.assertEqual(response.status_code, 200)


class ChangeStatViewTests(TestCase):
    """Boss manual stat correction: default_* = raw confirmed - posted."""

    def setUp(self):
        self.url = reverse('change_stat')
        self.boss = User.objects.create_user(username='vtx_boss_cs', password='pass12345', role='boss')
        self.cashier = User.objects.create_user(username='vtx_cashier_cs', password='pass12345', role='cashier')
        self.operator = User.objects.create_user(username='vtx_op_cs', password='pass12345', role='operator')
        d = today()
        rep = DailyReport.objects.create(operator=self.operator, type='income', date=d, category='c', is_closed=True)
        self.cash_tx = make_tx(self.operator, report=rep, payment_type='cash',
                               amount_uzs=Decimal('1000'), amount_usd=Decimal('10'),
                               amount_rub=Decimal('5'), amount_eur=Decimal('1'),
                               date=dt_on(d, 10))
        self.client.force_login(self.boss)

    def test_boss_only(self):
        self.client.force_login(self.cashier)
        response = self.client.post(self.url, {'stat_type': 'income', 'total_uzs': '100'})
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.operator)
        response = self.client.post(self.url, {'stat_type': 'income', 'total_uzs': '100'})
        self.assertEqual(response.status_code, 403)

    def test_posting_total_sets_default_so_stats_show_posted(self):
        response = self.client.post(self.url, {
            'stat_type': 'income', 'total_uzs': '400', 'total_usd': '4',
            'total_rub': '2', 'total_eur': '1',
        })
        self.assertEqual(response.status_code, 302)
        stat = Stat.objects.get(type=StatTypes.INCOME)
        self.assertEqual(stat.default_uzs, Decimal('600'))
        self.assertEqual(stat.default_usd, Decimal('6'))
        self.assertEqual(stat.default_rub, Decimal('3'))
        self.assertEqual(stat.default_eur, Decimal('0'))
        from finance.views.helpers import compute_money_stats
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['income'].total_uzs, Decimal('400'))
        self.assertEqual(stats['confirmed']['income'].total_usd, Decimal('4'))

    def test_each_stat_type_independent(self):
        # raw confirmed: income 1000 uzs, expense 0 -> diff 1000
        self.client.post(self.url, {'stat_type': 'income', 'total_uzs': '100'})
        self.client.post(self.url, {'stat_type': 'expense', 'total_uzs': '50'})
        self.client.post(self.url, {'stat_type': 'diff', 'total_uzs': '25'})
        self.assertEqual(Stat.objects.get(type=StatTypes.INCOME).default_uzs, Decimal('900'))
        self.assertEqual(Stat.objects.get(type=StatTypes.EXPENSE).default_uzs, Decimal('-50'))
        self.assertEqual(Stat.objects.get(type=StatTypes.BALANCE).default_uzs, Decimal('975'))

    def test_decimal_input_kept_to_cents(self):
        response = self.client.post(self.url, {'stat_type': 'income', 'total_uzs': '123.45'})
        self.assertEqual(response.status_code, 302)
        stat = Stat.objects.get(type=StatTypes.INCOME)
        self.assertEqual(stat.default_uzs, Decimal('876.55'))

    def test_garbage_input_does_not_500(self):
        response = self.client.post(self.url, {'stat_type': 'income', 'total_uzs': 'abc'})
        self.assertEqual(response.status_code, 302)

    def test_empty_post_does_not_500(self):
        response = self.client.post(self.url, {})
        self.assertEqual(response.status_code, 302)
