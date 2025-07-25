from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLES = [
        ('boss', 'Бошлиқ'),
        ('cashier', 'Главный кассир'),
        ('operator', 'Оператор')
    ]
    role = models.CharField(max_length=20, choices=ROLES)
    company = models.ForeignKey('Company', on_delete=models.CASCADE, null=True)
    created = models.DateField(auto_now_add=True)


class Company(models.Model):
    name = models.CharField(max_length=255)


class Transaction(models.Model):
    TYPES = [
        ('income', 'Kirim'),
        ('expense', 'Chiqim')
    ]
    PAYMENT_TYPES = [
        ('click', 'Click'),
        ('cash', 'Naqd'),
        ('terminal', 'Terminal'),
        ('bank', 'Bank'),
        ('debt', 'Qarz')
    ]
    
    date = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=10, choices=TYPES)
    amount_usd = models.DecimalField(max_digits=15, decimal_places=2)
    amount_uzs = models.DecimalField(max_digits=15, decimal_places=2)
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPES)
    description = models.TextField()
    operator = models.ForeignKey(User, on_delete=models.CASCADE)
    is_approved = models.BooleanField(default=False)


class DailyReport(models.Model):
    date = models.DateField(auto_now_add=True)
    operator = models.ForeignKey(User, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    
    total_cash = models.DecimalField(max_digits=15, decimal_places=2)
    total_click = models.DecimalField(max_digits=15, decimal_places=2)
    total_terminal = models.DecimalField(max_digits=15, decimal_places=2)
    total_bank = models.DecimalField(max_digits=15, decimal_places=2)
    total_debt = models.DecimalField(max_digits=15, decimal_places=2)
    
    is_closed = models.BooleanField(default=False)
    approved_by = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='approved_reports',
        null=True
    )    
