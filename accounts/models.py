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
