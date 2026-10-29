import re
from datetime import date
from pathlib import Path

from django.test import Client, TestCase

from finance.models import Company, DailyReport, User


class PolishTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user("boss", password="pw-boss-12345", role="boss")
        self.cashier = User.objects.create_user("cash", password="pw-cash-12345", role="cashier")
        self.operator = User.objects.create_user("op", password="pw-op-12345", role="operator")  # no company
        DailyReport.objects.create(type="income", date=date(2026, 10, 4), operator=self.operator, category="x",
                                   total_uzs=1000, is_closed=True)

    def get(self, user, url):
        client = Client()
        client.force_login(user)
        return client.get(url)

    def test_dates_are_dd_mm_yyyy_everywhere(self):
        for user, url in ((self.boss, "/reports/boss/?from=2026-10-01&to=2026-10-31"),
                          (self.cashier, "/reports/cashier/?from=2026-10-01&to=2026-10-31"),
                          (self.boss, "/dashboard/boss/")):
            html = self.get(user, url).content.decode()
            self.assertNotRegex(html, r"\b\d{2}/\d{2}/\d{4}\b", url)
        self.assertIn("04.10.2026", self.get(self.boss, "/reports/boss/?from=2026-10-01&to=2026-10-31").content.decode())

    def test_single_date_inputs_use_the_uzbek_picker_not_the_browsers_date_input(self):
        for user, url in ((self.cashier, "/expenses/"), (self.cashier, "/incomes/"),
                          (self.operator, "/my-transactions/")):
            html = self.get(user, url).content.decode()
            self.assertIn("data-uz-date", html, url)
            self.assertNotIn('type="date"', html, url)

    def test_month_picker_is_a_select_with_uzbek_month_names(self):
        html = self.get(self.boss, "/dashboard/boss/?from=2026-10-01&to=2026-10-31").content.decode()
        self.assertIn('<select class="finance-month-picker', html)
        self.assertNotIn('type="month"', html)
        self.assertIn("'Oktabr'", html)
        self.assertIn('data-selected="2026-10"', html)

    def test_range_picker_shows_dd_mm_yyyy(self):
        html = self.get(self.boss, "/reports/boss/").content.decode()
        self.assertIn("altFormat: 'd.m.Y'", html)

    def test_an_empty_company_shows_a_dash(self):
        html = self.get(self.boss, "/reports/boss/?from=2026-10-01&to=2026-10-31").content.decode()
        self.assertRegex(html, r">\s*-\s*<")

    def test_money_values_never_wrap_or_clip(self):
        css = Path("static/sneat/finance.css").read_text()
        block = re.search(r"\.finance-money-value \{(.*?)\}", css, re.S).group(1)
        self.assertIn("white-space: nowrap", block)
        self.assertNotIn("text-overflow", block)
        self.assertNotIn("overflow: hidden", block)
