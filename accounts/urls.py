from django.urls import path
from .views import (
    HomeView,
    BossDashboardView, ChiefCashierDashboardView, OperatorDashboardView,
    CustomLoginView, CustomLogoutView, RegisterView,
    ProfileView, UserListView, UserCreateView, UserUpdateView, UserDeleteView
)

urlpatterns = [
    # Home
    path('', HomeView.as_view(), name='home'),

    # Auth
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    path("register/", RegisterView.as_view(), name="register"),

    # Dashboards
    path("dashboard/boss/", BossDashboardView.as_view(), name="boss_dashboard"),
    path("dashboard/chief-cashier/", ChiefCashierDashboardView.as_view(), name="chief_cashier_dashboard"),
    path("dashboard/operator/", OperatorDashboardView.as_view(), name="operator_dashboard"),

    # Profile
    path("profile/", ProfileView.as_view(), name="profile"),

    # User management (boss)
    path("users/", UserListView.as_view(), name="user_list"),
    path("users/create/", UserCreateView.as_view(), name="user_create"),
    path('users/<int:pk>/edit/', UserUpdateView.as_view(), name='user_update'),
    path('users/<int:pk>/delete/', UserDeleteView.as_view(), name='user_delete'),
]