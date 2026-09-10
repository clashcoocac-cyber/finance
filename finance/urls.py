from django.urls import path
from .views.accounts import (
    HomeView,
    BossDashboardView, ChiefCashierDashboardView, OperatorDashboardView, FinancePageView,
    CustomLoginView, CustomLogoutView,
    UserListCreateView, UserUpdateView, UserDeleteView, TransactionView
)
from .views.accounts import TransactionDeleteView
from .views.transaction import (
    TransactionCreateView, OperatorTransactionsView, BulkConfirmReportsView, CloseCashRegister,
    ExpensesPageView, IncomesPageView, TransactionList, ChangeStatView
)
from .views.reports import BossReportsView, CashierReportsView, OperatorReportsView

urlpatterns = [
    # Home
    path('', HomeView.as_view(), name='home'),

    # Auth
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),

    # Dashboards
    path("dashboard/boss/", BossDashboardView.as_view(), name="boss_dashboard"),
    path("dashboard/cashier/", ChiefCashierDashboardView.as_view(), name="cashier_dashboard"),
    path("dashboard/operator/", OperatorDashboardView.as_view(), name="operator_dashboard"),
    path("finance/", FinancePageView.as_view(), name="finance_page"),

    # Profile

    # User management (boss)
    path("users/", UserListCreateView.as_view(), name="users"),
    path('users/update', UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', UserDeleteView.as_view(), name='user_delete'),

    path('transactions/', TransactionList.as_view(), name='transaction_list'),
    path('transactions/<int:pk>', TransactionView.as_view(), name='transaction'),
    path('transactions/<int:pk>/delete/', TransactionDeleteView.as_view(), name='transaction_delete'),
    path('transactions/create/', TransactionCreateView.as_view(), name='transaction_create'),

    # Daily reports (one page per role)
    path('reports/boss/', BossReportsView.as_view(), name='boss_reports'),
    path('reports/cashier/', CashierReportsView.as_view(), name='cashier_reports'),
    path('reports/operator/', OperatorReportsView.as_view(), name='operator_reports'),

    path('my-transactions/', OperatorTransactionsView.as_view(), name='operator_transactions'),

    path('reports/bulk-confirm/', BulkConfirmReportsView.as_view(), name='bulk_confirm_reports'),
    path('cash-register/close/', CloseCashRegister.as_view(), name='close_cash_register'),

    path('expenses/', ExpensesPageView.as_view(), name='expenses_list'),
    path('incomes/', IncomesPageView.as_view(), name='incomes_list'),

    path('stats/', ChangeStatView.as_view(), name='change_stat'),
]