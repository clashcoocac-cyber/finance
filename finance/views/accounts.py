from datetime import datetime
from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView, ListView, DeleteView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum
from finance.forms import UserRegisterForm, UserUpdateForm
from finance.models import User, Company
from finance.models import DailyReport
from finance.mixins import BossRequiredMixin, CashierRequiredMixin, OperatorRequiredMixin
from finance.models import Transaction
from django.db.models import Sum, Case, When, DecimalField, F, Value



# --- DASHBOARDS ---

class BossDashboardView(TemplateView):
    template_name = 'dashboard/boss.html'
    login_url = reverse_lazy('login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['users'] = User.objects.all()
        context['date'] = self.request.GET.get('date', None) or datetime.today().strftime('%Y-%m-%d')
        context['reports'] = DailyReport.objects.filter(date=context['date']).order_by('type')
        
        qs = DailyReport.objects.filter(is_closed=True)

        result = {}

        for currency in ['uzs', 'usd', 'rub', 'uer']:
            income_key = f'total_{currency}_income'
            expense_key = f'total_{currency}_expense'

            aggregated = qs.aggregate(
                **{
                    income_key: Sum(
                        Case(
                            When(type='income', then=F(f'total_{currency}')),
                            default=Value(0),
                            output_field=DecimalField()
                        )
                    ),
                    expense_key: Sum(
                        Case(
                            When(type='expense', then=F(f'total_{currency}')),
                            default=Value(0),
                            output_field=DecimalField()
                        )
                    )
                }
            )

            income = aggregated[income_key] or 0
            expense = aggregated[expense_key] or 0

            result[currency] = {
                'income': income,
                'expense': expense,
                'diff': income - expense
            }
        
        context['stats'] = result
        return context

class ChiefCashierDashboardView(LoginRequiredMixin, CashierRequiredMixin, TemplateView):
    template_name = 'cashier_home.html'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['pending_reports'] = DailyReport.objects.filter(is_closed=False)
        context['approved_reports'] = DailyReport.objects.filter(is_closed=True)
        context['today_transactions'] = Transaction.objects.filter(date__date=self.request.user.last_login.date())
        return context

class OperatorDashboardView(LoginRequiredMixin, OperatorRequiredMixin, TemplateView):
    template_name = 'dashboard/operator.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        context['my_transactions'] = Transaction.objects.filter(operator=user).order_by('-date')[:10]
        context['my_reports'] = DailyReport.objects.filter(operator=user).order_by('-date')[:5]

        queryset = Transaction.objects.filter(
            operator=self.request.user,
        )

        result = {}
        for payment in ['click', 'cash', 'terminal', 'bank']:
            subquery = queryset.filter(payment_type=payment).aggregate(
                usd=Sum('amount_usd'),
                uzs=Sum('amount_uzs'),
                rub=Sum('amount_rub'),
                eur=Sum('amount_eur'),
            )
            result[payment] = subquery
        context['total'] = result
        
        
        return context

# --- AUTH (LOGIN / LOGOUT / REGISTER) ---

class CustomLoginView(LoginView):
    template_name = 'accounts/login.html'

    def form_invalid(self, form):
        messages.error(self.request, "Login yoki parol noto‘g‘ri!")
        return super().form_invalid(form)


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
