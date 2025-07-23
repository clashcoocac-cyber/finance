from django.shortcuts import render, redirect
from django.views import View
from django.views.generic import TemplateView, ListView, DeleteView, CreateView, UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db.models import Sum
from accounts.forms import UserRegisterForm
from accounts.models import User, Company
from reports.models import DailyReport
from accounts.mixins import BossRequiredMixin, CashierRequiredMixin, OperatorRequiredMixin
from transactions.models import Transaction


# --- DASHBOARDS ---

class BossDashboardView(TemplateView):
    template_name = 'dashboard/boss.html'
    login_url = reverse_lazy('login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['total_income'] = Transaction.objects.filter(type='income').aggregate(total=Sum('amount_uzs'))['total'] or 0
        context['total_expense'] = Transaction.objects.filter(type='expense').aggregate(total=Sum('amount_uzs'))['total'] or 0
        context['companies'] = Company.objects.all()
        context['users'] = User.objects.all()
        context['reports'] = DailyReport.objects.all().order_by('-date')[:10]
        return context

class ChiefCashierDashboardView(LoginRequiredMixin, CashierRequiredMixin, TemplateView):
    template_name = 'dashboard/chief_cashier.html'
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

class RegisterView(TemplateView):
    template_name = 'accounts/register.html'
    def get(self, request):
        form = UserRegisterForm()
        return render(request, self.template_name, {'form': form})
    def post(self, request):
        form = UserRegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, 'Ro‘yxatdan o‘tish muvaffaqiyatli!')
            return redirect('login')
        return render(request, self.template_name, {'form': form})

# --- PROFILE ---

class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = 'accounts/profile.html'
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['user'] = self.request.user
        return context

# --- USER MANAGEMENT (Boss uchun) ---

class UserListView(LoginRequiredMixin, BossRequiredMixin, ListView):
    model = User
    template_name = 'accounts/user_list.html'
    context_object_name = 'users'

    def get_queryset(self):
        return super().get_queryset().order_by('role')


class UserCreateView(LoginRequiredMixin, BossRequiredMixin, CreateView):
    model = User
    form_class = UserRegisterForm
    template_name = 'accounts/user_create.html'
    success_url = reverse_lazy('user_list')


class UserUpdateView(BossRequiredMixin, UpdateView):
    model = User
    form_class = UserRegisterForm
    template_name = "accounts/user_update.html"
    success_url = reverse_lazy('user_list')


class UserDeleteView(BossRequiredMixin, DeleteView):
    model = User
    success_url = reverse_lazy('user_list')

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
