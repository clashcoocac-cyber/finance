from django.urls import path
from .views.accounts import (
    HomeView,
    BossDashboardView, ChiefCashierDashboardView, OperatorDashboardView,
    CustomLoginView, CustomLogoutView,
    UserListCreateView, UserUpdateView, UserDeleteView, TransactionView
)
from .views.transaction import (
    TransactionCreateView, ConfirmExpenseView, CloseCashRegister, ConfirmIncomeView,
    ExpensesPageView, IncomesPageView, TransactionList, ChangeStatView
)

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

    # Profile

    # User management (boss)
    path("users/", UserListCreateView.as_view(), name="users"),
    path('users/update', UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', UserDeleteView.as_view(), name='user_delete'),

    path('transactions/', TransactionList.as_view(), name='transaction_list'),
    path('transactions/<int:pk>', TransactionView.as_view(), name='transaction'),
    path('transactions/create/', TransactionCreateView.as_view(), name='transaction_create'),

    path('reports/<int:pk>/confirm/', ConfirmExpenseView.as_view(), name='confirm_expense'),
    path('cash-register/close/', CloseCashRegister.as_view(), name='close_cash_register'),
    path('confirm-income/<int:pk>/', ConfirmIncomeView.as_view(), name='confirm_income'),

    path('expenses/', ExpensesPageView.as_view(), name='expenses_list'),
    path('incomes/', IncomesPageView.as_view(), name='incomes_list'),

    path('stats/', ChangeStatView.as_view(), name='change_stat'),
]