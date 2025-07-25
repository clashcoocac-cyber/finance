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
    ]
    
    date = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=10, choices=TYPES)
    amount_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    amount_uzs = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    amount_rub = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    amount_eur = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPES)
    description = models.TextField()
    operator = models.ForeignKey(User, on_delete=models.CASCADE)
    counterparty = models.CharField(max_length=255)
    report = models.ForeignKey('DailyReport', on_delete=models.CASCADE, null=True, blank=True)



class DailyReport(models.Model):
    TYPES = [
        ('income', 'Kirim'),
        ('expense', 'Chiqim')
    ]
    type = models.CharField(max_length=10, choices=TYPES)
    date = models.DateField(auto_now_add=True)
    operator = models.ForeignKey(User, on_delete=models.CASCADE)
    operator_shift = models.IntegerField(null=True, blank=True)
    category = models.CharField(max_length=100)
    
    total_uzs = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_usd = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_rub = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    total_uer = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    uzs_detail = models.JSONField(null=True, blank=True)
    usd_detail = models.JSONField(null=True, blank=True)
    rub_detail = models.JSONField(null=True, blank=True)
    eur_detail = models.JSONField(null=True, blank=True)
    
    is_closed = models.BooleanField(default=False)
   
