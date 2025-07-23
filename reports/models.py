from django.db import models

from accounts.models import User, Company


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
