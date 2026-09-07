from decimal import Decimal
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from finance.models import User, Transaction, DailyReport, Category, Counterparty
from finance.forms import ExpenseForm, TransactionFrom


class DataMigrationBackfillTests(TestCase):
    """The migration already ran when the test DB was built from migrations,
    so this just asserts the expected end state — it does not re-run RunPython."""

    def test_seed_categories_exist_with_correct_group(self):
        self.assertTrue(Category.objects.filter(name__iexact='chikako zavod', group='expense').exists())
        self.assertTrue(Category.objects.filter(name__iexact='mssb xarajat', group='xarajat').exists())

    def test_seed_counterparties_exist(self):
        self.assertTrue(Counterparty.objects.filter(name__iexact='Kenjayev Jasur').exists())


class BulkConfirmReportsViewTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user(username='boss_bc', password='pass12345', role='boss')
        self.cashier = User.objects.create_user(username='cashier_bc', password='pass12345', role='cashier')
        self.operator = User.objects.create_user(username='operator_bc', password='pass12345', role='operator')
        today = timezone.now().date()
        self.expense_report = DailyReport.objects.create(
            operator=self.operator, type='expense', date=today, category='test', is_closed=False,
        )
        self.income_report = DailyReport.objects.create(
            operator=self.operator, type='income', date=today, is_closed=False,
        )

    def test_boss_confirms_expense_reports(self):
        self.client.force_login(self.boss)
        response = self.client.post(reverse('bulk_confirm_reports'), {'report_ids': [self.expense_report.pk]})
        self.expense_report.refresh_from_db()
        self.assertTrue(self.expense_report.is_closed)
        self.assertEqual(response.status_code, 302)

    def test_boss_cannot_confirm_income_reports(self):
        self.client.force_login(self.boss)
        self.client.post(reverse('bulk_confirm_reports'), {'report_ids': [self.income_report.pk]})
        self.income_report.refresh_from_db()
        self.assertFalse(self.income_report.is_closed)

    def test_cashier_confirms_income_reports(self):
        self.client.force_login(self.cashier)
        self.client.post(reverse('bulk_confirm_reports'), {'report_ids': [self.income_report.pk]})
        self.income_report.refresh_from_db()
        self.assertTrue(self.income_report.is_closed)

    def test_operator_forbidden(self):
        self.client.force_login(self.operator)
        response = self.client.post(reverse('bulk_confirm_reports'), {'report_ids': [self.income_report.pk]})
        self.assertEqual(response.status_code, 403)

    def test_redirect_preserves_query_string(self):
        self.client.force_login(self.cashier)
        response = self.client.post(reverse('bulk_confirm_reports'), {
            'report_ids': [self.income_report.pk],
            'current_qs': 'from=2026-01-01&to=2026-01-31&category=almashdi',
        })
        self.assertIn('from=2026-01-01', response.url)
        self.assertIn('category=almashdi', response.url)


class ExpenseFormCategoryTests(TestCase):
    def setUp(self):
        self.cashier = User.objects.create_user(username='cashier_ef', password='pass12345', role='cashier')

    def test_new_category_persists_for_next_form(self):
        form = ExpenseForm(data={
            'category': '__new__', 'new_category': 'Elektr energiya',
            'amount_uzs': '150000', 'payment_type': 'cash',
            'description': "Oylik to'lov", 'exp_type': 'expense',
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save(operator=self.cashier, date='2026-09-07')

        self.assertTrue(Category.objects.filter(name__iexact='elektr energiya', group='expense').exists())

        next_form = ExpenseForm()
        choice_values = dict(next_form.fields['category'].choices)
        self.assertIn('elektr energiya', choice_values)

    def test_existing_category_selection_does_not_duplicate(self):
        Category.objects.get_or_create(name='chikako zavod', defaults={'group': 'expense'})
        form = ExpenseForm(data={
            'category': 'chikako zavod', 'amount_uzs': '10000', 'payment_type': 'cash',
            'description': '', 'exp_type': 'expense',
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save(operator=self.cashier, date='2026-09-07')
        self.assertEqual(Category.objects.filter(name__iexact='chikako zavod').count(), 1)


class OperatorCounterpartyFormTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='op_cf', password='pass12345', role='operator')

    def test_new_counterparty_persists_for_next_form(self):
        form = TransactionFrom(data={
            'counterparty': '__new__', 'other_counterparty': 'Yangi Aka',
            'amount_uzs': '50000', 'payment_type': 'cash',
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save(operator=self.operator, date='2026-09-07')

        self.assertTrue(Counterparty.objects.filter(name__iexact='yangi aka').exists())

        next_form = TransactionFrom()
        choice_values = dict(next_form.fields['counterparty'].choices)
        self.assertIn('Yangi Aka', choice_values)
