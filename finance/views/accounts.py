from datetime import datetime, timedelta
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.db.models import Sum
from finance.forms import UserRegisterForm, UserUpdateForm, TransactionFrom
from finance.models import PERSONS, Stat, StatTypes, User
from finance.models import DailyReport
from finance.mixins import BossRequiredMixin, CashierRequiredMixin, OperatorRequiredMixin
from finance.models import Transaction, CLICKS
from django.db.models import Sum, Q



# --- DASHBOARDS ---

class BossDashboardView(TemplateView):
    template_name = 'dashboard/boss.html'
    login_url = reverse_lazy('login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['from'] = self.request.GET.get('from', None) or datetime.today().strftime('%Y-%m-%d')
        context['to'] = self.request.GET.get('to', None) or datetime.today().strftime('%Y-%m-%d')
        context['type'] = self.request.GET.get('type', None)
        context['q'] = self.request.GET.get('q', None)
        reports = DailyReport.objects.all()
        if context['from']:
            date_from = datetime.strptime(context['from'], '%Y-%m-%d').date()
            reports = reports.filter(date__gte=date_from)
        if context['to']:
            date_to = datetime.strptime(context['to'], '%Y-%m-%d').date()
            reports = reports.filter(date__lte=date_to)
        if context['type']:
            reports = reports.filter(type=context['type'])
        if context['q']:
            reports = reports.filter(
                Q(operator__username__icontains=context['q']) |
                Q(operator__company__name__icontains=context['q']) |
                Q(category__icontains=context['q'])
            )

        context['reports'] = reports.order_by('-date')
        
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
        inc_stat, _ = Stat.objects.get_or_create(type=StatTypes.INCOME)
        inc_stat.total_uzs = (income_stats['total_uzs'] or 0) - inc_stat.default_uzs
        inc_stat.total_usd = (income_stats['total_usd'] or 0) - inc_stat.default_usd
        inc_stat.total_rub = (income_stats['total_rub'] or 0) - inc_stat.default_rub
        inc_stat.total_eur = (income_stats['total_eur'] or 0) - inc_stat.default_eur
        inc_stat.save()

        expense_qs = DailyReport.objects.filter(type='expense', is_closed=True)
        expense_stats = expense_qs.aggregate(
            total_usd=Sum('total_usd'),
            total_uzs=Sum('total_uzs'),
            total_rub=Sum('total_rub'),
            total_eur=Sum('total_uer')  # e'tibor bering: bu yerda `total_uer` yozilgan
        )
        expense_stat, _ = Stat.objects.get_or_create(type=StatTypes.EXPENSE)
        expense_stat.total_uzs = (expense_stats['total_uzs'] or 0) - expense_stat.default_uzs
        expense_stat.total_usd = (expense_stats['total_usd'] or 0) - expense_stat.default_usd
        expense_stat.total_rub = (expense_stats['total_rub'] or 0) - expense_stat.default_rub
        expense_stat.total_eur = (expense_stats['total_eur'] or 0) - expense_stat.default_eur
        expense_stat.save()

        diff_stats = {
            'usd': (income_stats['total_usd'] or 0) - (expense_stats['total_usd'] or 0),
            'uzs': (income_stats['total_uzs'] or 0) - (expense_stats['total_uzs'] or 0),
            'rub': (income_stats['total_rub'] or 0) - (expense_stats['total_rub'] or 0),
            'eur': (income_stats['total_eur'] or 0) - (expense_stats['total_eur'] or 0),
        }
        diff_stat, _ = Stat.objects.get_or_create(type=StatTypes.BALANCE)
        diff_stat.total_uzs = int(diff_stats['uzs']) - diff_stat.default_uzs
        diff_stat.total_usd = int(diff_stats['usd']) - diff_stat.default_usd
        diff_stat.total_rub = int(diff_stats['rub']) - diff_stat.default_rub
        diff_stat.total_eur = int(diff_stats['eur']) - diff_stat.default_eur
        diff_stat.save()

        context['stats'] = {
            'income': inc_stat,
            'expense': expense_stat,
            'diff': diff_stat
        }
        
        return context


class ChiefCashierDashboardView(LoginRequiredMixin, CashierRequiredMixin, TemplateView):
    template_name = 'cashier_home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['from'] = self.request.GET.get('from', None) or datetime.today().strftime('%Y-%m-%d')
        context['to'] = self.request.GET.get('to', None) or datetime.today().strftime('%Y-%m-%d')
        context['q'] = self.request.GET.get('q', None)

        reports = DailyReport.objects.filter(type='income')
        if context['from']:
            date_from = datetime.strptime(context['from'], '%Y-%m-%d').date()
            reports = reports.filter(date__gte=date_from)
        if context['to']:
            date_to = datetime.strptime(context['to'], '%Y-%m-%d').date() + timedelta(days=1)
            reports = reports.filter(date__lte=date_to)
        if context['q']:
            reports = reports.filter(
                Q(operator__username__icontains=context['q']) |
                Q(operator__company__name__icontains=context['q']) |
                Q(category__icontains=context['q'])
            )
        context['reports'] = reports.order_by('-date')
        
        queryset = Transaction.objects.filter(
            report__is_closed=True, date__date__range=(context['from'], context['to'])
        )

        result = {}
        for payment in ['click', 'cash']:
            if payment is not 'click':
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
        inc_stat, _ = Stat.objects.get_or_create(type=StatTypes.INCOME)
        inc_stat.total_uzs = (income_stats['total_uzs'] or 0) - inc_stat.default_uzs
        inc_stat.total_usd = (income_stats['total_usd'] or 0) - inc_stat.default_usd
        inc_stat.total_rub = (income_stats['total_rub'] or 0) - inc_stat.default_rub
        inc_stat.total_eur = (income_stats['total_eur'] or 0) - inc_stat.default_eur
        inc_stat.save()

        expense_qs = DailyReport.objects.filter(type='expense', is_closed=True)
        expense_stats = expense_qs.aggregate(
            total_usd=Sum('total_usd'),
            total_uzs=Sum('total_uzs'),
            total_rub=Sum('total_rub'),
            total_eur=Sum('total_uer')  # e'tibor bering: bu yerda `total_uer` yozilgan
        )
        expense_stat, _ = Stat.objects.get_or_create(type=StatTypes.EXPENSE)
        expense_stat.total_uzs = (expense_stats['total_uzs'] or 0) - expense_stat.default_uzs
        expense_stat.total_usd = (expense_stats['total_usd'] or 0) - expense_stat.default_usd
        expense_stat.total_rub = (expense_stats['total_rub'] or 0) - expense_stat.default_rub
        expense_stat.total_eur = (expense_stats['total_eur'] or 0) - expense_stat.default_eur
        expense_stat.save()

        diff_stats = {
            'usd': (income_stats['total_usd'] or 0) - (expense_stats['total_usd'] or 0),
            'uzs': (income_stats['total_uzs'] or 0) - (expense_stats['total_uzs'] or 0),
            'rub': (income_stats['total_rub'] or 0) - (expense_stats['total_rub'] or 0),
            'eur': (income_stats['total_eur'] or 0) - (expense_stats['total_eur'] or 0),
        }
        diff_stat, _ = Stat.objects.get_or_create(type=StatTypes.BALANCE)
        diff_stat.total_uzs = int(diff_stats['uzs']) - diff_stat.default_uzs
        diff_stat.total_usd = int(diff_stats['usd']) - diff_stat.default_usd
        diff_stat.total_rub = int(diff_stats['rub']) - diff_stat.default_rub
        diff_stat.total_eur = int(diff_stats['eur']) - diff_stat.default_eur
        diff_stat.save()

        context['stats'] = {
            'income': inc_stat,
            'expense': expense_stat,
            'diff': diff_stat
        }
        context['clicks'] = CLICKS
        return context

class OperatorDashboardView(LoginRequiredMixin, OperatorRequiredMixin, TemplateView):
    template_name = 'dashboard/operator.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['from'] = self.request.GET.get('from', None) or datetime.today().strftime('%Y-%m-%d')
        context['to'] = self.request.GET.get('to', None) or datetime.today().strftime('%Y-%m-%d')
        context['q'] = self.request.GET.get('q', None)

        user = self.request.user
        my_transactions = Transaction.objects.filter(operator=user)
        if context['from']:
            date_from = datetime.strptime(context['from'], '%Y-%m-%d').date()
            my_transactions = my_transactions.filter(date__gte=date_from)
        if context['to']:
            date_to = datetime.strptime(context['to'], '%Y-%m-%d').date() + timedelta(days=1)
            my_transactions = my_transactions.filter(date__lte=date_to)
        if context['q']:
            my_transactions = my_transactions.filter(
                Q(counterparty__icontains=context['q']) |
                Q(description__icontains=context['q'])
            )
        context['my_transactions'] = my_transactions.order_by('-date')
        context['reports'] = DailyReport.objects.filter(operator=user).order_by('-date')[:3]
        context['persons'] = PERSONS

        queryset = Transaction.objects.filter(
            operator=self.request.user, date__date__range=(context['from'], context['to'])
        )

        result = {}
        for payment in ['click', 'cash']:
            if payment is not 'click':
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
        print(request.POST)
        user = User.objects.filter(id=request.POST.get('user_id')).first()
        form = UserUpdateForm(request.POST, instance=user)

        if form.is_valid():
            form.save()
            return redirect(self.success_url)

        return redirect(self.success_url)
    



class UserDeleteView(BossRequiredMixin, DeleteView):
    model = User
    success_url = reverse_lazy('users')

    def get(self, request, *args, **kwargs):
        return super().delete(request, *args, **kwargs)


class HomeView(View):
    def get(self, request):
        if request.user.is_authenticated:
            if request.user.role == 'boss':
                return redirect('boss_dashboard')
            elif request.user.role == 'cashier':
                return redirect('cashier_dashboard')
            elif request.user.role == 'operator':
                return redirect('operator_dashboard')
        return redirect('login')
    

class TransactionView(LoginRequiredMixin, BossRequiredMixin, View):
    template_name = 'edit_tran.html'

    def get(self, request, pk, *args, **kwargs):
        transaction = Transaction.objects.filter(pk=pk).first()
        if not transaction:
            return redirect('transaction_list')

        form = TransactionFrom(instance=transaction)
        context = {
            'form': form,
            'transaction': transaction,
            'persons': PERSONS,
            'clicks': CLICKS,
            'choices': Transaction.PAYMENT_TYPES,
        }
        return render(request, self.template_name, context)
    
    def post(self, request, pk, *args, **kwargs):
        transaction = Transaction.objects.filter(pk=pk).first()
        if not transaction:
            return redirect('transaction_list')

        data = request.POST.copy()
        transaction = Transaction.objects.filter(pk=pk).first()
        transaction.payment_type = data.get('payment_type')
        transaction.click = data.get('click') or None
        transaction.amount_usd = int(data.get('amount_usd', 0) or 0) or None
        transaction.amount_uzs = int(data.get('amount_uzs', 0) or 0) or None
        transaction.amount_rub = int(data.get('amount_rub', 0) or 0) or None
        transaction.amount_eur = int(data.get('amount_eur', 0) or 0) or None
        transaction.save()
        return redirect('transaction_list')
