"""Regression checks for the UI review fixes: every page renders for its role,
garbage date params fall back instead of 500, failed finance-page submits keep
typed values, and lists paginate."""
from datetime import date

from django.test import TestCase
from django.urls import reverse

from finance.models import User, DailyReport, Transaction, Category, Counterparty


class RenderSmokeTests(TestCase):
    ROLE_URLS = {
        'boss': ['boss_dashboard', 'finance_page', 'boss_reports', 'transaction_list', 'users'],
        'cashier': ['cashier_dashboard', 'finance_page', 'cashier_reports', 'incomes_list', 'expenses_list'],
        'operator': ['operator_dashboard', 'operator_transactions', 'operator_reports'],
    }

    def setUp(self):
        self.users = {r: User.objects.create_user(username=f'u_{r}', password='x', role=r) for r in self.ROLE_URLS}
        Category.objects.create(name='ijara', group='expense')
        Counterparty.objects.create(name='Almashdi', group='income')
        for i in range(3):
            tx = Transaction.objects.create(
                type='income', amount_uzs=1000 + i, payment_type='cash', description='',
                operator=self.users['operator'], counterparty='Ali', date=f'2026-09-0{i + 1} 10:00',
            )
            rep = DailyReport.objects.create(
                type='income', date=date(2026, 9, i + 1), operator=self.users['operator'],
                category='Ali', total_uzs=1000 + i, uzs_detail={'cash': 1000 + i},
            )
            tx.report = rep
            tx.save()

    def test_every_page_renders_for_its_role(self):
        for role, names in self.ROLE_URLS.items():
            self.client.force_login(self.users[role])
            for name in names:
                for qs in ('', '?from=2026-09-01&to=2026-09-30', '?from=garbage&to=2026-02-31&date=x&report_date=nope&page=999'):
                    with self.subTest(role=role, url=name, qs=qs):
                        response = self.client.get(reverse(name) + qs)
                        self.assertEqual(response.status_code, 200)

    def test_edit_transaction_page_renders_decimal_amount(self):
        tx = Transaction.objects.first()
        tx.amount_usd = '12.50'
        tx.save()
        self.client.force_login(self.users['boss'])
        response = self.client.get(reverse('transaction', args=[tx.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="12.50"')

    def test_login_page_renders(self):
        response = self.client.get(reverse('login'))
        self.assertContains(response, 'autocomplete="current-password"')

    def test_reports_paginate(self):
        self.client.force_login(self.users['boss'])
        response = self.client.get(reverse('boss_reports') + '?from=2026-09-01&to=2026-09-30')
        self.assertEqual(response.context['page_obj'].paginator.count, 3)
        self.assertEqual(len(response.context['reports']), 3)


class FinancePageFailedSubmitTests(TestCase):
    def setUp(self):
        self.cashier = User.objects.create_user(username='c1', password='x', role='cashier')
        Counterparty.objects.create(name='Almashdi', group='income')
        self.client.force_login(self.cashier)

    def test_failed_income_keeps_values_and_shows_field_errors(self):
        response = self.client.post(reverse('finance_page'), {
            'kind': 'income', 'counterparty': '__new__', 'other_counterparty': '',
            'purpose': 'foyda', 'amount_usd': '250.75', 'payment_type': 'terminal',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['failed_modal'], 'income')
        self.assertContains(response, 'value="250.75"')
        self.assertContains(response, 'Yangi manba nomi:')
        # flash rendered once (base layout), not duplicated by the page
        self.assertEqual(response.content.decode().count('Formani tekshiring.'), 1)

    def test_unknown_kind_redirects(self):
        response = self.client.post(reverse('finance_page'), {'kind': 'bogus'})
        self.assertRedirects(response, reverse('finance_page'))


class DateParamTests(TestCase):
    def test_date_param(self):
        from finance.views.helpers import date_param
        self.assertEqual(date_param('2026-09-13', 'd'), '2026-09-13')
        self.assertEqual(date_param(' 2026-09-13 ', 'd'), '2026-09-13')
        for bad in (None, '', '  ', 'garbage', '2026-02-31', '12.5', '2026-09-13T00:00'):
            self.assertEqual(date_param(bad, 'd'), 'd', bad)
