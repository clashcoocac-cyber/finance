from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from finance.models import User, Transaction, DailyReport, Stat, Category, Counterparty


@admin.register(User)
class UserAdminBase(UserAdmin):
    model = User
    fields = ['username', 'role']
    fieldsets = None

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    ...


@admin.register(DailyReport)
class DailyReportAdmin(admin.ModelAdmin):
    ...


@admin.register(Stat)
class StatAdmin(admin.ModelAdmin):
    ...


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'group', 'is_active', 'created']
    list_filter = ['group', 'is_active']
    search_fields = ['name']


@admin.register(Counterparty)
class CounterpartyAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created']
    list_filter = ['is_active']
    search_fields = ['name']
