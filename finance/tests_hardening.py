"""Regression tests for the production-hardening pass: report recalculation
with several transactions on one payment channel, boss edit validation,
user deactivation instead of cascade delete, and garbage-tolerant POSTs."""
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from finance.forms import TransactionEditForm, UserUpdateForm
from finance.models import Company, DailyReport, Stat, Transaction, User


def make_user(username, role):
    return User.objects.create_user(username=username, password='pass12345', role=role)


def make_tx(operator, report=None, **kw):
    params = dict(type='income', payment_type='cash', description='', counterparty='x',
                  operator=operator, date=timezone.now(), report=report, amount_uzs=Decimal('1000'))
    params.update(kw)
    return Transaction.objects.create(**params)


class ReportRecalcTests(TestCase):
    def setUp(self):
        self.op = make_user('hard_op', 'operator')
        self.report = DailyReport.objects.create(type='income', date=timezone.localdate(),
                                                 operator=self.op, category='c')

    def test_two_transactions_same_channel_accumulate(self):
        # used to raise TypeError: float + Decimal on the second save
        make_tx(self.op, self.report, amount_uzs=Decimal('100.50'), amount_usd=Decimal('1'))
        make_tx(self.op, self.report, amount_uzs=Decimal('200.25'), amount_usd=None)
        self.report.refresh_from_db()
        self.assertEqual(self.report.total_uzs, Decimal('300.75'))
        self.assertEqual(self.report.total_usd, Decimal('1'))
        self.assertEqual(self.report.uzs_detail, {'cash': 300.75})
        self.assertEqual(self.report.usd_detail, {'cash': 1.0})

    def test_click_keyed_by_card(self):
        make_tx(self.op, self.report, payment_type='click', click='click1', amount_uzs=Decimal('5'))
        make_tx(self.op, self.report, payment_type='click', click='click2', amount_uzs=Decimal('7'))
        make_tx(self.op, self.report, payment_type='click', click='click1', amount_uzs=Decimal('1'))
        self.report.refresh_from_db()
        self.assertEqual(self.report.uzs_detail, {'click1': 6.0, 'click2': 7.0})

    def test_moving_transaction_between_reports_recalcs_both(self):
        other = DailyReport.objects.create(type='income', date=timezone.localdate(),
                                           operator=self.op, category='c')
        tx = make_tx(self.op, self.report, amount_uzs=Decimal('10'))
        tx.report = other
        tx.save()
        self.report.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(self.report.total_uzs, Decimal('0'))
        self.assertIsNone(self.report.uzs_detail)
        self.assertEqual(other.total_uzs, Decimal('10'))

    def test_delete_recalcs(self):
        a = make_tx(self.op, self.report, amount_uzs=Decimal('10'))
        make_tx(self.op, self.report, amount_uzs=Decimal('5'))
        a.delete()
        self.report.refresh_from_db()
        self.assertEqual(self.report.total_uzs, Decimal('5'))


class TransactionEditFormTests(TestCase):
    def test_click_requires_card(self):
        form = TransactionEditForm({'payment_type': 'click', 'click': '', 'amount_uzs': '1'})
        self.assertFalse(form.is_valid())
        self.assertIn('click', form.errors)

    def test_non_click_drops_card(self):
        form = TransactionEditForm({'payment_type': 'cash', 'click': 'click1', 'amount_uzs': '1'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data['click'])

    def test_garbage_amount_is_error(self):
        form = TransactionEditForm({'payment_type': 'cash', 'amount_uzs': 'abc'})
        self.assertFalse(form.is_valid())
        self.assertIn('amount_uzs', form.errors)


class UserUpdateFormTests(TestCase):
    def test_blank_company_clears_without_creating_empty_company(self):
        user = make_user('hard_upd', 'operator')
        user.company = Company.objects.create(name='Old'); user.save()
        form = UserUpdateForm({'user_id': user.pk, 'username': 'hard_upd', 'company_name': '  '}, instance=user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        self.assertIsNone(user.company)
        self.assertFalse(Company.objects.filter(name='').exists())


class BossPostHardeningTests(TestCase):
    def setUp(self):
        self.boss = make_user('hard_boss', 'boss')
        self.client.force_login(self.boss)

    def test_user_update_bad_id_redirects(self):
        for bad in ('abc', '', '99999'):
            response = self.client.post(reverse('user_update'), {'user_id': bad, 'username': 'x'})
            self.assertRedirects(response, reverse('users'))

    def test_user_update_invalid_form_redirects_with_message(self):
        other = make_user('hard_other', 'operator')
        response = self.client.post(reverse('user_update'), {
            'user_id': other.pk, 'username': self.boss.username,  # duplicate username
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(any('Formani tekshiring' in str(m) for m in response.context['messages']))

    def test_change_stat_rejects_bad_type_and_amount(self):
        self.client.post(reverse('change_stat'), {'stat_type': 'nope', 'total_uzs': '1'})
        self.assertFalse(Stat.objects.filter(type='nope').exists())
        response = self.client.post(reverse('change_stat'), {'stat_type': 'income', 'total_uzs': 'abc'})
        self.assertRedirects(response, reverse('boss_dashboard'))
        self.assertEqual(Stat.objects.filter(type='income').exclude(default_uzs=0).count(), 0)

    def test_change_stat_accepts_spaces_and_comma(self):
        self.client.post(reverse('change_stat'), {'stat_type': 'income', 'total_uzs': '1 000,50'})
        self.assertEqual(Stat.objects.get(type='income').default_uzs, Decimal('-1000.50'))

    def test_bulk_confirm_ignores_non_numeric_ids(self):
        op = make_user('hard_op2', 'operator')
        report = DailyReport.objects.create(type='expense', date=timezone.localdate(), operator=op, category='c')
        response = self.client.post(reverse('bulk_confirm_reports'), {'report_ids': ['abc', str(report.pk)]})
        self.assertEqual(response.status_code, 302)
        report.refresh_from_db()
        self.assertTrue(report.is_closed)

    def test_transaction_delete_removes_empty_report(self):
        op = make_user('hard_op3', 'operator')
        report = DailyReport.objects.create(type='income', date=timezone.localdate(), operator=op, category='c')
        tx = make_tx(op, report)
        self.client.post(reverse('transaction_delete', args=[tx.pk]))
        self.assertFalse(Transaction.objects.filter(pk=tx.pk).exists())
        self.assertFalse(DailyReport.objects.filter(pk=report.pk).exists())

    def test_transaction_delete_keeps_report_with_others(self):
        op = make_user('hard_op4', 'operator')
        report = DailyReport.objects.create(type='income', date=timezone.localdate(), operator=op, category='c')
        tx = make_tx(op, report, amount_uzs=Decimal('10'))
        make_tx(op, report, amount_uzs=Decimal('5'))
        self.client.post(reverse('transaction_delete', args=[tx.pk]))
        report.refresh_from_db()
        self.assertEqual(report.total_uzs, Decimal('5'))
