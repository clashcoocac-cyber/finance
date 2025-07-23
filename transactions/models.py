from django.db import models

from accounts.models import User


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
