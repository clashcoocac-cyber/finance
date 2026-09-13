from datetime import datetime, timedelta
from decimal import Decimal
from django.utils import timezone
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models.functions import Lower
from django.urls import reverse_lazy
from django.db.models import Sum
from django.contrib import messages
from finance.forms import UserRegisterForm, UserUpdateForm, TransactionEditForm, IncomeForm, ExpenseForm
from finance.models import Counterparty, User
from finance.models import DailyReport, Category
from finance.mixins import BossRequiredMixin, CashierRequiredMixin, OperatorRequiredMixin
from finance.models import Transaction, CLICKS
from django.db.models import Sum, Q
from finance.views.helpers import compute_money_stats, date_param



# --- DASHBOARDS ---

class BossDashboardView(LoginRequiredMixin, BossRequiredMixin, TemplateView):
    template_name = 'dashboard/boss.html'
    login_url = reverse_lazy('login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()
        month_start = today.replace(day=1).strftime('%Y-%m-%d')
        context['from'] = date_param(self.request.GET.get('from'), month_start)
        context['to'] = date_param(self.request.GET.get('to'), today.strftime('%Y-%m-%d'))

        date_from = datetime.strptime(context['from'], '%Y-%m-%d').date()
        date_to = datetime.strptime(context['to'], '%Y-%m-%d').date()

        context['stats'] = compute_money_stats(date_from=date_from, date_to=date_to)
        context['operator_count'] = User.objects.filter(role='operator').count()
        context['cashier_count'] = User.objects.filter(role='cashier').count()
        context['transaction_count'] = Transaction.objects.count()
        context['pending_reports_count'] = DailyReport.objects.filter(is_closed=False).count()
        context['recent_reports'] = DailyReport.objects.select_related('operator').order_by('-date')[:5]
        return context


class ChiefCashierDashboardView(LoginRequiredMixin, CashierRequiredMixin, TemplateView):
    template_name = 'cashier_home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()
        month_start = today.replace(day=1).strftime('%Y-%m-%d')
        context['from'] = date_param(self.request.GET.get('from'), month_start)
        context['to'] = date_param(self.request.GET.get('to'), today.strftime('%Y-%m-%d'))

        context['pending_reports_count'] = DailyReport.objects.filter(
            type='income', is_closed=False
        ).count()
        context['recent_reports'] = DailyReport.objects.filter(
            type='income'
        ).select_related('operator').order_by('-date')[:5]

        # parse date range for consistent filtering
        date_from = datetime.strptime(context['from'], '%Y-%m-%d').date()
        date_to = datetime.strptime(context['to'], '%Y-%m-%d').date()

        income_qs = Transaction.objects.filter(
            report__is_closed=True, date__date__range=(date_from, date_to), type='income'
        )
        expense_qs = Transaction.objects.filter(
            report__is_closed=True, date__date__range=(date_from, date_to), type='expense'
        )

        result = {}
        for payment in ['click', 'cash']:
            if payment != 'click':
                income_subquery = income_qs.filter(payment_type=payment).aggregate(
                    usd=Sum('amount_usd'),
                    uzs=Sum('amount_uzs'),
                    rub=Sum('amount_rub'),
                    eur=Sum('amount_eur'),
                )
                expense_subquery = expense_qs.filter(payment_type=payment).aggregate(
                    usd=Sum('amount_usd'),
                    uzs=Sum('amount_uzs'),
                    rub=Sum('amount_rub'),
                    eur=Sum('amount_eur'),
                )
                result[payment] = {
                    'usd': (income_subquery['usd'] or 0) - (expense_subquery['usd'] or 0),
                    'uzs': (income_subquery['uzs'] or 0) - (expense_subquery['uzs'] or 0),
                    'rub': (income_subquery['rub'] or 0) - (expense_subquery['rub'] or 0),
                    'eur': (income_subquery['eur'] or 0) - (expense_subquery['eur'] or 0),
                }
            else:
                for click in CLICKS:
                    income_subquery = income_qs.filter(payment_type=payment, click=click[0]).aggregate(
                        usd=Sum('amount_usd'),
                        uzs=Sum('amount_uzs'),
                        rub=Sum('amount_rub'),
                        eur=Sum('amount_eur'),
                    )
                    expense_subquery = expense_qs.filter(payment_type=payment, click=click[0]).aggregate(
                        usd=Sum('amount_usd'),
                        uzs=Sum('amount_uzs'),
                        rub=Sum('amount_rub'),
                        eur=Sum('amount_eur'),
                    )
                    result[click[0]] = {
                        'usd': (income_subquery['usd'] or 0) - (expense_subquery['usd'] or 0),
                        'uzs': (income_subquery['uzs'] or 0) - (expense_subquery['uzs'] or 0),
                        'rub': (income_subquery['rub'] or 0) - (expense_subquery['rub'] or 0),
                        'eur': (income_subquery['eur'] or 0) - (expense_subquery['eur'] or 0),
                    }
            
        context['total'] = result

        context['stats'] = compute_money_stats(date_from=date_from, date_to=date_to)
        context['clicks'] = CLICKS
        return context

class FinancePageView(LoginRequiredMixin, TemplateView):
    template_name = 'finance_page.html'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_superuser:
            return super().dispatch(request, *args, **kwargs)
        if not (hasattr(request.user, 'role') and request.user.role in ['boss', 'cashier']):
            return redirect('login')
        return super().dispatch(request, *args, **kwargs)

    FORMS = {'income': (IncomeForm, "Kirim muvaffaqiyatli qo'shildi."),
             'expense': (ExpenseForm, "Chiqim muvaffaqiyatli qo'shildi.")}

    def post(self, request, *args, **kwargs):
        kind = request.POST.get('kind')
        if kind not in self.FORMS:
            return redirect('finance_page')
        form_class, success_msg = self.FORMS[kind]
        form = form_class(request.POST)
        if form.is_valid():
            form.save(operator=request.user)
            messages.success(request, success_msg)
            return redirect('finance_page')
        messages.error(request, "Formani tekshiring.")
        # re-render with the failed modal open, its bound form (values +
        # field errors) inside it
        kwargs['failed_modal'] = kind
        kwargs[f'{kind}_form'] = form
        return self.get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        today = datetime.today()
        month_start = today.replace(day=1).strftime('%Y-%m-%d')
        context['from'] = date_param(self.request.GET.get('from'), month_start)
        context['to'] = date_param(self.request.GET.get('to'), today.strftime('%Y-%m-%d'))

        date_from = datetime.strptime(context['from'], '%Y-%m-%d').date()
        date_to = datetime.strptime(context['to'], '%Y-%m-%d').date()

        def _sum(qs, **extra):
            return qs.filter(**extra).aggregate(
                usd=Sum('amount_usd'), uzs=Sum('amount_uzs'),
                rub=Sum('amount_rub'), eur=Sum('amount_eur'),
            )

        noncash = ['click', 'terminal', 'bank']
        income_qs = Transaction.objects.filter(date__date__range=(date_from, date_to), type='income')
        expense_qs = Transaction.objects.filter(date__date__range=(date_from, date_to), type='expense')

        # split by report confirmation state, like the dashboard does
        noncash_income = _sum(income_qs, report__is_closed=True, payment_type__in=noncash)
        noncash_expense = _sum(expense_qs, report__is_closed=True, payment_type__in=noncash)
        noncash_income_pending = _sum(income_qs, report__is_closed=False, payment_type__in=noncash)
        noncash_expense_pending = _sum(expense_qs, report__is_closed=False, payment_type__in=noncash)

        all_income = _sum(income_qs, report__is_closed=True)
        all_expense = _sum(expense_qs, report__is_closed=True)
        all_income_pending = _sum(income_qs, report__is_closed=False)
        all_expense_pending = _sum(expense_qs, report__is_closed=False)

        cur_keys = ['usd', 'uzs', 'rub', 'eur']

        def _stats(confirmed, pending):
            stats = {
                'income': {f'total_{k}': confirmed['income'].get(k) or 0 for k in cur_keys},
                'expense': {f'total_{k}': confirmed['expense'].get(k) or 0 for k in cur_keys},
            }
            stats['diff'] = {f'total_{k}': stats['income'][f'total_{k}'] - stats['expense'][f'total_{k}'] for k in cur_keys}
            stats['pending'] = {
                'income': {f'total_{k}': pending['income'].get(k) or 0 for k in cur_keys},
                'expense': {f'total_{k}': pending['expense'].get(k) or 0 for k in cur_keys},
            }
            stats['pending']['diff'] = {f'total_{k}': stats['pending']['income'][f'total_{k}'] - stats['pending']['expense'][f'total_{k}'] for k in cur_keys}
            # headline numbers include pending, like the dashboard
            stats['combined'] = {
                key: {f'total_{k}': stats[key][f'total_{k}'] + stats['pending'][key][f'total_{k}'] for k in cur_keys}
                for key in ['income', 'expense', 'diff']
            }
            return stats

        context['noncash_stats'] = _stats(
            {'income': noncash_income, 'expense': noncash_expense},
            {'income': noncash_income_pending, 'expense': noncash_expense_pending},
        )
        context['all_stats'] = _stats(
            {'income': all_income, 'expense': all_expense},
            {'income': all_income_pending, 'expense': all_expense_pending},
        )

        context['income_counterparties'] = Counterparty.objects.filter(is_active=True, group='income')
        context['expense_category_options'] = [
            {'name': c.name, 'group': c.group} for c in Category.objects.filter(is_active=True)
        ]
        context['clicks'] = CLICKS
        context['failed_modal'] = kwargs.get('failed_modal')
        context['income_form'] = kwargs.get('income_form')
        context['expense_form'] = kwargs.get('expense_form')
        return context


class OperatorDashboardView(LoginRequiredMixin, OperatorRequiredMixin, TemplateView):
    template_name = 'dashboard/operator.html'

    def get_context_data(self, **kwargs):
        report_date = date_param(self.request.GET.get('report_date'), datetime.today().strftime('%Y-%m-%d'))
        context = super().get_context_data(**kwargs)
        context['from'] = date_param(self.request.GET.get('from'), report_date)
        context['to'] = date_param(self.request.GET.get('to'), report_date)
        context['q'] = self.request.GET.get('q', None)
        context['report_date'] = report_date
        context['is_expired'] = timezone.localdate() - datetime.strptime(report_date, '%Y-%m-%d').date() > timedelta(days=3)

        user = self.request.user
        context['reports'] = DailyReport.objects.filter(operator=user).order_by('-date')[:5]
        context['today_transaction_count'] = Transaction.objects.filter(
            operator=user, date__date=datetime.strptime(report_date, '%Y-%m-%d').date()
        ).count()
        context['unreported_count'] = Transaction.objects.filter(
            operator=user, report__isnull=True,
            date__date=datetime.strptime(report_date, '%Y-%m-%d').date(),
        ).count()

        queryset = Transaction.objects.filter(
            operator=self.request.user, date__date__range=(context['from'], context['to'])
        )

        result = {}
        for payment in ['click', 'cash']:
            if payment != 'click':
                subquery = queryset.filter(payment_type=payment).aggregate(
                    usd=Sum('amount_usd'),
                    uzs=Sum('amount_uzs'),
                    rub=Sum('amount_rub'),
                    eur=Sum('amount_eur'),
                )
                result[payment] = subquery
            else:
                for click in CLICKS:
                    subquery = queryset.filter(payment_type=payment, click=click[0]).aggregate(
                        usd=Sum('amount_usd'),
                        uzs=Sum('amount_uzs'),
                        rub=Sum('amount_rub'),
                        eur=Sum('amount_eur'),
                    )
                    result[click[0]] = subquery
            
        context['total'] = result
        context['clicks'] = CLICKS
        return context

# --- AUTH (LOGIN / LOGOUT / REGISTER) ---

class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'

    def post(self, request, *args, **kwargs):
        shift = request.POST.get('shift', None)
        if shift:
            request.session['shift'] = shift
        return super().post(request, *args, **kwargs)


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('login')
    http_method_names = ['get', 'post']

    def get(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)

class UserListCreateView(LoginRequiredMixin, BossRequiredMixin, View):
    template_name = 'accounts/user_list.html'
    success_url = reverse_lazy('users')

    def get(self, request, *args, **kwargs):
        form = UserRegisterForm()
        users = User.objects.order_by('role') # .exclude(role='boss')
        context = {
            'form': form,
            'users': users,
            'operator_count': User.objects.filter(role='operator').count(),
            'cashier_count': User.objects.filter(role='cashier').count(),
            'transaction_count': Transaction.objects.count(),
        }
        return render(request, self.template_name, context)
    
    def post(self, request, *args, **kwargs):
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect(self.success_url)
        
        users = User.objects.order_by('role') # .exclude(role='boss')
        context = {
            'form': form,
            'users': users,
            'operator_count': User.objects.filter(role='operator').count(),
            'cashier_count': User.objects.filter(role='cashier').count(),
        }
        return render(request, self.template_name, context)


class UserUpdateView(LoginRequiredMixin, BossRequiredMixin, View):
    success_url = reverse_lazy('users')

    def post(self, request, *args, **kwargs):
        user_id = request.POST.get('user_id') or ''
        user = User.objects.filter(id=user_id).first() if user_id.isdigit() else None
        if not user:
            messages.error(request, "Foydalanuvchi topilmadi.")
            return redirect(self.success_url)
        form = UserUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Foydalanuvchi yangilandi.")
        else:
            messages.error(request, "Formani tekshiring: " + "; ".join(
                f"{field}: {err}" for field, errs in form.errors.items() for err in errs
            ))
        return redirect(self.success_url)
    



class UserDeleteView(LoginRequiredMixin, BossRequiredMixin, View):
    success_url = reverse_lazy('users')

    def post(self, request, *args, **kwargs):
        user = User.objects.filter(pk=kwargs['pk']).first()
        if not user or user.is_boss or user.pk == request.user.pk:
            messages.error(request, "Bu foydalanuvchini o'chirib bo'lmaydi.")
        elif Transaction.objects.filter(operator=user).exists() or DailyReport.objects.filter(operator=user).exists():
            # transactions/reports cascade on delete — keep the history, just
            # lock the account
            user.is_active = False
            user.save(update_fields=['is_active'])
            messages.success(request, f"{user.username} faolsizlantirildi (tranzaksiyalari saqlanadi).")
        else:
            user.delete()
            messages.success(request, f"{user.username} o'chirildi.")
        return redirect(self.success_url)


class HomeView(View):
    def get(self, request):
        if request.user.is_authenticated:
            if request.user.is_cashier:
                return redirect('cashier_dashboard')
            elif request.user.is_operator:
                return redirect('operator_dashboard')
            elif request.user.is_boss:
                return redirect('boss_dashboard')
        return redirect('login')
    

class TransactionView(LoginRequiredMixin, BossRequiredMixin, View):
    template_name = 'edit_tran.html'

    def get(self, request, pk, *args, **kwargs):
        transaction = Transaction.objects.filter(pk=pk).first()
        if not transaction:
            return redirect('transaction_list')

        form = TransactionEditForm(instance=transaction)
        context = {
            'form': form,
            'transaction': transaction,
            'clicks': CLICKS,
            'choices': Transaction.PAYMENT_TYPES,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, pk, *args, **kwargs):
        transaction = Transaction.objects.filter(pk=pk).first()
        if not transaction:
            return redirect('transaction_list')

        form = TransactionEditForm(request.POST, instance=transaction)
        if not form.is_valid():
            messages.error(request, "Formani tekshiring.")
            return render(request, self.template_name, {
                'form': form, 'transaction': transaction,
                'clicks': CLICKS, 'choices': Transaction.PAYMENT_TYPES,
            })
        form.save()
        messages.success(request, "Tranzaksiya yangilandi.")
        return redirect('transaction_list')


class TransactionDeleteView(LoginRequiredMixin, BossRequiredMixin, View):
    success_url = reverse_lazy('transaction_list')

    def post(self, request, pk, *args, **kwargs):
        transaction = Transaction.objects.filter(pk=pk).first()
        if not transaction:
            return redirect(self.success_url)

        report = transaction.report
        # the post_delete signal recalculates the report's totals/details from
        # the remaining transactions; a report left with none is removed
        transaction.delete()
        if report and not Transaction.objects.filter(report=report).exists():
            report.delete()
        messages.success(request, "Tranzaksiya o'chirildi.")
        return redirect(self.success_url)
