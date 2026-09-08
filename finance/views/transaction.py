from collections import defaultdict
from datetime import datetime, date, timedelta
from decimal import Decimal
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView, ListView, DeleteView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.http import HttpResponseForbidden
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum, Q
from finance.forms import ExpenseForm, TransactionFrom, IncomeForm
from finance.models import User, Company, Category
from finance.models import DailyReport, CLICKS
from finance.mixins import BossRequiredMixin, CashierRequiredMixin, OperatorRequiredMixin
from finance.models import Transaction, Stat
from finance.views.helpers import preserve_filters, raw_confirmed_totals


class OperatorTransactionsView(LoginRequiredMixin, OperatorRequiredMixin, View):
    """Operator's own transaction list, with the add-transaction modal form."""

    template_name = 'dashboard/operator_transactions.html'

    def get(self, request, *args, **kwargs):
        return self._render(request)

    def _render(self, request, form=None):
        report_date = request.GET.get('report_date') or datetime.today().strftime('%Y-%m-%d')
        date_from = request.GET.get('from') or report_date
        date_to = request.GET.get('to') or report_date
        q = request.GET.get('q') or ''
        counterparty = request.GET.get('counterparty') or ''
        payment_type = request.GET.get('payment_type') or ''

        my_transactions = Transaction.objects.filter(operator=request.user).filter(
            date__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date(),
            date__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date(),
        )
        if q:
            my_transactions = my_transactions.filter(
                Q(counterparty__icontains=q) | Q(description__icontains=q)
            )
        if counterparty:
            my_transactions = my_transactions.filter(counterparty__icontains=counterparty)
        if payment_type:
            my_transactions = my_transactions.filter(payment_type=payment_type)

        context = {
            'form': form or TransactionFrom(),
            'my_transactions': my_transactions.select_related('report').order_by('-date'),
            # Transactions not yet bundled into a daily report: exactly what
            # "Kassani yopish" will send to the cashier for this date.
            'unreported_count': Transaction.objects.filter(
                operator=request.user,
                report__isnull=True,
                date__date=datetime.strptime(report_date, '%Y-%m-%d').date(),
            ).count(),
            'report_date': report_date,
            'from': date_from,
            'to': date_to,
            'q': q,
            'counterparty': counterparty,
            'payment_type': payment_type,
            'clicks': CLICKS,
        }
        return render(request, self.template_name, context)


class TransactionCreateView(LoginRequiredMixin, OperatorRequiredMixin, View):
    success_url = reverse_lazy('operator_transactions')

    def post(self, request, *args, **kwargs):
        form = TransactionFrom(request.POST)
        date_param = request.GET.get('report_date', None) or datetime.today().date().strftime('%Y-%m-%d')

        if form.is_valid():
            form.save(operator=request.user, date=date_param)
            messages.success(request, "Amaliyot qo'shildi.")
            return redirect(str(self.success_url) + '?report_date=' + date_param)

        messages.error(request, "Formani tekshiring.")
        return OperatorTransactionsView()._render(request, form=form)


class BulkConfirmReportsView(LoginRequiredMixin, View):
    success_url_boss = reverse_lazy('boss_reports')
    success_url_cashier = reverse_lazy('cashier_reports')

    def post(self, request, *args, **kwargs):
        if request.user.is_boss:
            allowed_types = ['expense', 'xarajat']
            success_url = str(self.success_url_boss)
        elif request.user.is_cashier:
            allowed_types = ['income']
            success_url = str(self.success_url_cashier)
        else:
            return HttpResponseForbidden()

        report_ids = request.POST.getlist('report_ids')
        if report_ids:
            DailyReport.objects.filter(pk__in=report_ids, type__in=allowed_types).update(is_closed=True)
            messages.success(request, "Tanlangan hisobotlar tasdiqlandi.")

        return redirect(preserve_filters(request, success_url))


class CloseCashRegister(LoginRequiredMixin, OperatorRequiredMixin, View):
    success_url = reverse_lazy('operator_reports')

    def post(self, request, *args, **kwargs):
        user = request.user
        report_date_str = request.GET.get('report_date', None) or datetime.today().date().strftime('%Y-%m-%d')
        shift = request.session.get('shift', None)

        try:
            selected_date = datetime.strptime(report_date_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            selected_date = datetime.today().date()

        # Collect unreported transactions for this operator on the selected date only
        unreported = list(
            Transaction.objects.filter(
                operator=user, 
                report__isnull=True,
                date__date=selected_date
            ).order_by('-date')
        )

        if not unreported:
            return redirect(self.success_url + f'?report_date={report_date_str}')

        # One report per operator per day, full stop — "Kassani yopish" bundles
        # every transaction from the day into a single report, regardless of
        # which shift was active in the session when each close happened
        # (operator_shift used to be part of this lookup, which silently
        # created a second report whenever the session's shift value changed
        # or was missing between closes).
        report, created = DailyReport.objects.get_or_create(
            operator=user,
            date=selected_date,
            defaults={'is_closed': False, 'type': 'income', 'operator_shift': shift},
        )

        # If a report already existed and was closed, reopen it so boss can confirm
        if report.is_closed:
            report.is_closed = False

        # Start from existing details if present
        result = {
            'usd': defaultdict(lambda: Decimal('0')),
            'uzs': defaultdict(lambda: Decimal('0')),
            'rub': defaultdict(lambda: Decimal('0')),
            'eur': defaultdict(lambda: Decimal('0')),
        }

        # seed from existing report details
        for k, v in (report.usd_detail or {}).items():
            result['usd'][k] += Decimal(v or 0)
        for k, v in (report.uzs_detail or {}).items():
            result['uzs'][k] += Decimal(v or 0)
        for k, v in (report.rub_detail or {}).items():
            result['rub'][k] += Decimal(v or 0)
        for k, v in (report.eur_detail or {}).items():
            result['eur'][k] += Decimal(v or 0)

        comment_tran = None
        for tx in unreported:
            if not comment_tran and tx.comment:
                comment_tran = tx

            key = tx.click if tx.payment_type == 'click' else tx.payment_type
            result['usd'][key] += Decimal(tx.amount_usd or 0)
            result['uzs'][key] += Decimal(tx.amount_uzs or 0)
            result['rub'][key] += Decimal(tx.amount_rub or 0)
            result['eur'][key] += Decimal(tx.amount_eur or 0)

        # assign transactions to this report
        Transaction.objects.filter(pk__in=[t.pk for t in unreported]).update(report=report)

        if comment_tran:
            report.comment = comment_tran.comment

        report.total_usd = sum(result['usd'].values())
        report.total_uzs = sum(result['uzs'].values())
        report.total_rub = sum(result['rub'].values())
        # set EUR total
        report.total_eur = sum(result['eur'].values())

        report.usd_detail = {k: int(v) for k, v in result['usd'].items()}
        report.uzs_detail = {k: int(v) for k, v in result['uzs'].items()}
        report.rub_detail = {k: int(v) for k, v in result['rub'].items()}
        report.eur_detail = {k: int(v) for k, v in result['eur'].items()}
        report.is_closed = False
        report.save()

        return redirect(self.success_url + f'?report_date={report_date_str}')


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
            'clicks': CLICKS,
            'clicks_map': dict(CLICKS),
        }
        return render(request, self.template_name, context)


class TransactionList(LoginRequiredMixin, BossRequiredMixin, View):
    template_name = 'transaction_page.html'

    def get(self, request, *args, **kwargs):
        date_from = request.GET.get('from', None) or (date.today() - timedelta(days=7)).strftime('%Y-%m-%d')
        date_to = request.GET.get('to', None) or date.today().strftime('%Y-%m-%d')
        search_query = request.GET.get('q', '').strip()

        transactions = Transaction.objects.all().order_by('-date')
        if date_from:
            transactions = transactions.filter(date__gte=datetime.strptime(date_from, '%Y-%m-%d'))
        if date_to:
            transactions = transactions.filter(date__lte=datetime.strptime(date_to, '%Y-%m-%d') + timedelta(days=1))
        if search_query:
            transactions = transactions.filter(
                Q(operator__username__icontains=search_query) |
                Q(operator__company__name__icontains=search_query) |
                Q(report__category__icontains=search_query) |
                Q(counterparty__icontains=search_query)
            )
        categories = request.GET.getlist('category')
        if categories:
            transactions = transactions.filter(report__category__in=categories)

        context = {
            'transactions': transactions,
            'total_usd': transactions.aggregate(Sum('amount_usd'))['amount_usd__sum'] or 0,
            'total_uzs': transactions.aggregate(Sum('amount_uzs'))['amount_uzs__sum'] or 0,
            'total_rub': transactions.aggregate(Sum('amount_rub'))['amount_rub__sum'] or 0,
            'total_eur': transactions.aggregate(Sum('amount_eur'))['amount_eur__sum'] or 0,
            'from': date_from,
            'to': date_to,
            'q': search_query,
            'categories': categories,
            'category_options': Category.objects.filter(is_active=True),
        }
        return render(request, self.template_name, context)


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
