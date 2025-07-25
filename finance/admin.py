from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from finance.models import User, Transaction, DailyReport


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