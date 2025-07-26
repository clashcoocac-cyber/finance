from datetime import datetime, date
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView, ListView, DeleteView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum
from finance.forms import TransactionFrom
from finance.models import User, Company
from finance.models import DailyReport
from finance.mixins import BossRequiredMixin, CashierRequiredMixin, OperatorRequiredMixin
from finance.models import Transaction


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
        transactions = Transaction.objects.filter(operator=user, date__date=today)

        report, _ = DailyReport.objects.get_or_create(
            operator=user,
            date=today,
            defaults={'is_closed': False}
        )

        transactions.update(report=report)
        report.total_uzs = transactions.aggregate(Sum('amount_uzs'))['amount_uzs__sum'] or 0
        report.total_usd = transactions.aggregate(Sum('amount_usd'))['amount_usd__sum'] or 0
        report.total_rub = transactions.aggregate(Sum('amount_rub'))['amount_rub__sum'] or 0
        report.total_uer = transactions.aggregate(Sum('amount_eur'))['amount_eur__sum'] or 0
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
