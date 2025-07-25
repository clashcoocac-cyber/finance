from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from finance.models import User


@admin.register(User)
class UserAdminBase(UserAdmin):
    model = User
    fields = ['username', 'role']
    fieldsets = None
