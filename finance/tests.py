from django.test import TestCase
from django.utils import timezone
from finance.models import User, Transaction, DailyReport, Category, Counterparty


class DataMigrationBackfillTests(TestCase):
    """The migration already ran when the test DB was built from migrations,
    so this just asserts the expected end state — it does not re-run RunPython."""

    def test_seed_categories_exist_with_correct_group(self):
        self.assertTrue(Category.objects.filter(name__iexact='chikako zavod', group='expense').exists())
        self.assertTrue(Category.objects.filter(name__iexact='mssb xarajat', group='xarajat').exists())

    def test_seed_counterparties_exist(self):
        self.assertTrue(Counterparty.objects.filter(name__iexact='Kenjayev Jasur').exists())
