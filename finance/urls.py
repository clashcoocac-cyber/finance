from django.urls import path
from .views.accounts import (
    HomeView,
    BossDashboardView, ChiefCashierDashboardView, OperatorDashboardView,
    CustomLoginView, CustomLogoutView,
    ProfileView, UserListCreateView, UserUpdateView, UserDeleteView
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
    path("profile/", ProfileView.as_view(), name="profile"),

    # User management (boss)
    path("users/", UserListCreateView.as_view(), name="users"),
    path('users/<int:pk>/edit/', UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', UserDeleteView.as_view(), name='user_delete'),
]