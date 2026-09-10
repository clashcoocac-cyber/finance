from django.test import TestCase
from django.urls import reverse

from finance.forms import ExpenseForm
from finance.models import User, DailyReport, Transaction, Category, Counterparty


class FinancePageAccessTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user(username='boss_fp', password='pass12345', role='boss')
        self.cashier = User.objects.create_user(username='cashier_fp', password='pass12345', role='cashier')
        self.operator = User.objects.create_user(username='operator_fp', password='pass12345', role='operator')

    def test_boss_sees_finance_page(self):
        self.client.force_login(self.boss)
        response = self.client.get(reverse('finance_page'))
        self.assertEqual(response.status_code, 200)

    def test_cashier_sees_finance_page(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse('finance_page'))
        self.assertEqual(response.status_code, 200)

    def test_operator_forbidden(self):
        self.client.force_login(self.operator)
        response = self.client.get(reverse('finance_page'))
        self.assertEqual(response.status_code, 302)


class FinancePageIncomePostTests(TestCase):
    def setUp(self):
        self.cashier = User.objects.create_user(username='cashier_fi', password='pass12345', role='cashier')
        Counterparty.objects.get_or_create(name='Almashdi', defaults={'group': 'income'})
        Category.objects.get_or_create(name='chikako zavod', defaults={'group': 'expense'})

    def test_noncash_income_post_creates_transaction(self):
        self.client.force_login(self.cashier)
        response = self.client.post(reverse('finance_page'), {
            'kind': 'income', 'counterparty': 'Almashdi', 'purpose': 'foyda',
            'amount_usd': '100', 'payment_type': 'terminal',
        })
        self.assertEqual(response.status_code, 302)
        tx = Transaction.objects.filter(type='income', payment_type='terminal').latest('pk')
        self.assertEqual(tx.amount_usd, 100)
        self.assertEqual(tx.report.category, 'Almashdi')
        self.assertEqual(tx.report.desc, 'Maqsad: foyda')

    def test_noncash_expense_post_creates_transaction(self):
        self.client.force_login(self.cashier)
        response = self.client.post(reverse('finance_page'), {
            'kind': 'expense', 'category': 'chikako zavod',
            'amount_uzs': '50000', 'payment_type': 'bank', 'exp_type': 'expense',
            'description': '',
        })
        self.assertEqual(response.status_code, 302)
        tx = Transaction.objects.filter(type='expense', payment_type='bank').latest('pk')
        self.assertEqual(tx.amount_uzs, 50000)
        self.assertEqual(tx.report.category, 'chikako zavod')
