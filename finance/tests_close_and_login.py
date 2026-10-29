from decimal import Decimal

from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from finance.models import Company, DailyReport, Transaction, User


class CloseCashRegisterTotalsTests(TestCase):
    def setUp(self):
        company = Company.objects.create(name="C")
        self.operator = User.objects.create_user("op", password="pw-op-12345", role="operator", company=company)
        self.client = Client()
        self.client.force_login(self.operator)
        self.today = timezone.localdate()

    def add(self, usd=None, uzs=None, payment="cash"):
        return Transaction.objects.create(
            date=timezone.now(), type="income", payment_type=payment, description="d", operator=self.operator,
            counterparty="x", amount_usd=None if usd is None else Decimal(usd),
            amount_uzs=None if uzs is None else Decimal(uzs))

    def close(self):
        return self.client.post(f"/cash-register/close/?report_date={self.today}")

    def report(self):
        return DailyReport.objects.get(operator=self.operator, date=self.today)

    def test_cents_survive_closing_the_register_twice_in_one_day(self):
        self.add(usd="10.50"); self.close()
        self.add(usd="5.00"); self.close()
        report = self.report()
        self.assertEqual(report.total_usd, Decimal("15.50"))
        self.assertAlmostEqual(report.usd_detail["cash"], 15.5)

    def test_pressing_close_twice_never_counts_a_transaction_twice(self):
        self.add(uzs="100000")
        self.close(); self.close()
        self.assertEqual(self.report().total_uzs, Decimal("100000"))
        self.assertEqual(DailyReport.objects.filter(operator=self.operator).count(), 1)

    def test_details_split_by_payment_type_and_match_the_total(self):
        self.add(uzs="1000", payment="cash"); self.add(uzs="2500", payment="terminal")
        self.close()
        report = self.report()
        self.assertEqual(report.total_uzs, Decimal("3500"))
        self.assertEqual({k: int(v) for k, v in report.uzs_detail.items()}, {"cash": 1000, "terminal": 2500})
        self.assertEqual(Transaction.objects.filter(report=report).count(), 2)

    def test_a_closed_report_is_reopened_when_new_transactions_are_added(self):
        self.add(uzs="1000"); self.close()
        DailyReport.objects.filter(pk=self.report().pk).update(is_closed=True)
        self.add(uzs="500"); self.close()
        report = self.report()
        self.assertFalse(report.is_closed)
        self.assertEqual(report.total_uzs, Decimal("1500"))


class LoginThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user("cashier1", password="right-pass-123", role="cashier")

    def attempt(self, password, username="cashier1"):
        return Client().post("/login/", {"username": username, "password": password})

    def test_five_wrong_passwords_lock_the_username_even_for_the_right_one(self):
        for _ in range(5):
            self.assertEqual(self.attempt("wrong").status_code, 200)
        self.assertEqual(self.attempt("right-pass-123").status_code, 429)

    def test_a_correct_login_resets_the_counter(self):
        for _ in range(4):
            self.attempt("wrong")
        self.assertEqual(self.attempt("right-pass-123").status_code, 302)
        for _ in range(4):
            self.assertEqual(self.attempt("wrong").status_code, 200)

    def test_other_usernames_are_not_locked_by_someone_elses_failures(self):
        User.objects.create_user("cashier2", password="other-pass-123", role="cashier")
        for _ in range(5):
            self.attempt("wrong")
        self.assertEqual(self.attempt("other-pass-123", username="cashier2").status_code, 302)
