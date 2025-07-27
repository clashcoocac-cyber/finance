from collections import defaultdict
from datetime import datetime, date, timedelta
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView, ListView, DeleteView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum, Q
from finance.forms import ExpenseForm, TransactionFrom, IncomeCHoices, IncomeForm
from finance.models import User, Company
from finance.models import DailyReport
from finance.mixins import BossRequiredMixin, CashierRequiredMixin, OperatorRequiredMixin
from finance.models import Transaction, Stat


class TransactionCreateView(LoginRequiredMixin, OperatorRequiredMixin, View):
    template_name = 'dashboard/operator.html'
    success_url = reverse_lazy('operator_dashboard')
    
    def post(self, request, *args, **kwargs):
        form = TransactionFrom(request.POST)
        if form.is_valid():
            form.save(operator=request.user)
            return redirect(self.success_url)
        
        users = User.objects.exclude(role='boss').order_by('role')
        context = {
            'form': form,
            'users': users,
            'operator_count': User.objects.filter(role='operator').count(),
            'cashier_count': User.objects.filter(role='cashier').count(),
        }
        return render(request, self.template_name, context)


class ConfirmExpenseView(LoginRequiredMixin, BossRequiredMixin, View):
    success_url = reverse_lazy('home')

    def post(self, request, pk, *args, **kwargs):
        report = DailyReport.objects.filter(id=pk).first()
        report.is_closed = True
        report.save()
        return redirect(self.success_url)


class CloseCashRegister(LoginRequiredMixin, OperatorRequiredMixin, View):
    template_name = 'dashboard/operator.html'
    success_url = reverse_lazy('operator_dashboard')

    def post(self, request, *args, **kwargs):
        user = request.user
        today = date.today()
        transactions = Transaction.objects.filter(operator=user, date__date=today).order_by('-date')
        shift = request.session.get('shift', None)

        report, _ = DailyReport.objects.get_or_create(
            operator=user,
            operator_shift=shift,
            date=today,
            defaults={'is_closed': False},
            type='income'
        )

        transactions.update(report=report)
        comment_tran = transactions.filter(comment__isnull=False).first()
        if comment_tran:
            report.comment = comment_tran.comment

        result = {
        'usd': defaultdict(lambda: 0),
        'uzs': defaultdict(lambda: 0),
        'rub': defaultdict(lambda: 0),
        'eur': defaultdict(lambda: 0),
    }

        for tx in transactions:
            if tx.payment_type == 'click':
                result['usd'][tx.click] += tx.amount_usd or 0
                result['uzs'][tx.click] += tx.amount_uzs or 0
                result['rub'][tx.click] += tx.amount_rub or 0
                result['eur'][tx.click] += tx.amount_eur or 0
            else:
                result['usd'][tx.payment_type] += tx.amount_usd or 0
                result['uzs'][tx.payment_type] += tx.amount_uzs or 0
                result['rub'][tx.payment_type] += tx.amount_rub or 0
                result['eur'][tx.payment_type] += tx.amount_eur or 0

        report.total_usd = sum(result['usd'].values())
        report.total_uzs = sum(result['uzs'].values())
        report.total_rub = sum(result['rub'].values())
        report.total_uer = sum(result['eur'].values()) 

        report.usd_detail = {k: int(v) for k, v in result['usd'].items()}
        report.uzs_detail = {k: int(v) for k, v in result['uzs'].items()}
        report.rub_detail = {k: int(v) for k, v in result['rub'].items()}
        report.eur_detail = {k: int(v) for k, v in result['eur'].items()}
        report.is_closed = False
        report.save()

        return redirect(self.success_url)


class ConfirmIncomeView(LoginRequiredMixin, CashierRequiredMixin, View):
    success_url = reverse_lazy('cashier_dashboard')

    def post(self, request, pk, *args, **kwargs):
        report = DailyReport.objects.filter(id=pk).first()
        if report:
            report.is_closed = True
            report.save()
            messages.success(request, "Kirim tasdiqlandi.")
        else:
            messages.error(request, "Kirim topilmadi.")
        return redirect(self.success_url)


class ExpensesPageView(LoginRequiredMixin, CashierRequiredMixin, View):
    template_name = 'expenses_page.html'
    success_url = reverse_lazy('expenses_list')

    def get(self, request, *args, **kwargs):
        context = {}
        report_date = request.GET.get('date', None) or date.today().strftime('%Y-%m-%d')
        reposts = DailyReport.objects.filter(type='expense', date=report_date).order_by('-date')
        context['reports'] = reposts
        context['date'] = report_date
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        form = ExpenseForm(request.POST)
        if form.is_valid():
            form.save(operator=request.user)
            messages.success(request, "Chiqim muvaffaqiyatli qo'shildi.")
            return redirect(self.success_url)
        else:
            messages.error(request, "Chiqim qo'shishda xatolik yuz berdi.")
        return render(request, self.template_name, {'form': form})
    

class IncomesPageView(LoginRequiredMixin, CashierRequiredMixin, View):
    template_name = 'incomes_page.html'
    success_url = reverse_lazy('incomes_list')

    def get(self, request, *args, **kwargs):
        context = {}
        report_date = request.GET.get('date', None) or date.today().strftime('%Y-%m-%d')
        reposts = DailyReport.objects.filter(type='income', operator=request.user, date=report_date).order_by('-date')
        context['reports'] = reposts
        context['date'] = report_date
        context['choices'] = IncomeCHoices
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        form = IncomeForm(request.POST)
        if form.is_valid():
            form.save(operator=request.user)
            return redirect(self.success_url)
        else:
            print(form.errors)
        return redirect(self.success_url)


class TransactionList(LoginRequiredMixin, BossRequiredMixin, View):
    template_name = 'transaction_page.html'

    def get(self, request, *args, **kwargs):
        date_from = request.GET.get('from', None) or date.today().strftime('%Y-%m-%d')
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

        context = {
            'transactions': transactions,
            'total_usd': transactions.aggregate(Sum('amount_usd'))['amount_usd__sum'] or 0,
            'total_uzs': transactions.aggregate(Sum('amount_uzs'))['amount_uzs__sum'] or 0,
            'total_rub': transactions.aggregate(Sum('amount_rub'))['amount_rub__sum'] or 0,
            'total_eur': transactions.aggregate(Sum('amount_eur'))['amount_eur__sum'] or 0,
            'from': date_from,
            'to': date_to,
            'q': search_query
        }
        return render(request, self.template_name, context)


class ChangeStatView(LoginRequiredMixin, BossRequiredMixin, View):
    template_name = 'dashboard/boss.html'
    success_url = reverse_lazy('boss_dashboard')

    def post(self, request, *args, **kwargs):
        stat_type = request.POST.get('stat_type')
        total_uzs = int(request.POST.get('total_uzs', 0))
        total_usd = int(request.POST.get('total_usd', 0))
        total_rub = int(request.POST.get('total_rub', 0))
        total_eur = int(request.POST.get('total_eur', 0))

        stat, _ = Stat.objects.get_or_create(type=stat_type)

        income_qs = Transaction.objects.filter(
            report__is_closed=True,
            payment_type__in=['cash', 'click'],
        )
        income_stats = income_qs.aggregate(
            total_usd=Sum('amount_usd'),
            total_uzs=Sum('amount_uzs'),
            total_rub=Sum('amount_rub'),
            total_eur=Sum('amount_eur')
        )

        expense_qs = DailyReport.objects.filter(type='expense', is_closed=True)
        expense_stats = expense_qs.aggregate(
            total_usd=Sum('total_usd'),
            total_uzs=Sum('total_uzs'),
            total_rub=Sum('total_rub'),
            total_eur=Sum('total_uer')  # e'tibor bering: bu yerda `total_uer` yozilgan
        )

        diff_stats = {
            'total_uzs': (income_stats['total_uzs'] or 0) - (expense_stats['total_uzs'] or 0),
            'total_usd': (income_stats['total_usd'] or 0) - (expense_stats['total_usd'] or 0),
            'total_rub': (income_stats['total_rub'] or 0) - (expense_stats['total_rub'] or 0),
            'total_eur': (income_stats['total_eur'] or 0) - (expense_stats['total_eur'] or 0),
        }

        data = {
            'income': income_stats,
            'expense': expense_stats,
            'diff': diff_stats,
        }
        stat.default_uzs = (data[stat_type]['total_uzs'] or 0) - total_uzs
        stat.default_usd = (data[stat_type]['total_usd'] or 0) - total_usd
        stat.default_rub = (data[stat_type]['total_rub'] or 0) - total_rub
        stat.default_eur = (data[stat_type]['total_eur'] or 0) - total_eur
        stat.save()

        return redirect(self.success_url)
