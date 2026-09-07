# Kassa/Moliya tizimi redizayn + tuzatishlar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the entire Django kassa/finance app (boss/cashier/operator roles) with a consistent modern design system, and ship the 7 functional requirements the user asked for (persisted category/counterparty picklists, checkbox bulk-confirm, multi-category filter with persistence, pending-vs-confirmed money visibility everywhere), plus authorized legacy bug fixes found while reading the code.

**Architecture:** Django 5.2 server-rendered templates, no SPA/build step. Tailwind via CDN (unchanged) + Alpine.js via CDN (new) for the interactivity that used to be hand-rolled vanilla JS (checkbox bulk-select, filter chips, select↔text-input toggles). Two new lookup models (`Category`, `Counterparty`) back the "remember what I typed" picklists. A small `finance/views/helpers.py` centralizes the money-stats aggregation (confirmed vs pending) and the filter-preserving redirect, replacing three copies of near-identical code.

**Tech Stack:** Django 5.2.4, SQLite (dev, `app.db`) / Postgres (prod, per `psycopg2-binary` in requirements), Tailwind CDN, Alpine.js 3.x CDN, `django-widget-tweaks` (already installed, unused so far).

**Spec:** `docs/superpowers/specs/2026-09-07-kassa-redesign-design.md`

## Global Constraints

- No frontend build step — Tailwind CDN (`<script src="https://cdn.tailwindcss.com">`) and Alpine.js CDN (`https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js`) only, both already/newly approved by the user.
- Design tokens are CSS custom properties on `:root` in `templates/base.html`, light theme is the default, dark theme via `@media (prefers-color-scheme: dark)`. Exact values: `--color-bg:#F8FAFC`, `--color-surface:#FFFFFF`, `--color-surface-muted:#F1F5F9`, `--color-border:#E2E8F0`, `--color-text:#0F172A`, `--color-text-muted:#64748B`, `--color-brand:#1E3A8A`, `--color-brand-foreground:#FFFFFF`, `--color-positive:#16A34A`, `--color-positive-bg:#F0FDF4`, `--color-negative:#DC2626`, `--color-negative-bg:#FEF2F2`, `--color-pending:#D97706`, `--color-pending-bg:#FFFBEB`.
- UI font: Inter. Money amounts: `.money` class (`font-variant-numeric: tabular-nums`, monospace stack).
- Every picklist ("Boshqa" pattern) works the same way: server-rendered `<select>` of DB-backed active options + a `('__new__', "+ Yangi qo'shish")` choice; picking it swaps the select for a text input (Alpine `x-show`, see `templates/partials/_select_or_new_field.html`); the submitted value is `get_or_create`'d so it appears in the select next time. Never a free-text "Boshqa" typed inline in the select itself.
- Every "tasdiqlash" action anywhere in the app is checkbox multi-select + one bulk "Tasdiqlash" button — no more per-row confirm buttons.
- Any POST view that redirects back into a filtered list must preserve the querystring the user was looking at, via `finance.views.helpers.preserve_filters()` and a `current_qs` hidden input carrying `{{ request.GET.urlencode }}`.
- Money stats are always split into `confirmed` (is_closed=True, existing manual-offset-adjusted logic) and `pending` (is_closed=False, live, un-offset) — never hide the pending numbers.
- Follow existing code conventions: Django class-based views in `finance/views/{accounts,transaction}.py`, forms in `finance/forms.py`, mixins in `finance/mixins.py`, templates extend `templates/base.html`.
- Every pinned-version external `<script src="https://cdn...">` tag (i.e. everything except Tailwind's play-CDN script, which is a self-updating JIT compiler that Tailwind's own docs say not to pin with SRI) gets `integrity="sha384-..." crossorigin="anonymous"`, verified against the exact file fetched during planning:
  - Alpine.js `alpinejs@3.14.1/dist/cdn.min.js` → `sha384-l8f0VcPi/M1iHPv8egOnY/15TDwqgbOR1anMIJWvU6nLRgZVLTLSaNqi/TOoT5Fh`
  - html2pdf.js `html2pdf.js/0.10.1/html2pdf.bundle.min.js` → `sha384-Yv5O+t3uE3hunW8uyrbpPW3iw6/5/Y7HitWJBLgqfMoA36NogMmy+8wWZMpn3HWc`
  - (`html2canvas.min.js` and `jspdf.umd.min.js` are dropped entirely, not just SRI'd — see Task 15 Step 1's cleanup note: `html2pdf.bundle.min.js` already bundles both, so `boss.html`'s separate loads of them were redundant dead weight.)

---

## Task 1: `Category` and `Counterparty` models

**Files:**
- Modify: `finance/models.py`
- Migration: `finance/migrations/` (generated via `makemigrations`)

**Interfaces:**
- Produces: `Category(name: str unique, group: 'expense'|'xarajat', is_active: bool, created)`, `Counterparty(name: str unique, is_active: bool, created)` — both with `Meta.ordering = ['name']` and `__str__` returning `self.name`. `Transaction.counterparty` becomes a plain `CharField` (no more `choices=PERSONS`).

- [ ] **Step 1: Add the two models to `finance/models.py`**

Insert directly after the `class Company(models.Model): name = ...` block (before the `PERSONS` list, which stays for now — Task 6 removes it once nothing references it):

```python
class Category(models.Model):
    GROUPS = [('expense', 'Chiqim'), ('xarajat', 'Xarajat')]

    name = models.CharField(max_length=100, unique=True)
    group = models.CharField(max_length=10, choices=GROUPS)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Counterparty(models.Model):
    name = models.CharField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'counterparties'

    def __str__(self):
        return self.name
```

- [ ] **Step 2: Remove the static `choices=PERSONS` from `Transaction.counterparty`**

In the `Transaction` model, change:

```python
    counterparty = models.CharField(max_length=255, choices=PERSONS)
```

to:

```python
    counterparty = models.CharField(max_length=255)
```

(Historical rows are untouched — this only removes the DB-level choice constraint so the field can hold any value the new `Counterparty`-backed forms produce. `get_counterparty_display()` calls elsewhere lose their translation power; Task 6 fixes every template that calls it.)

- [ ] **Step 3: Generate the migration**

Run: `python manage.py makemigrations finance`
Expected: a new file like `finance/migrations/00XX_category_counterparty_alter_transaction_counterparty.py` containing `CreateModel` for `Category` and `Counterparty` plus `AlterField` for `Transaction.counterparty`. Note the exact filename — Task 2's migration depends on it.

- [ ] **Step 4: Apply and sanity-check**

Run: `python manage.py migrate finance`
Expected: migration applies with no errors. Run `python manage.py shell -c "from finance.models import Category, Counterparty; print(Category.objects.count(), Counterparty.objects.count())"` → expect `0 0`.

- [ ] **Step 5: Commit**

```bash
git add finance/models.py finance/migrations/
git commit -m "feat: add Category and Counterparty lookup models"
```

---

## Task 2: Data migration — backfill `Category`/`Counterparty` from legacy data

**Files:**
- Create: `finance/migrations/00XX_backfill_category_counterparty.py` (exact number = Task 1's migration number + 1; run `python manage.py makemigrations finance --empty --name backfill_category_counterparty` to generate the skeleton, then fill in `operations`)

**Interfaces:**
- Consumes: `Category`, `Counterparty`, `Transaction`, `DailyReport` (historical model state, via `apps.get_model` — never import the current `finance.models` module directly inside a migration).
- Produces: populated `Category`/`Counterparty` tables; normalizes any `Transaction.counterparty` value that still equals an old `PERSONS` slug (e.g. `'kenjayev_jasur'`) into its human label (e.g. `'Kenjayev Jasur'`), so `{{ transaction.counterparty }}` displays correctly once `get_counterparty_display` is removed from templates (Task 6).

- [ ] **Step 1: Write the migration**

```python
from django.db import migrations

PERSONS_SEED = [
    ('kenjayev_jasur', 'Kenjayev Jasur'),
    ('abdullayev_vohid', 'Abdullayev Vohid'),
    ('murodov_zubaydullo', 'Murodov Zubaydullo'),
    ('yarashev_kamol', 'Yarashev Kamol'),
    ('umarov_maxsud', 'Umarov Maxsud'),
    ('axmedov_ulugbek', "Axmedov Ulug'bek"),
    ('amonova_rushana', 'Amonova Rushana'),
    ('hamidova_umida', 'Hamidova Umida'),
]

CATEGORIES_SEED = [
    ('chikako zavod', 'expense'),
    ('jasur un', 'expense'),
    ('ravshan $', 'expense'),
    ('almashdi', 'expense'),
    ('rasxod den', 'expense'),
    ('mssb xarajat', 'xarajat'),
    ('opt xarajat', 'xarajat'),
    ('sfb xarajat', 'xarajat'),
]


def backfill(apps, schema_editor):
    Counterparty = apps.get_model('finance', 'Counterparty')
    Category = apps.get_model('finance', 'Category')
    Transaction = apps.get_model('finance', 'Transaction')
    DailyReport = apps.get_model('finance', 'DailyReport')

    slug_to_label = dict(PERSONS_SEED)

    for label in slug_to_label.values():
        Counterparty.objects.get_or_create(name__iexact=label, defaults={'name': label})

    for slug, label in slug_to_label.items():
        Transaction.objects.filter(type='income', counterparty=slug).update(counterparty=label)

    counterparty_values = (
        Transaction.objects.filter(type='income')
        .exclude(counterparty__isnull=True)
        .exclude(counterparty='')
        .values_list('counterparty', flat=True)
        .distinct()
    )
    for value in counterparty_values:
        value = (value or '').strip()
        if value:
            Counterparty.objects.get_or_create(name__iexact=value, defaults={'name': value})

    for name, group in CATEGORIES_SEED:
        Category.objects.get_or_create(name__iexact=name, defaults={'name': name, 'group': group})

    category_values = (
        DailyReport.objects.filter(type__in=['expense', 'xarajat'])
        .exclude(category__isnull=True)
        .exclude(category='')
        .values_list('category', flat=True)
        .distinct()
    )
    for value in category_values:
        value = (value or '').strip()
        if value:
            Category.objects.get_or_create(name__iexact=value, defaults={'name': value, 'group': 'expense'})


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '00XX_category_counterparty_alter_transaction_counterparty'),  # replace with Task 1's exact filename
    ]

    operations = [
        migrations.RunPython(backfill, noop_reverse),
    ]
```

Any historical free-text category not in `CATEGORIES_SEED` defaults to `group='expense'` — boss can recategorize via `/admin/` if wrong (Task 3).

- [ ] **Step 2: Run it**

Run: `python manage.py migrate finance`
Expected: no errors. Then `python manage.py shell -c "from finance.models import Category, Counterparty; print(Category.objects.count(), Counterparty.objects.count())"` → expect `8` (or more, if historical free-text values existed) and `>= 8`.

- [ ] **Step 3: Write a regression test for the backfill logic**

Add to `finance/tests.py`:

```python
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
```

- [ ] **Step 4: Run the test**

Run: `python manage.py test finance.tests.DataMigrationBackfillTests -v 2`
Expected: `OK` (2 tests).

- [ ] **Step 5: Commit**

```bash
git add finance/migrations/ finance/tests.py
git commit -m "feat: backfill Category/Counterparty from legacy PERSONS/CATEGORIES data"
```

---

## Task 3: Admin registration

**Files:**
- Modify: `finance/admin.py`

- [ ] **Step 1: Register the two models**

```python
from finance.models import User, Transaction, DailyReport, Stat, Category, Counterparty


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'group', 'is_active', 'created']
    list_filter = ['group', 'is_active']
    search_fields = ['name']


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created']
    list_filter = ['is_active']
    search_fields = ['name']
```

- [ ] **Step 2: Verify in the admin**

Run: `python manage.py runserver` (or use the `run` skill), log in to `/admin/` as a superuser, confirm "Categories" and "Counterparties" appear and list the backfilled rows with correct `group` values.

- [ ] **Step 3: Commit**

```bash
git add finance/admin.py
git commit -m "feat: register Category and Counterparty in admin"
```

---

## Task 4: `preserve_filters` helper + `BulkConfirmReportsView` (replaces `ConfirmExpenseView`/`ConfirmIncomeView`)

**Files:**
- Create: `finance/views/helpers.py`
- Modify: `finance/views/transaction.py` (remove `ConfirmExpenseView`, `ConfirmIncomeView`; add `BulkConfirmReportsView`)
- Modify: `finance/urls.py`
- Test: `finance/tests.py`

**Interfaces:**
- Produces: `preserve_filters(request, base_url: str) -> str` — reads `request.POST['current_qs']`, appends as querystring to `base_url`. `BulkConfirmReportsView` — `POST /reports/bulk-confirm/`, form fields `report_ids` (multi) + `current_qs` (hidden), url name `bulk_confirm_reports`.
- Consumes (later tasks' templates must produce): checkbox inputs `name="report_ids" value="{{ report.pk }}"` and hidden `<input type="hidden" name="current_qs" value="{{ request.GET.urlencode }}">` inside a `<form method="post" action="{% url 'bulk_confirm_reports' %}">`.

- [ ] **Step 1: Write the failing tests**

Add to `finance/tests.py`:

```python
from decimal import Decimal
from django.urls import reverse
from finance.models import User, DailyReport


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
```

- [ ] **Step 2: Run to verify failure**

Run: `python manage.py test finance.tests.BulkConfirmReportsViewTests -v 2`
Expected: FAIL — `NoReverseMatch: Reverse for 'bulk_confirm_reports' not found`.

- [ ] **Step 3: Write `finance/views/helpers.py`**

```python
from decimal import Decimal
from django.db.models import Sum
from finance.models import Transaction, Stat, StatTypes


def preserve_filters(request, base_url):
    """Redirect back to base_url keeping the query string the page was
    showing when its form was submitted. POST handlers read `current_qs`
    (a hidden field carrying `request.GET.urlencode` from the filtered
    page) instead of `request.META['QUERY_STRING']`, because that reflects
    the POST target's own (empty) querystring, not the page the user saw.
    """
    qs = request.POST.get('current_qs', '')
    return f"{base_url}?{qs}" if qs else base_url
```

- [ ] **Step 4: Replace the two confirm views in `finance/views/transaction.py`**

Remove `ConfirmExpenseView` and `ConfirmIncomeView` entirely. Add (near the top, after imports — add `from django.http import HttpResponseForbidden` and `from finance.views.helpers import preserve_filters` to the import block):

```python
class BulkConfirmReportsView(LoginRequiredMixin, View):
    success_url_boss = reverse_lazy('boss_dashboard')
    success_url_cashier = reverse_lazy('cashier_dashboard')

    def post(self, request, *args, **kwargs):
        role = request.user.role
        if role == 'boss':
            allowed_types = ['expense', 'xarajat']
            success_url = str(self.success_url_boss)
        elif role == 'cashier':
            allowed_types = ['income']
            success_url = str(self.success_url_cashier)
        else:
            return HttpResponseForbidden()

        report_ids = request.POST.getlist('report_ids')
        if report_ids:
            DailyReport.objects.filter(pk__in=report_ids, type__in=allowed_types).update(is_closed=True)
            messages.success(request, "Tanlangan hisobotlar tasdiqlandi.")

        return redirect(preserve_filters(request, success_url))
```

- [ ] **Step 5: Update `finance/urls.py`**

Replace:

```python
from .views.transaction import (
    TransactionCreateView, ConfirmExpenseView, CloseCashRegister, ConfirmIncomeView,
    ExpensesPageView, IncomesPageView, TransactionList, ChangeStatView
)
```

with:

```python
from .views.transaction import (
    TransactionCreateView, BulkConfirmReportsView, CloseCashRegister,
    ExpensesPageView, IncomesPageView, TransactionList, ChangeStatView
)
```

Replace:

```python
    path('reports/<int:pk>/confirm/', ConfirmExpenseView.as_view(), name='confirm_expense'),
    path('cash-register/close/', CloseCashRegister.as_view(), name='close_cash_register'),
    path('confirm-income/<int:pk>/', ConfirmIncomeView.as_view(), name='confirm_income'),
```

with:

```python
    path('reports/bulk-confirm/', BulkConfirmReportsView.as_view(), name='bulk_confirm_reports'),
    path('cash-register/close/', CloseCashRegister.as_view(), name='close_cash_register'),
```

- [ ] **Step 6: Run tests again**

Run: `python manage.py test finance.tests.BulkConfirmReportsViewTests -v 2`
Expected: `OK` (5 tests).

- [ ] **Step 7: Commit**

```bash
git add finance/views/helpers.py finance/views/transaction.py finance/urls.py finance/tests.py
git commit -m "feat: replace single-row confirm views with checkbox bulk-confirm"
```

---

## Task 5: `ExpenseForm` — DB-backed, group-aware category picklist

**Files:**
- Modify: `finance/forms.py` (`ExpenseForm`)
- Modify: `finance/views/transaction.py` (`ExpensesPageView` — also fixes the missing-context-on-invalid-form bug found during review)
- Test: `finance/tests.py`

**Interfaces:**
- Produces: `ExpenseForm.category_options` — `list[{'name': str, 'group': 'expense'|'xarajat'}]`, exposed for the template's Alpine group-filtering (Task 18 consumes this). `ExpenseForm.fields['category'].choices` includes `('__new__', "+ Yangi qo'shish")`. `ExpenseForm` gains `new_category` field.
- Consumes: `Category` model (Task 1).

- [ ] **Step 1: Write the failing test**

Add to `finance/tests.py`:

```python
from finance.forms import ExpenseForm


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
        Category.objects.create(name='chikako zavod', group='expense')
        form = ExpenseForm(data={
            'category': 'chikako zavod', 'amount_uzs': '10000', 'payment_type': 'cash',
            'description': '', 'exp_type': 'expense',
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save(operator=self.cashier, date='2026-09-07')
        self.assertEqual(Category.objects.filter(name__iexact='chikako zavod').count(), 1)
```

- [ ] **Step 2: Run to verify failure**

Run: `python manage.py test finance.tests.ExpenseFormCategoryTests -v 2`
Expected: FAIL (category choice `'chikako zavod'` not a valid choice — form still uses the old hardcoded `CATEGORIES` dict).

- [ ] **Step 3: Rewrite `ExpenseForm` in `finance/forms.py`**

Add `from .models import ... Category, Counterparty` to the existing model import line. Delete the old `CATEGORIES` dict. Replace the `ExpenseForm` class body with:

```python
class ExpenseForm(forms.Form):
    category = forms.ChoiceField(choices=[])
    new_category = forms.CharField(required=False, max_length=100, label="Yangi kategoriya nomi")
    amount_usd = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    amount_uzs = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    amount_rub = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    amount_eur = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    payment_type = forms.ChoiceField(choices=Transaction.PAYMENT_TYPES)
    click = forms.ChoiceField(choices=CLICKS, required=False)
    description = forms.CharField(widget=forms.Textarea, required=False)
    exp_type = forms.CharField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        active_categories = Category.objects.filter(is_active=True)
        self.category_options = [{'name': c.name, 'group': c.group} for c in active_categories]
        self.fields['category'].choices = (
            [(c.name, c.name) for c in active_categories] + [('__new__', "+ Yangi qo'shish")]
        )

    def clean(self):
        cleaned_data = super().clean()
        category = cleaned_data.get('category')
        new_category = (cleaned_data.get('new_category') or '').strip()
        if category == '__new__':
            if not new_category:
                self.add_error('new_category', "Yangi kategoriya nomini kiriting.")
            else:
                cleaned_data['category'] = new_category.lower()
        return cleaned_data

    def save(self, commit=True, operator=None, date=None):
        exp_type = self.cleaned_data.get('exp_type')
        category = self.cleaned_data['category']
        Category.objects.get_or_create(
            name__iexact=category,
            defaults={'name': category, 'group': exp_type if exp_type in dict(Category.GROUPS) else 'expense'},
        )
        desc = self.cleaned_data.get('description') or None

        if date:
            try:
                parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                parsed_date = datetime.now().date()
        else:
            parsed_date = datetime.now().date()

        report = DailyReport.objects.create(
            operator=operator, type=exp_type, is_closed=False,
            category=category, desc=desc, date=parsed_date,
        )
        report.total_uzs = self.cleaned_data.get('amount_uzs') or 0
        report.total_usd = self.cleaned_data.get('amount_usd') or 0
        report.total_rub = self.cleaned_data.get('amount_rub') or 0
        report.total_eur = self.cleaned_data.get('amount_eur') or 0

        payment_type = self.cleaned_data.get('payment_type')
        detail_key = self.cleaned_data.get('click') if payment_type == 'click' else payment_type
        report.uzs_detail = {detail_key: float(self.cleaned_data.get('amount_uzs') or 0)}
        report.usd_detail = {detail_key: float(self.cleaned_data.get('amount_usd') or 0)}
        report.rub_detail = {detail_key: float(self.cleaned_data.get('amount_rub') or 0)}
        report.eur_detail = {detail_key: float(self.cleaned_data.get('amount_eur') or 0)}
        report.save()

        transaction = Transaction.objects.create(
            type='expense',
            amount_usd=self.cleaned_data.get('amount_usd'),
            amount_uzs=self.cleaned_data.get('amount_uzs'),
            amount_rub=self.cleaned_data.get('amount_rub'),
            amount_eur=self.cleaned_data.get('amount_eur'),
            payment_type=payment_type,
            click=self.cleaned_data.get('click') if payment_type == 'click' else None,
            description=self.cleaned_data['description'],
            operator=operator,
            report=report,
            counterparty=category,
            date=datetime.combine(parsed_date, datetime.now().time()),
        )
        return transaction
```

(This also drops the old dead branch that silently substituted `description` for `category` when the category wasn't a recognized dict key — the new form always validates `category` explicitly, so that quirk can't happen anymore.)

- [ ] **Step 4: Fix `ExpensesPageView` in `finance/views/transaction.py`** (found during review: the `post()` error path re-renders without `reports`/`date` in context, so a validation failure shows a broken page)

Replace the whole `ExpensesPageView` class with:

```python
class ExpensesPageView(LoginRequiredMixin, CashierRequiredMixin, View):
    template_name = 'expenses_page.html'
    success_url = reverse_lazy('expenses_list')

    def get(self, request, *args, **kwargs):
        return self._render(request)

    def post(self, request, *args, **kwargs):
        form = ExpenseForm(request.POST)
        report_date = request.GET.get('date', None) or date.today().strftime('%Y-%m-%d')
        if form.is_valid():
            form.save(operator=request.user, date=report_date)
            messages.success(request, "Chiqim muvaffaqiyatli qo'shildi.")
            return redirect(self.success_url + f'?date={report_date}')
        messages.error(request, "Formani tekshiring.")
        return self._render(request, form=form)

    def _render(self, request, form=None):
        report_date = request.GET.get('date', None) or date.today().strftime('%Y-%m-%d')
        reports = DailyReport.objects.filter(type__in=['expense', 'xarajat'], date=report_date).order_by('-date')
        context = {
            'form': form or ExpenseForm(),
            'reports': reports,
            'date': report_date,
            'clicks': CLICKS,
            'clicks_map': dict(CLICKS),
        }
        return render(request, self.template_name, context)
```

- [ ] **Step 5: Run tests again**

Run: `python manage.py test finance.tests.ExpenseFormCategoryTests -v 2`
Expected: `OK` (2 tests).

- [ ] **Step 6: Commit**

```bash
git add finance/forms.py finance/views/transaction.py finance/tests.py
git commit -m "feat: DB-backed group-aware category picklist for expenses"
```

---

## Task 6: Operator "kimdan oldi" DB-backed + `IncomeForm` typo fix + silent-failure fix

**Files:**
- Modify: `finance/forms.py` (`TransactionFrom`, `IncomeForm`)
- Modify: `finance/views/accounts.py` (`OperatorDashboardView`, `TransactionView` — drop dead/stale `PERSONS` context)
- Modify: `finance/views/transaction.py` (`IncomesPageView` — fixes silent form-failure bug found during review)
- Modify: `finance/models.py` (delete now-unused `PERSONS` constant)
- Test: `finance/tests.py`

**Interfaces:**
- Produces: `TransactionFrom.fields['counterparty'].choices` DB-backed + `('__new__', ...)`; `IncomeForm.counterparty` (renamed from `countryparty`).
- Consumes: `Counterparty` model (Task 1).

- [ ] **Step 1: Write the failing test**

Add to `finance/tests.py`:

```python
from finance.forms import TransactionFrom
from finance.models import Counterparty


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
```

- [ ] **Step 2: Run to verify failure**

Run: `python manage.py test finance.tests.OperatorCounterpartyFormTests -v 2`
Expected: FAIL (`'__new__'` not a valid choice — form still uses static `PERSONS`).

- [ ] **Step 3: Rewrite `TransactionFrom` in `finance/forms.py`**

```python
class TransactionFrom(forms.ModelForm):
    counterparty = forms.ChoiceField(choices=[])
    other_counterparty = forms.CharField(required=False, max_length=255, label="Boshqa shaxs nomi")

    class Meta:
        model = Transaction
        fields = ['amount_usd', 'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'click', 'comment', 'counterparty']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['counterparty'].choices = (
            [(c.name, c.name) for c in Counterparty.objects.filter(is_active=True)] + [('__new__', "+ Yangi qo'shish")]
        )

    def clean(self):
        cleaned_data = super().clean()
        counterparty = cleaned_data.get('counterparty')
        other = (cleaned_data.get('other_counterparty') or '').strip()
        if counterparty == '__new__':
            if not other:
                self.add_error('other_counterparty', "Yangi shaxs nomini kiriting.")
            else:
                cleaned_data['counterparty'] = other
        return cleaned_data

    def save(self, commit=True, operator=None, date=None):
        transaction = super().save(commit=False)
        counterparty = self.cleaned_data['counterparty']
        Counterparty.objects.get_or_create(name__iexact=counterparty, defaults={'name': counterparty})
        transaction.counterparty = counterparty
        transaction.operator = operator
        transaction.type = 'income'

        if date:
            try:
                parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
                now_time = datetime.now().time()
                transaction.date = datetime.combine(parsed_date, now_time)
            except Exception:
                transaction.date = datetime.now()
        else:
            transaction.date = datetime.now()

        if commit:
            transaction.save()

        return transaction
```

- [ ] **Step 4: Fix the `countryparty` typo in `IncomeForm`**

```python
class IncomeForm(forms.ModelForm):
    counterparty = forms.ChoiceField(choices=IncomeCHoices)
    other_counterparty = forms.CharField(required=False, max_length=255, label="Boshqa shaxs nomi")
    click = forms.ChoiceField(choices=CLICKS, required=False)

    class Meta:
        model = Transaction
        fields = ['amount_usd', 'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'click', 'comment', 'counterparty', 'other_counterparty']

    def save(self, commit=True, operator=None, date=None):
        transaction = super().save(commit=False)
        if self.cleaned_data['counterparty'] == 'other':
            transaction.counterparty = self.cleaned_data['other_counterparty'].lower()
        else:
            transaction.counterparty = self.cleaned_data['counterparty'].lower()
        transaction.operator = operator

        if date:
            try:
                parsed_date = datetime.strptime(date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                parsed_date = datetime.now().date()
        else:
            parsed_date = datetime.now().date()

        report = DailyReport.objects.create(operator=operator, type='income', is_closed=True, date=parsed_date)
        report.total_uzs = self.cleaned_data.get('amount_uzs') or 0
        report.total_usd = self.cleaned_data.get('amount_usd') or 0
        report.total_rub = self.cleaned_data.get('amount_rub') or 0
        report.total_eur = self.cleaned_data.get('amount_eur') or 0

        payment_type = self.cleaned_data.get('payment_type')
        detail_key = self.cleaned_data.get('click') if payment_type == 'click' else payment_type
        report.uzs_detail = {detail_key: float(self.cleaned_data.get('amount_uzs') or 0)}
        report.usd_detail = {detail_key: float(self.cleaned_data.get('amount_usd') or 0)}
        report.rub_detail = {detail_key: float(self.cleaned_data.get('amount_rub') or 0)}
        report.eur_detail = {detail_key: float(self.cleaned_data.get('amount_eur') or 0)}
        report.category = transaction.counterparty
        report.save()

        transaction.report = report
        transaction.type = 'income'
        transaction.click = self.cleaned_data.get('click') if payment_type == 'click' else None
        transaction.date = datetime.combine(parsed_date, datetime.now().time())
        if commit:
            transaction.save()

        return transaction
```

Note: `IncomeCHoices` (Almashdi / Vozvrat rasx den / Boshqa) stays a fixed static list — it is a source-of-funds category, not a person list, so it is **not** converted to a DB-backed picklist. Only the field name changes.

- [ ] **Step 5: Fix `IncomesPageView`'s silent failure in `finance/views/transaction.py`** (found during review: on an invalid form it currently redirects to `success_url` unconditionally, silently dropping the submitted data with zero user feedback)

```python
class IncomesPageView(LoginRequiredMixin, CashierRequiredMixin, View):
    template_name = 'incomes_page.html'
    success_url = reverse_lazy('incomes_list')

    def get(self, request, *args, **kwargs):
        return self._render(request)

    def post(self, request, *args, **kwargs):
        form = IncomeForm(request.POST)
        report_date = request.GET.get('date', None) or date.today().strftime('%Y-%m-%d')
        if form.is_valid():
            form.save(operator=request.user, date=report_date)
            messages.success(request, "Kirim muvaffaqiyatli qo'shildi.")
            return redirect(self.success_url + f'?date={report_date}')
        messages.error(request, "Formani tekshiring.")
        return self._render(request, form=form)

    def _render(self, request, form=None):
        report_date = request.GET.get('date', None) or date.today().strftime('%Y-%m-%d')
        reports = DailyReport.objects.filter(type='income', operator=request.user, date=report_date).order_by('-date')
        context = {
            'form': form or IncomeForm(),
            'reports': reports,
            'date': report_date,
            'choices': IncomeCHoices,
            'clicks': CLICKS,
            'clicks_map': dict(CLICKS),
        }
        return render(request, self.template_name, context)
```

- [ ] **Step 6: Drop the dead `PERSONS` context and constant**

In `finance/views/accounts.py`: remove `from finance.models import PERSONS, ...` (keep the rest of that import line), add `Counterparty` to the `finance.models` import. In `OperatorDashboardView.get_context_data`, replace `context['persons'] = PERSONS` with `context['counterparties'] = Counterparty.objects.filter(is_active=True)`. In `TransactionView.get`, remove `'persons': PERSONS,` from the context dict entirely (the fork confirmed `edit_tran.html` never uses it).

In `finance/models.py`, delete the `PERSONS` list (now unreferenced anywhere).

- [ ] **Step 7: Run tests again**

Run: `python manage.py test finance -v 2`
Expected: all tests `OK` (confirms nothing else broke from removing `PERSONS`).

- [ ] **Step 8: Commit**

```bash
git add finance/forms.py finance/views/accounts.py finance/views/transaction.py finance/models.py finance/tests.py
git commit -m "feat: DB-backed counterparty picklist for operator income entry; fix countryparty typo and silent income-form failure"
```

---

## Task 7: Shared money-stats helper — confirmed vs pending split

**Files:**
- Modify: `finance/views/helpers.py` (add `raw_confirmed_totals`, `raw_pending_totals`, `compute_money_stats`)
- Modify: `finance/views/accounts.py` (`BossDashboardView`, `ChiefCashierDashboardView`)
- Modify: `finance/views/transaction.py` (`ChangeStatView` — refactored onto the same helper, no behavior change)
- Test: `finance/tests.py`

**Interfaces:**
- Produces: `compute_money_stats() -> {'confirmed': {'income': Stat, 'expense': Stat, 'diff': Stat}, 'pending': {'income': dict, 'expense': dict, 'diff': dict}}`. Each `dict`/`Stat` exposes `total_uzs`/`total_usd`/`total_rub`/`total_eur` — template access (`stats.confirmed.income.total_uzs`, `stats.pending.income.total_uzs`) is identical whether the value is a `Stat` instance or a plain dict, since Django template variable lookup tries dict-key then attribute either way.
- Also produces: `raw_confirmed_totals() -> {'income': dict, 'expense': dict, 'diff': dict}` (unadjusted, no `default_*` offset applied) — reused by `ChangeStatView`.

- [ ] **Step 1: Write the failing test**

Add to `finance/tests.py`:

```python
from decimal import Decimal
from finance.views.helpers import compute_money_stats
from finance.models import Transaction


class MoneyStatsTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='op_ms', password='pass12345', role='operator')
        today = timezone.now().date()

        closed_report = DailyReport.objects.create(operator=self.operator, type='income', date=today, is_closed=True)
        Transaction.objects.create(
            type='income', payment_type='cash', amount_uzs=Decimal('100000'),
            operator=self.operator, counterparty='Test', report=closed_report, date=timezone.now(),
        )

        open_report = DailyReport.objects.create(operator=self.operator, type='income', date=today, is_closed=False)
        Transaction.objects.create(
            type='income', payment_type='cash', amount_uzs=Decimal('40000'),
            operator=self.operator, counterparty='Test', report=open_report, date=timezone.now(),
        )

    def test_confirmed_and_pending_are_separated(self):
        stats = compute_money_stats()
        self.assertEqual(stats['confirmed']['income'].total_uzs, Decimal('100000'))
        self.assertEqual(stats['pending']['income']['total_uzs'], Decimal('40000'))
```

- [ ] **Step 2: Run to verify failure**

Run: `python manage.py test finance.tests.MoneyStatsTests -v 2`
Expected: FAIL — `ImportError: cannot import name 'compute_money_stats'`.

- [ ] **Step 3: Add the helpers to `finance/views/helpers.py`**

```python
from django.db.models import Sum
from finance.models import Transaction, Stat, StatTypes

CURRENCIES = ('uzs', 'usd', 'rub', 'eur')


def _aggregate(qs):
    result = qs.aggregate(
        total_usd=Sum('amount_usd'), total_uzs=Sum('amount_uzs'),
        total_rub=Sum('amount_rub'), total_eur=Sum('amount_eur'),
    )
    return {k: v or 0 for k, v in result.items()}


def _totals_for(is_closed):
    income = _aggregate(Transaction.objects.filter(type='income', report__is_closed=is_closed, payment_type='cash'))
    expense = _aggregate(Transaction.objects.filter(type='expense', report__is_closed=is_closed, payment_type='cash'))
    diff = {f'total_{cur}': income[f'total_{cur}'] - expense[f'total_{cur}'] for cur in CURRENCIES}
    return {'income': income, 'expense': expense, 'diff': diff}


def raw_confirmed_totals():
    return _totals_for(is_closed=True)


def raw_pending_totals():
    return _totals_for(is_closed=False)


def compute_money_stats():
    """Confirmed totals get the manual `Stat.default_*` correction applied
    (existing boss "edit daily stats" feature); pending totals are always
    live with no correction — there's nothing to manually fix on money that
    hasn't been confirmed yet."""
    raw = raw_confirmed_totals()
    pending = raw_pending_totals()

    inc_stat, _ = Stat.objects.get_or_create(type=StatTypes.INCOME)
    for cur in CURRENCIES:
        setattr(inc_stat, f'total_{cur}', raw['income'][f'total_{cur}'] - getattr(inc_stat, f'default_{cur}'))
    inc_stat.save()

    exp_stat, _ = Stat.objects.get_or_create(type=StatTypes.EXPENSE)
    for cur in CURRENCIES:
        setattr(exp_stat, f'total_{cur}', raw['expense'][f'total_{cur}'] - getattr(exp_stat, f'default_{cur}'))
    exp_stat.save()

    diff_stat, _ = Stat.objects.get_or_create(type=StatTypes.BALANCE)
    for cur in CURRENCIES:
        setattr(diff_stat, f'total_{cur}', int(raw['diff'][f'total_{cur}']) - getattr(diff_stat, f'default_{cur}'))
    diff_stat.save()

    return {
        'confirmed': {'income': inc_stat, 'expense': exp_stat, 'diff': diff_stat},
        'pending': pending,
    }
```

- [ ] **Step 4: Wire into `BossDashboardView.get_context_data`** (`finance/views/accounts.py`)

Replace the whole block from `# All-time stats (no date filter) ...` down to `context['stats'] = {...}` with:

```python
        context['stats'] = compute_money_stats()
```

(Add `compute_money_stats` to the file's top-level `from finance.views.helpers import ...` — create that import line if it doesn't exist yet.)

- [ ] **Step 5: Wire into `ChiefCashierDashboardView.get_context_data`** (same file)

Replace its equivalent duplicated block (from `income_qs = Transaction.objects.filter(type='income', report__is_closed=True, ...)` down through `context['stats'] = {...}`, **keeping** the preceding `context['total']` payment-method breakdown block untouched — that's a separate feature, not part of this task) with the same `context['stats'] = compute_money_stats()` line.

- [ ] **Step 6: Refactor `ChangeStatView` in `finance/views/transaction.py` onto `raw_confirmed_totals`**

Replace the view body with:

```python
class ChangeStatView(LoginRequiredMixin, BossRequiredMixin, View):
    success_url = reverse_lazy('boss_dashboard')

    def post(self, request, *args, **kwargs):
        stat_type = request.POST.get('stat_type')
        total_uzs = int(request.POST.get('total_uzs', 0))
        total_usd = int(request.POST.get('total_usd', 0))
        total_rub = int(request.POST.get('total_rub', 0))
        total_eur = int(request.POST.get('total_eur', 0))

        stat, _ = Stat.objects.get_or_create(type=stat_type)
        raw = raw_confirmed_totals()
        data = raw[stat_type]

        stat.default_uzs = (data['total_uzs'] or 0) - total_uzs
        stat.default_usd = (data['total_usd'] or 0) - total_usd
        stat.default_rub = (data['total_rub'] or 0) - total_rub
        stat.default_eur = (data['total_eur'] or 0) - total_eur
        stat.save()

        return redirect(self.success_url)
```

Add `raw_confirmed_totals` to the `from finance.views.helpers import ...` line at the top of the file.

- [ ] **Step 7: Run tests**

Run: `python manage.py test finance -v 2`
Expected: all `OK`.

- [ ] **Step 8: Manually verify `ChangeStatView` behavior is unchanged**

Run the dev server, log in as boss, open the "edit daily stats" modal for "Umumiy Kirim", change the value, save, confirm the dashboard now shows the edited value (same as before this refactor — this exercises the code path `MoneyStatsTests` doesn't cover directly).

- [ ] **Step 9: Commit**

```bash
git add finance/views/helpers.py finance/views/accounts.py finance/views/transaction.py finance/tests.py
git commit -m "refactor: extract shared money-stats helper, split confirmed vs pending totals"
```

---

## Task 8: Multi-category filter (Boss, ChiefCashier, TransactionList)

**Files:**
- Modify: `finance/views/accounts.py` (`BossDashboardView`, `ChiefCashierDashboardView`)
- Modify: `finance/views/transaction.py` (`TransactionList`)
- Test: `finance/tests.py`

**Interfaces:**
- Produces: `context['categories']` (list of selected category names from `request.GET.getlist('category')`) and `context['category_options']` (`Category.objects.filter(is_active=True)`) on all three views.

- [ ] **Step 1: Write the failing test**

Add to `finance/tests.py`:

```python
class MultiCategoryFilterTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user(username='boss_cf', password='pass12345', role='boss')
        self.operator = User.objects.create_user(username='op_cf2', password='pass12345', role='operator')
        today = timezone.now().date()
        self.r1 = DailyReport.objects.create(operator=self.operator, type='expense', category='chikako zavod', date=today, is_closed=True)
        self.r2 = DailyReport.objects.create(operator=self.operator, type='expense', category='jasur un', date=today, is_closed=True)
        self.r3 = DailyReport.objects.create(operator=self.operator, type='expense', category='ravshan $', date=today, is_closed=True)

    def test_boss_dashboard_filters_multiple_categories(self):
        self.client.force_login(self.boss)
        response = self.client.get(reverse('boss_dashboard'), {'category': ['chikako zavod', 'jasur un']})
        reports = list(response.context['reports'])
        self.assertIn(self.r1, reports)
        self.assertIn(self.r2, reports)
        self.assertNotIn(self.r3, reports)
```

- [ ] **Step 2: Run to verify failure**

Run: `python manage.py test finance.tests.MultiCategoryFilterTests -v 2`
Expected: FAIL — `r3` still present (no category filtering applied yet).

- [ ] **Step 3: Add filtering to `BossDashboardView.get_context_data`**

After the existing `if context['q']: reports = reports.filter(...)` block, add:

```python
        context['categories'] = self.request.GET.getlist('category')
        if context['categories']:
            reports = reports.filter(category__in=context['categories'])
        context['category_options'] = Category.objects.filter(is_active=True)
```

(Move `context['reports'] = reports.order_by('-date')` to after this block if it currently comes before — check the existing method body and keep the filter chain in order: `from`/`to`/`type`/`q`/`categories`, then assign `context['reports']`.)

- [ ] **Step 4: Add the same to `ChiefCashierDashboardView.get_context_data`**

Same three lines, inserted after its existing `q` filter block and before `context['reports'] = reports.order_by('-date')`.

- [ ] **Step 5: Add the same to `TransactionList.get`** (`finance/views/transaction.py`)

After the existing `if search_query: transactions = transactions.filter(...)` block:

```python
        categories = request.GET.getlist('category')
        if categories:
            transactions = transactions.filter(report__category__in=categories)
```

And add to the `context` dict: `'categories': categories, 'category_options': Category.objects.filter(is_active=True),`.

- [ ] **Step 6: Add `Category` to imports** in both files' existing `finance.models` import lines.

- [ ] **Step 7: Run tests again**

Run: `python manage.py test finance.tests.MultiCategoryFilterTests -v 2`
Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
git add finance/views/accounts.py finance/views/transaction.py finance/tests.py
git commit -m "feat: multi-select category filter on boss/cashier dashboards and transaction list"
```

---

## Task 9: Money-precision fixes (remaining spots) + `TransactionView` amount parsing

**Files:**
- Modify: `finance/models.py` (`_recalc_report`)
- Modify: `finance/views/accounts.py` (`TransactionView.post`)
- Test: `finance/tests.py`

**Interfaces:**
- No new interfaces — pure bug fix, same signatures.

(Tasks 5 and 6 already switched `ExpenseForm.save`/`IncomeForm.save` from `int(...)` to `float(...)` when building `*_detail` JSON. This task covers the two remaining spots the code review found: the signal-driven `_recalc_report` in `models.py`, and `TransactionView.post`'s manual amount parsing.)

- [ ] **Step 1: Write the failing test**

Add to `finance/tests.py`:

```python
class ReportDetailPrecisionTests(TestCase):
    def setUp(self):
        self.operator = User.objects.create_user(username='op_prec', password='pass12345', role='operator')

    def test_recalc_report_preserves_decimal_amount(self):
        report = DailyReport.objects.create(operator=self.operator, type='income', date=timezone.now().date(), is_closed=False)
        Transaction.objects.create(
            type='income', payment_type='cash', amount_uzs=Decimal('1000.75'),
            operator=self.operator, counterparty='Test', report=report, date=timezone.now(),
        )
        report.refresh_from_db()
        self.assertEqual(report.uzs_detail['cash'], 1000.75)
```

- [ ] **Step 2: Run to verify failure**

Run: `python manage.py test finance.tests.ReportDetailPrecisionTests -v 2`
Expected: FAIL — `report.uzs_detail['cash'] == 1000` (truncated).

- [ ] **Step 3: Fix `_recalc_report` in `finance/models.py`**

Change the four lines building `uzs[key]`, `usd[key]`, `rub[key]`, `eur[key]` from `int((...) + (...))` to `float((...) + (...))`:

```python
            uzs[key] = float((uzs.get(key, 0) or 0) + (tr.amount_uzs or 0))
            usd[key] = float((usd.get(key, 0) or 0) + (tr.amount_usd or 0))
            rub[key] = float((rub.get(key, 0) or 0) + (tr.amount_rub or 0))
            eur[key] = float((eur.get(key, 0) or 0) + (tr.amount_eur or 0))
```

- [ ] **Step 4: Run test again**

Run: `python manage.py test finance.tests.ReportDetailPrecisionTests -v 2`
Expected: `OK`.

- [ ] **Step 5: Fix `TransactionView.post` amount parsing in `finance/views/accounts.py`** (found during review — same truncation bug, no dedicated test since it's a thin manual-parse view; covered by Task 21's manual QA pass)

Change:

```python
        transaction.amount_usd = int(data.get('amount_usd', 0) or 0) or None
        transaction.amount_uzs = int(data.get('amount_uzs', 0) or 0) or None
        transaction.amount_rub = int(data.get('amount_rub', 0) or 0) or None
        transaction.amount_eur = int(data.get('amount_eur', 0) or 0) or None
```

to:

```python
        transaction.amount_usd = Decimal(data.get('amount_usd') or 0) or None
        transaction.amount_uzs = Decimal(data.get('amount_uzs') or 0) or None
        transaction.amount_rub = Decimal(data.get('amount_rub') or 0) or None
        transaction.amount_eur = Decimal(data.get('amount_eur') or 0) or None
```

(`Decimal` is already imported at the top of this file.)

- [ ] **Step 6: Run the full suite**

Run: `python manage.py test finance -v 2`
Expected: all `OK`.

- [ ] **Step 7: Commit**

```bash
git add finance/models.py finance/views/accounts.py finance/tests.py
git commit -m "fix: stop truncating decimal currency amounts to integers"
```

---

## Task 10: `TransactionDeleteView` dead-code cleanup

**Files:**
- Modify: `finance/views/accounts.py`

- [ ] **Step 1: Remove the no-op try/except**

In `TransactionDeleteView.get` (soon to be `.post`, see Task 11), replace:

```python
            try:
                report.total_eur = (getattr(report, 'total_eur', Decimal('0')) or Decimal('0')) - eur
            except Exception:
                report.total_eur = (getattr(report, 'total_eur', Decimal('0')) or Decimal('0')) - eur
```

with:

```python
            report.total_eur = (getattr(report, 'total_eur', Decimal('0')) or Decimal('0')) - eur
```

- [ ] **Step 2: Run the suite**

Run: `python manage.py test finance -v 2`
Expected: all `OK` (behavior-neutral cleanup).

- [ ] **Step 3: Commit**

```bash
git add finance/views/accounts.py
git commit -m "refactor: remove dead try/except in TransactionDeleteView"
```

---

## Task 11: Convert GET-based delete to POST-with-confirm (CSRF hardening)

**Files:**
- Modify: `finance/views/accounts.py` (`TransactionDeleteView`, `UserDeleteView`)
- Test: `finance/tests.py`

**Interfaces:**
- `TransactionDeleteView`/`UserDeleteView` now expose `post()` instead of `get()` — same URL names (`transaction_delete`, `user_delete`), same behavior, but a bare GET now 405s instead of deleting. `UserDeleteView` also gains a same-file guard against deleting a `role='boss'` account (authz gap found during review — the template already hides the delete button for boss users, but the view itself had no server-side check).

- [ ] **Step 1: Write the failing tests**

Add to `finance/tests.py`:

```python
class DeleteViewsRequirePostTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_user(username='boss_del', password='pass12345', role='boss')
        self.other_boss = User.objects.create_user(username='boss_del2', password='pass12345', role='boss')

    def test_get_no_longer_deletes_user(self):
        self.client.force_login(self.boss)
        target = User.objects.create_user(username='op_del', password='pass12345', role='operator')
        response = self.client.get(reverse('user_delete', args=[target.pk]))
        self.assertEqual(response.status_code, 405)
        self.assertTrue(User.objects.filter(pk=target.pk).exists())

    def test_post_deletes_user(self):
        self.client.force_login(self.boss)
        target = User.objects.create_user(username='op_del2', password='pass12345', role='operator')
        self.client.post(reverse('user_delete', args=[target.pk]))
        self.assertFalse(User.objects.filter(pk=target.pk).exists())

    def test_cannot_delete_boss_user(self):
        self.client.force_login(self.boss)
        self.client.post(reverse('user_delete', args=[self.other_boss.pk]))
        self.assertTrue(User.objects.filter(pk=self.other_boss.pk).exists())
```

- [ ] **Step 2: Run to verify failure**

Run: `python manage.py test finance.tests.DeleteViewsRequirePostTests -v 2`
Expected: FAIL (`test_get_no_longer_deletes_user` gets 302, not 405 — GET still deletes).

- [ ] **Step 3: Rewrite `UserDeleteView`**

```python
class UserDeleteView(LoginRequiredMixin, BossRequiredMixin, View):
    success_url = reverse_lazy('users')

    def post(self, request, *args, **kwargs):
        user = User.objects.filter(pk=kwargs['pk']).first()
        if user and user.role != 'boss':
            user.delete()
        return redirect(self.success_url)
```

(Drops the `DeleteView` generic base — it was only ever used for its `.delete()` method via the `get()` override; a plain `View` with just `post()` is simpler and 405s on GET automatically.)

- [ ] **Step 4: Rewrite `TransactionDeleteView`'s entry point**

Change `def get(self, request, pk, *args, **kwargs):` to `def post(self, request, pk, *args, **kwargs):` — no other changes to the method body (Task 10 already cleaned up the try/except inside it). Also add `LoginRequiredMixin` to its base classes if not already present — check the current class declaration; if it's `class TransactionDeleteView(BossRequiredMixin, View):`, leave as-is (`BossRequiredMixin.test_func` already checks `is_authenticated`).

- [ ] **Step 5: Run tests again**

Run: `python manage.py test finance.tests.DeleteViewsRequirePostTests -v 2`
Expected: `OK` (3 tests).

- [ ] **Step 6: Run the full suite**

Run: `python manage.py test finance -v 2`
Expected: all `OK`.

- [ ] **Step 7: Commit**

```bash
git add finance/views/accounts.py finance/tests.py
git commit -m "fix: require POST for destructive delete actions; block deleting boss users"
```

**Note for Phase C:** every template with a delete link (`edit_tran.html`, `transaction_page.html`, `accounts/user_list.html`) must change that `<a href="{% url '...delete...' %}">` into a small `<form method="post" action="{% url '...delete...' %}">{% csrf_token %}<button ...></button></form>` with a `confirm()` guard on the button's click — Tasks 20/21/22 below cover this.

---

## Task 12: `base.html` — design tokens, Inter, Alpine.js

**Files:**
- Modify: `templates/base.html`

- [ ] **Step 1: Rewrite the file**

```html
<!DOCTYPE html>
<html lang="uz">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Moliyaviy Boshqaruv Tizimi{% endblock %}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js"
        integrity="sha384-l8f0VcPi/M1iHPv8egOnY/15TDwqgbOR1anMIJWvU6nLRgZVLTLSaNqi/TOoT5Fh"
        crossorigin="anonymous" defer></script>
    <style>
        :root {
            --color-bg: #F8FAFC;
            --color-surface: #FFFFFF;
            --color-surface-muted: #F1F5F9;
            --color-border: #E2E8F0;
            --color-text: #0F172A;
            --color-text-muted: #64748B;
            --color-brand: #1E3A8A;
            --color-brand-foreground: #FFFFFF;
            --color-positive: #16A34A;
            --color-positive-bg: #F0FDF4;
            --color-negative: #DC2626;
            --color-negative-bg: #FEF2F2;
            --color-pending: #D97706;
            --color-pending-bg: #FFFBEB;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --color-bg: #0F172A;
                --color-surface: #1B2336;
                --color-surface-muted: #1A1E2F;
                --color-border: #334155;
                --color-text: #F8FAFC;
                --color-text-muted: #94A3B8;
            }
        }
        body { font-family: 'Inter', sans-serif; background: var(--color-bg); color: var(--color-text); }
        .money { font-variant-numeric: tabular-nums; font-family: ui-monospace, 'SFMono-Regular', 'Fira Code', monospace; }
        .fade-in { animation: fadeIn 0.2s ease-in; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
        [x-cloak] { display: none !important; }
    </style>
</head>
<body class="min-h-screen">
{% block content %}{% endblock %}
<script>
    function bulkSelect() {
        return {
            selected: [],
            allSelected: false,
            toggleAll(event) {
                const checked = event.target.checked;
                this.selected = checked
                    ? Array.from(document.querySelectorAll('input[name="report_ids"]')).map(el => el.value)
                    : [];
            },
        };
    }
</script>
</body>
</html>
```

- [ ] **Step 2: Verify it loads with no console errors**

Run the dev server (`python manage.py runserver` or the `run` skill). Open any page in a browser (e.g. `/login/`). Confirm: no red console errors, `window.Alpine` is defined (Alpine loaded), page background/text use the new token colors (inspect computed styles on `<body>`).

- [ ] **Step 3: Commit**

```bash
git add templates/base.html
git commit -m "feat: design tokens, Inter font, Alpine.js in base template"
```

---

## Task 13: Reusable partials — stat card, status badge, select-or-new field, bulk action bar, filter bar

**Files:**
- Create: `templates/partials/_stat_card.html`
- Create: `templates/partials/_status_badge.html`
- Create: `templates/partials/_select_or_new_field.html`
- Create: `templates/partials/_bulk_action_bar.html`
- Create: `templates/partials/_filter_bar.html`

**Interfaces:**
- `_status_badge.html` — include with `status` = `"confirmed"` | `"pending"` | `"income"` | `"expense"`.
- `_stat_card.html` — include with `title` (str), `amounts` (object/dict with `total_uzs`/`total_usd`/`total_rub`/`total_eur`), `status` (passed through to `_status_badge.html`), `tone` = `"positive"` | `"negative"` | `"neutral"`.
- `_select_or_new_field.html` — include with `field` (a bound `ChoiceField` whose choices include `('__new__', ...)`), `new_field` (the paired bound `CharField`), `new_label` (str placeholder).
- `_bulk_action_bar.html` — include inside a `<form x-data="bulkSelect()">` (the `bulkSelect()` Alpine factory lives in `base.html`, Task 12); expects checkboxes elsewhere in the same form named `report_ids` and a header checkbox using `x-model="allSelected" @change="toggleAll($event)"`.
- `_filter_bar.html` — include with `action` (str, usually `request.path`), `date_from`, `date_to`, `search`, `selected_categories` (list of str), `category_options` (`Category` queryset/list).

- [ ] **Step 1: `templates/partials/_status_badge.html`**

```html
{% if status == "confirmed" %}
<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium" style="background: var(--color-positive-bg); color: var(--color-positive);">Tasdiqlangan</span>
{% elif status == "pending" %}
<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium" style="background: var(--color-pending-bg); color: var(--color-pending);">Kutilmoqda</span>
{% elif status == "income" %}
<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium" style="background: var(--color-positive-bg); color: var(--color-positive);">Kirim</span>
{% elif status == "expense" %}
<span class="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium" style="background: var(--color-negative-bg); color: var(--color-negative);">Chiqim</span>
{% endif %}
```

- [ ] **Step 2: `templates/partials/_stat_card.html`**

```html
{% load custom_filters %}
<div class="rounded-xl p-5 border" style="background: var(--color-surface); border-color: var(--color-border);">
    <div class="flex items-center justify-between mb-3">
        <p class="text-sm font-medium" style="color: var(--color-text-muted);">{{ title }}</p>
        {% include "partials/_status_badge.html" with status=status %}
    </div>
    <div class="space-y-1 money text-sm" style="color: {% if tone == 'positive' %}var(--color-positive){% elif tone == 'negative' %}var(--color-negative){% else %}var(--color-text){% endif %};">
        {% if amounts.total_uzs %}<div class="text-lg font-semibold">{{ amounts.total_uzs|format_currency }} so'm</div>{% endif %}
        {% if amounts.total_usd %}<div>{{ amounts.total_usd|format_currency }} $</div>{% endif %}
        {% if amounts.total_rub %}<div>{{ amounts.total_rub|format_currency }} ₽</div>{% endif %}
        {% if amounts.total_eur %}<div>{{ amounts.total_eur|format_currency }} €</div>{% endif %}
    </div>
</div>
```

- [ ] **Step 3: `templates/partials/_select_or_new_field.html`**

```html
<div x-data="{ mode: '{{ field.value|default_if_none:'' }}' === '__new__' ? 'new' : 'select' }">
    <select name="{{ field.html_name }}" x-ref="select" x-show="mode === 'select'"
        @change="mode = $event.target.value === '__new__' ? 'new' : 'select'"
        class="w-full px-3 py-2 border rounded-lg text-sm" style="border-color: var(--color-border);">
        {% for value, label in field.field.choices %}
        <option value="{{ value }}" {% if field.value == value %}selected{% endif %}>{{ label }}</option>
        {% endfor %}
    </select>
    <div x-show="mode === 'new'" class="flex gap-2">
        <input type="text" name="{{ new_field.html_name }}" value="{{ new_field.value|default_if_none:'' }}"
            placeholder="{{ new_label }}" class="flex-1 px-3 py-2 border rounded-lg text-sm" style="border-color: var(--color-border);">
        <button type="button" @click="mode = 'select'; $refs.select.selectedIndex = 0"
            class="px-3 py-2 border rounded-lg text-sm whitespace-nowrap" style="border-color: var(--color-border);">
            Ro'yxatdan tanlash
        </button>
    </div>
    {% if field.errors %}<p class="text-xs mt-1" style="color: var(--color-negative);">{{ field.errors|striptags }}</p>{% endif %}
    {% if new_field.errors %}<p class="text-xs mt-1" style="color: var(--color-negative);">{{ new_field.errors|striptags }}</p>{% endif %}
</div>
```

- [ ] **Step 4: `templates/partials/_bulk_action_bar.html`**

```html
<div class="flex items-center justify-between mb-3 px-4 py-2 rounded-lg" style="background: var(--color-surface-muted);">
    <span class="text-sm" style="color: var(--color-text-muted);" x-text="selected.length + ' ta belgilandi'"></span>
    <button type="submit" :disabled="selected.length === 0" :class="selected.length === 0 ? 'opacity-40 cursor-not-allowed' : ''"
        class="px-4 py-2 rounded-lg text-sm font-medium transition-colors" style="background: var(--color-brand); color: var(--color-brand-foreground);">
        Tasdiqlash
    </button>
</div>
```

- [ ] **Step 5: `templates/partials/_filter_bar.html`**

```html
<form method="get" action="{{ action }}" x-data="{ categoriesOpen: false }" class="space-y-3">
    <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
        <div>
            <label class="block text-xs font-medium mb-1" style="color: var(--color-text-muted);">Boshlanish sanasi</label>
            <input type="date" name="from" value="{{ date_from }}" class="w-full px-3 py-2 border rounded-lg text-sm" style="border-color: var(--color-border);">
        </div>
        <div>
            <label class="block text-xs font-medium mb-1" style="color: var(--color-text-muted);">Tugash sanasi</label>
            <input type="date" name="to" value="{{ date_to }}" class="w-full px-3 py-2 border rounded-lg text-sm" style="border-color: var(--color-border);">
        </div>
        <div class="relative">
            <label class="block text-xs font-medium mb-1" style="color: var(--color-text-muted);">Kategoriya</label>
            <button type="button" @click="categoriesOpen = !categoriesOpen" class="w-full px-3 py-2 border rounded-lg text-sm text-left" style="border-color: var(--color-border);">
                {{ selected_categories|length|default:0 }} tanlangan
            </button>
            <div x-show="categoriesOpen" @click.outside="categoriesOpen = false" x-cloak
                class="absolute z-10 mt-1 w-full rounded-lg border shadow-lg p-2 max-h-56 overflow-y-auto" style="background: var(--color-surface); border-color: var(--color-border);">
                {% for cat in category_options %}
                <label class="flex items-center gap-2 px-2 py-1 text-sm rounded">
                    <input type="checkbox" name="category" value="{{ cat.name }}" {% if cat.name in selected_categories %}checked{% endif %}>
                    {{ cat.name }}
                </label>
                {% endfor %}
            </div>
        </div>
        <div>
            <label class="block text-xs font-medium mb-1" style="color: var(--color-text-muted);">Qidiruv</label>
            <input type="text" name="q" value="{{ search|default:'' }}" placeholder="Operator, kategoriya..." class="w-full px-3 py-2 border rounded-lg text-sm" style="border-color: var(--color-border);">
        </div>
    </div>
    <button type="submit" class="px-4 py-2 rounded-lg text-sm font-medium" style="background: var(--color-brand); color: var(--color-brand-foreground);">
        Filtrlarni qo'llash
    </button>
</form>
```

This one Alpine-driven partial replaces the five separately copy-pasted `applyTransactionFilters()` vanilla-JS functions found across `cashier_home.html`, `dashboard/operator.html` (×2 filter bars), `transaction_page.html`, and `dashboard/boss.html`.

- [ ] **Step 6: Commit**

```bash
git add templates/partials/
git commit -m "feat: reusable design-system partials (stat card, badge, select-or-new, bulk bar, filter bar)"
```

---

## Task 14: `templates/accounts/login.html` redesign

**Files:**
- Modify: `templates/accounts/login.html`

**Requirements (from spec §6 + review findings):**
- Uses the new tokens/Inter via `base.html`. Centered card layout, same 3 fields (`username`, `password`, `shift` select 1/2).
- **Fix the real bug**: the current template never renders `{{ form.errors }}` — a wrong password gives zero feedback. Add `{% if form.non_field_errors %}` (and per-field errors for `username`/`password`) rendered as a visible error banner using `--color-negative`/`--color-negative-bg`.
- Drop the unused `{% load widget_tweaks %}` (confirmed dead by review — no widget-tweaks filter is actually used in this file).
- No JS needed beyond what Alpine/base.html already provides.

- [ ] **Step 1: Rewrite the template** per the requirements above, extending `base.html`, using `--color-*` tokens and Inter (inherited).

- [ ] **Step 2: Manual verification**

Run the dev server. Visit `/login/`. Submit wrong credentials → confirm a visible error message appears (this is the regression check for the bug fix). Submit correct credentials for a seeded user → confirm redirect to the correct role dashboard.

- [ ] **Step 3: Commit**

```bash
git add templates/accounts/login.html
git commit -m "redesign: login page with visible error feedback"
```

---

## Task 15: `templates/dashboard/boss.html` redesign

**Files:**
- Modify: `templates/dashboard/boss.html`

**Context variables available (from `BossDashboardView`, post Tasks 7-8):** `from`, `to`, `type`, `q`, `categories` (list[str]), `category_options` (Category qs), `reports` (DailyReport qs), `stats.confirmed.{income,expense,diff}.total_{uzs,usd,rub,eur}`, `stats.pending.{income,expense,diff}.total_{uzs,usd,rub,eur}`.

**Requirements:**
- Nav bar: keep existing links (Tranzaksiyalar, Foydalanuvchilar, Chiqish) restyled with tokens.
- Stat cards: **six** cards now (was three) — confirmed income/expense/diff via `_stat_card.html` with `status="confirmed"`, plus pending income/expense/diff with `status="pending"`. Keep the existing "edit daily stats" modal (`editDailyStats()`/`change_stat` form) wired to the **confirmed** card values only (pending has nothing to manually correct, per spec §4.3).
- Replace the filter block with `{% include "partials/_filter_bar.html" with action=request.path date_from=from date_to=to search=q selected_categories=categories category_options=category_options %}`. The existing `type` (income/expense/xarajat) select stays as a plain extra `<select name="type">` alongside the filter bar (not part of the shared partial, since it's boss-page-specific) — keep it inside the same `<form method="get">` by putting the type select directly in this page rather than the partial. Since `_filter_bar.html` renders its own `<form>`, the cleanest approach here is: don't `{% include %}` the partial verbatim on this page — instead copy its field markup inline into this page's own single `<form method="get">` (which also contains the `type` select), keeping every field name identical (`from`, `to`, `category`, `q`) so the same querystring contract holds. This is the one page where the filter bar isn't a drop-in include because of the extra `type` field.
- Table: replace the per-row expense "Tasdiqlash" button with the checkbox bulk-confirm pattern (spec §4.4): wrap the table in `<form method="post" action="{% url 'bulk_confirm_reports' %}" x-data="bulkSelect()">{% csrf_token %}<input type="hidden" name="current_qs" value="{{ request.GET.urlencode }}">`, include `_bulk_action_bar.html`, add a header checkbox (`x-model="allSelected" @change="toggleAll($event)"`), and per-row: `{% if report.type != 'income' and not report.is_closed %}<input type="checkbox" name="report_ids" value="{{ report.pk }}">{% endif %}` (income rows never get a boss-side checkbox — boss only confirms expense/xarajat, per the existing business split preserved in `BulkConfirmReportsView`). Replace the status column's per-row form with `{% include "partials/_status_badge.html" with status=report.is_closed|yesno:"confirmed,pending" %}` for income rows, and for expense/xarajat rows keep the pending badge next to the checkbox (both visible — "hech qanday qator yashirilmaydi" per spec §4.7).
- Keep the PDF export (`generatePDF()`/html2pdf) working — same `#invoice` wrapper id. **Cleanup while you're in this file:** the current page loads `html2canvas.min.js` and `jspdf.umd.min.js` individually *and* `html2pdf.bundle.min.js` at the bottom, but only ever calls the bundled `html2pdf()` global — the two individual loads are dead weight (the bundle already includes them). Drop those two `<script>` tags, keep only `html2pdf.bundle.min.js` with SRI: `<script src="https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js" integrity="sha384-Yv5O+t3uE3hunW8uyrbpPW3iw6/5/Y7HitWJBLgqfMoA36NogMmy+8wWZMpn3HWc" crossorigin="anonymous"></script>`.

- [ ] **Step 1: Rewrite the template** per the requirements above.

- [ ] **Step 2: Manual verification**

Run the dev server, log in as boss. Confirm: six stat cards all show correct confirmed/pending numbers (cross-check against `python manage.py shell` calling `compute_money_stats()` directly). Select 2+ categories in the filter, confirm table narrows correctly and stays narrowed after submitting. Check 2+ expense rows, click "Tasdiqlash", confirm both close and the page returns with the same filters still applied (this is the req #6 regression check). Confirm income rows show a badge but no checkbox. PDF export still downloads.

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard/boss.html
git commit -m "redesign: boss dashboard with confirmed/pending stats, multi-category filter, checkbox bulk-confirm"
```

---

## Task 16: `templates/cashier_home.html` redesign

**Files:**
- Modify: `templates/cashier_home.html`

**Context variables available (from `ChiefCashierDashboardView`, post Tasks 7-8):** `from`, `to`, `q`, `categories`, `category_options`, `reports` (income-type DailyReport qs), `stats.confirmed.{income,expense,diff}`, `stats.pending.{income,expense,diff}`, `total.click1/click2/cash.{uzs,usd,rub,eur}`, `clicks` (CLICKS).

**Requirements:**
- **Fix the review-found gap**: render all three confirmed + three pending stat cards (currently only "Qoldiq" is shown) via `_stat_card.html`, same six-card pattern as Task 15.
- Render the `total.cash` card too (currently computed but hidden/commented out) alongside the existing Click1/Click2 cards — three payment-method cards total, all live (unaffected by is_closed, this is the running-balance-per-channel feature, unrelated to confirmed/pending).
- Filter bar: `{% include "partials/_filter_bar.html" with action=request.path date_from=from date_to=to search=q selected_categories=categories category_options=category_options %}`.
- Table: checkbox bulk-confirm for income reports — same pattern as Task 15 but every unconfirmed row gets a checkbox here (cashier confirms income, not boss): `<form method="post" action="{% url 'bulk_confirm_reports' %}" x-data="bulkSelect()">{% csrf_token %}<input type="hidden" name="current_qs" value="{{ request.GET.urlencode }}">`, `_bulk_action_bar.html`, header checkbox, per-row `{% if not report.is_closed %}<input type="checkbox" name="report_ids" value="{{ report.pk }}">{% endif %}`, status badge always visible via `_status_badge.html`.
- Fix the inverted `{% if report.category %}...{% else %}company.name{% endif %}` branch the review flagged — since this view only ever shows `type='income'` reports, just render `report.operator.company.name` directly (drop the dead `report.category` branch).
- Keep PDF export working (`#invoice` wrapper, same SRI'd `html2pdf.bundle.min.js` script tag as Task 15 — see Global Constraints for the exact hash).

- [ ] **Step 1: Rewrite the template** per the requirements above.

- [ ] **Step 2: Manual verification**

Run the dev server, log in as cashier. Confirm all six stat cards + three payment-method cards render with real numbers. Check several income rows, bulk-confirm, confirm filters survive the redirect. Confirm company name always shows correctly in the table (regression check for the inverted-branch fix).

- [ ] **Step 3: Commit**

```bash
git add templates/cashier_home.html
git commit -m "redesign: cashier dashboard with full confirmed/pending stats and checkbox bulk-confirm"
```

---

## Task 17: `templates/dashboard/operator.html` redesign

**Files:**
- Modify: `templates/dashboard/operator.html`

**Context variables available (post Task 6):** `clicks`, `total.click1/click2/cash.*`, `form` (`TransactionFrom`, now with `counterparty`/`other_counterparty` DB-backed picklist), `report_date`, `counterparties` (renamed from `persons` — `Counterparty` qs; only needed if you render the list yourself instead of using `form.counterparty` — normally you just render the bound form field), `reports` (last 3), `my_transactions`, `from`, `to`, `q`, `request.session.shift`.

**Requirements:**
- Replace the `counterparty`/`other_counterparty` pair (currently plain `<select>` + JS `seeWho()` toggle) with `{% include "partials/_select_or_new_field.html" with field=form.counterparty new_field=form.other_counterparty new_label="Yangi shaxs nomi" %}` — this is req #2, and it retires the `seeWho()` function.
- Drop the dead `{{ form.counterparty.option }}` expression (review-flagged, not a real Django API, currently renders nothing).
- Replace `{{ transaction.get_counterparty_display }}` in the transactions table with `{{ transaction.counterparty }}` (the model's `choices=PERSONS` is gone as of Task 1 — historical values were normalized to human labels in Task 2's migration, so the raw field value is already correct to display).
- Keep `changePaymentType()`'s behavior (payment_type→click select toggle) but reimplement with Alpine `x-show` scoped to the add-transaction form's own `x-data`, instead of a global `onchange` handler touching `#click` by id.
- Filter bar on "Mening Tranzaksiyalarim": keep a minimal from/to/q form styled with the new tokens — **don't** pull in `_filter_bar.html`'s category-chip UI here (no category concept applies to an operator's own income transactions; the spec never asked for it — YAGNI).
- Fix the review-found filter-loss bug on the "last 3 reports" date-picker: its `onchange="window.location.href = ...` currently replaces the full querystring, dropping `from`/`to`/`q`. Change it to merge: read `window.location.search` into a `URLSearchParams`, `.set('report_date', newValue)`, then navigate — same fix shape as the existing (correct) `applyTransactionFilters()` pattern, just applied to this one control too.
- No checkbox/bulk-confirm on this page — operator never confirms their own transactions (unchanged).
- Preserve the existing `'OPT' in request.user.username` conditional hiding of the Click1 card exactly as-is (out of scope to change — flagged by review but not one of the 7 requirements; don't touch this business rule).
- Keep `generatePDF()` working (same `#div1`/`#div2` wrapper it already uses), and use the same SRI'd `html2pdf.bundle.min.js` script tag as Task 15 (drop any individual `html2canvas`/`jspdf` loads here too, if present).

- [ ] **Step 1: Rewrite the template** per the requirements above.

- [ ] **Step 2: Manual verification**

Run the dev server, log in as operator. Add a transaction picking an existing counterparty from the select → confirm it saves. Add another transaction, click the "+" toggle, type a brand-new name → confirm it saves, then reload the page and confirm the new name now appears in the select (this is the req #2 regression check — should match `OperatorCounterpartyFormTests` from Task 6). Change the report-date picker while `from`/`to`/`q` filters are set → confirm they survive the navigation (regression check for the flagged bug). Confirm payment_type→click toggle still works without a full page reload.

- [ ] **Step 3: Commit**

```bash
git add templates/dashboard/operator.html
git commit -m "redesign: operator dashboard with persisted counterparty picklist"
```

---

## Task 18: `templates/expenses_page.html` redesign

**Files:**
- Modify: `templates/expenses_page.html`

**Context variables available (post Task 5):** `form` (`ExpenseForm`, exposes `form.category_options` — `list[{'name','group'}]` — and fields `exp_type`, `category`, `new_category`, `amount_*`, `payment_type`, `click`, `description`), `reports` (DailyReport qs for the selected date), `date`, `clicks`.

**Requirements:**
- Replace the entire hardcoded `exp_options`/`xar_options` JS + `changeCategories()`/`toggleCustomDescription()` machinery with: an Alpine `x-data` on the form root holding `expType` (bound to the `exp_type` select) and using `form.category_options` (rendered into the page via Django's `json_script` filter: `{{ form.category_options|json_script:"category-options-data" }}`, read in `x-init` via `JSON.parse(document.getElementById('category-options-data').textContent)`) to filter which `<option>`s are visible/enabled for the `category` select based on `expType` (`group === expType`). Use `_select_or_new_field.html`'s `mode: 'select'|'new'` convention for the "+" new-category flow, but since this field is also group-filtered, adapt the partial's markup inline here rather than a bare `{% include %}` (the partial doesn't know about groups).
- Keep the existing whole-number-only input handler on `amount_*` number inputs (blocks typing `.`) — this is a real business constraint (staff enter whole currency units), independent of the backend precision fix in Task 9 (that fix prevents *silent truncation of programmatically-computed sums*, e.g. `_recalc_report`; it does not change what a human is allowed to type into the form).
- Keep `description` as a genuinely separate free-text note field (no longer double-used as a fallback category name — Task 5 already removed that legacy branch on the backend, so nothing special needed here beyond a normal textarea).
- List side: each report shows category, date, payment breakdown, and `_status_badge.html` with `status="confirmed"` or `status="pending"` per `report.is_closed` — no confirm button here (expense confirmation happens on the boss dashboard, Task 15, unchanged).

- [ ] **Step 1: Rewrite the template** per the requirements above.

- [ ] **Step 2: Manual verification**

Run the dev server, log in as cashier. Add an expense picking `exp_type='expense'`, confirm only the 5 expense-group categories are selectable. Switch to `exp_type='xarajat'`, confirm only the 3 xarajat-group categories show. Use "+" to add a brand-new category under each group, confirm it saves and (reload) reappears filtered under the correct group next time (regression check for req #1 + the group-awareness fix). Confirm typing `.` in an amount field is still blocked.

- [ ] **Step 3: Commit**

```bash
git add templates/expenses_page.html
git commit -m "redesign: expenses page with group-aware persisted category picklist"
```

---

## Task 19: `templates/incomes_page.html` redesign

**Files:**
- Modify: `templates/incomes_page.html`

**Context variables available (post Task 6):** `form` (`IncomeForm`, field renamed `counterparty` — was `countryparty`), `reports`, `date`, `choices` (`IncomeCHoices`, unchanged static list), `clicks`.

**Requirements:**
- Update the `<select>`'s `name` attribute from `countryparty` to `counterparty` (matches the Task 6 form rename) — this is the one required functional change on this page besides the visual refresh.
- Per spec §4.2's scope note: this page's "Kategoriya" select (`IncomeCHoices`: Almashdi / Vozvrat rasx den / Boshqa) stays a **static** list, not converted to the `Category`/`Counterparty` DB-backed pattern — only `expenses_page.html` and `dashboard/operator.html` get that treatment. Keep the simple `toggleCustomDescription()`-equivalent (reimplemented in Alpine `x-show`, same as elsewhere) for the "Boshqa" → text-input swap on this fixed 3-option list.
- List side: same status-badge pattern as Task 18 (`confirmed`/`pending`, no confirm button here — income confirmation happens on the cashier dashboard, Task 16).

- [ ] **Step 1: Rewrite the template** per the requirements above.

- [ ] **Step 2: Manual verification**

Run the dev server, log in as cashier. Submit the income form with an invalid amount (e.g. leave a required field blank) → confirm you now see an error message and stay on the page with your other field values intact (regression check for the Task 6 silent-failure fix — previously this redirected with zero feedback). Submit a valid income → confirm it saves and appears in the list with the correct status badge.

- [ ] **Step 3: Commit**

```bash
git add templates/incomes_page.html
git commit -m "redesign: incomes page, fix counterparty field name"
```

---

## Task 20: `templates/transaction_page.html` redesign

**Files:**
- Modify: `templates/transaction_page.html`

**Context variables available (post Task 8):** `transactions` (Transaction qs), `total_usd/uzs/rub/eur` (previously dead — now render these as a small summary row/cards, closing that gap), `from`, `to`, `q`, `categories`, `category_options`.

**Requirements:**
- Replace the filter bar with `{% include "partials/_filter_bar.html" with action=request.path date_from=from date_to=to search=q selected_categories=categories category_options=category_options %}` — this is the req #5 multi-category filter landing on a page that had none before.
- Fix `{{ transaction.get_counterparty_display }}` → `{{ transaction.counterparty }}` (same reasoning as Task 17).
- Fix the broken `generatePDF()` (currently references nonexistent `#div1`/`#div2`, copy-pasted from operator.html): wrap the page's main content in `<div id="invoice">` and point `html2pdf().from(...)` at it, matching the working pattern already used in `boss.html`/`cashier_home.html`, including the same SRI'd `html2pdf.bundle.min.js` script tag (Global Constraints has the exact hash).
- Delete the dead copy-pasted `changePaymentType()`/`seeWho()` script blocks entirely (confirmed by review: no matching elements exist on this page, they only throw console noise).
- Convert the row-level delete link to the POST-form pattern required by Task 11: `<form method="post" action="{% url 'transaction_delete' transaction.pk %}" onsubmit="return confirm('Rostan ham o\'chirmoqchimisiz?')" class="inline">{% csrf_token %}<button type="submit" ...>O'chirish</button></form>`.
- Fix the block title (currently says "Operator Dashboard", copy-paste leftover — should reflect this page, e.g. "Barcha Tranzaksiyalar").
- No checkbox/bulk-confirm needed here — this page lists individual `Transaction` rows (not `DailyReport`s), and confirmation happens at the report level on the boss/cashier dashboards.

- [ ] **Step 1: Rewrite the template** per the requirements above.

- [ ] **Step 2: Manual verification**

Run the dev server, log in as boss. Select 2+ categories in the new filter, confirm the table narrows. Click "Yuklab Olish" (PDF), confirm it now actually downloads a PDF (regression check for the broken-PDF fix). Click delete on a transaction, confirm the browser confirm dialog appears and, on accept, the row is removed (regression check for the GET→POST fix from Task 11) — and confirm a manually-crafted GET request to the delete URL now 405s instead of deleting.

- [ ] **Step 3: Commit**

```bash
git add templates/transaction_page.html
git commit -m "redesign: transaction list with multi-category filter, fix PDF export and dead scripts"
```

---

## Task 21: `templates/edit_tran.html` redesign

**Files:**
- Modify: `templates/edit_tran.html`

**Context variables available:** `transaction`, `clicks`, `choices` (`Transaction.PAYMENT_TYPES`). `persons` is gone (Task 6 dropped it — it was dead in this template already).

**Requirements:**
- Visual refresh only — same fields (amounts, payment_type, click), no functional change to what's editable (per spec §6, confirmed unchanged).
- Convert the delete link to the POST-form pattern (same as Task 20) for `transaction_delete`.
- Remove the dead `onclick="updateTransaction()"` (undefined function, review-flagged) — the submit button just needs `type="submit"`, no onclick needed since it's already inside the edit `<form>`.

- [ ] **Step 1: Rewrite the template** per the requirements above.

- [ ] **Step 2: Manual verification**

Run the dev server, log in as boss, open a transaction's edit page, change an amount, save, confirm it persists and no console errors appear (regression check for removing the dead `onclick`). Confirm delete uses the POST-form pattern.

- [ ] **Step 3: Commit**

```bash
git add templates/edit_tran.html
git commit -m "redesign: transaction edit page"
```

---

## Task 22: `templates/accounts/user_list.html` redesign

**Files:**
- Modify: `templates/accounts/user_list.html`

**Context variables available:** `form` (`UserRegisterForm`), `users`, `operator_count`, `cashier_count`, `transaction_count`.

**Requirements:**
- Visual refresh only — same create-user form, same edit-user modal, same stats mini-cards, same users table.
- Convert the delete link to the POST-form pattern (Task 11's `user_delete`), and hide the delete button/form for `user.role == 'boss'` rows exactly as today (the view now also blocks it server-side as of Task 11 — belt and suspenders, keep both).
- Remove the dead `onclick="createUser()"` and `clearErrorMessages()` references (both undefined functions per review) — forms already submit natively.

- [ ] **Step 1: Rewrite the template** per the requirements above.

- [ ] **Step 2: Manual verification**

Run the dev server, log in as boss. Create a new operator user, confirm it appears in the table. Edit a user's company name via the modal, confirm it saves. Confirm no boss row shows a delete control. Confirm no console errors on page load or modal open/close.

- [ ] **Step 3: Commit**

```bash
git add templates/accounts/user_list.html
git commit -m "redesign: user management page"
```

---

## Task 23: Full manual QA pass (all three roles)

**Files:** none (verification-only task)

- [ ] **Step 1: Run the full automated test suite one more time**

Run: `python manage.py test finance -v 2`
Expected: all tests `OK`.

- [ ] **Step 2: Seed a clean local DB and walk through every role**

Using the dev server (`python manage.py runserver` or the `run` skill):

1. **Boss:** log in, confirm all 6 stat cards show plausible numbers, filter by 2+ categories + date range, submit, refresh the page manually (re-visit the URL) to confirm the filter state round-trips via URL as expected, bulk-confirm 2+ expense reports and confirm the redirect keeps the same filters, export PDF, edit a transaction, delete a transaction (POST-confirm), manage users (create/edit/attempt-delete-boss).
2. **Cashier:** log in, confirm all 6 stat cards + 3 payment-method cards, filter, bulk-confirm 2+ income reports (filters preserved), add an expense with a new category via "+" (group-correct), add one via an existing category, add an income with the countryparty→counterparty fixed field.
3. **Operator:** log in, add a transaction with an existing counterparty, add one with a brand-new counterparty via "+", confirm it appears in the select on next page load, change payment_type to click and confirm the click sub-select appears, change the report-date picker while other filters are set and confirm they're preserved, close the cash register.

- [ ] **Step 3: Check browser console on every page visited above**

No red errors expected (this specifically catches any leftover dead JS references the redesign should have removed).

- [ ] **Step 4: Confirm no accidental unrelated file changes**

Run: `git status` and `git diff --stat main` (or the appropriate base branch) — confirm only `finance/`, `templates/`, `docs/superpowers/` changed.

- [ ] **Step 5: Final commit if anything was fixed during QA**

If QA surfaces a small fix, make it, re-run the relevant test(s), and commit with a `fix:` message describing exactly what QA caught.
