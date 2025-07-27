from django import forms
from django.contrib.auth.forms import UserChangeForm
from django.shortcuts import redirect
from .models import Company, User, Transaction, DailyReport



class UserRegisterForm(forms.ModelForm):    
    password = forms.CharField(widget=forms.PasswordInput)
    company_name = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['username', 'role', 'company_name', 'password']

    def save(self, commit = True):
        company_name = self.cleaned_data.pop('company_name', '')
        password = self.cleaned_data.pop('password')

        user = super().save(commit=False)
        user.set_password(password)
        
        if company_name:
            company, _ = Company.objects.get_or_create(name=company_name)
            user.company = company
        else:
            user.company = None 

        if commit:
            user.save()
        return user


class UserUpdateForm(UserChangeForm):
    user_id = forms.IntegerField()
    new_password = forms.CharField(widget=forms.PasswordInput, required=False)
    company_name = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['user_id', 'username', 'new_password', 'company_name']

    def save(self, commit = True, **kwargs):
        user = super().save(commit=False)

        print(self.cleaned_data)

        new_password = self.cleaned_data.get('new_password')
        if new_password:
            user.set_password(new_password)

        company_name = self.cleaned_data.get('company_name')

        company, _ = Company.objects.get_or_create(name=company_name)
        user.company = company

        if commit:
            user.save()

        return user


class TransactionFrom(forms.ModelForm):
    other_counterparty = forms.CharField(required=False, max_length=255, label="Boshqa shaxs nomi")

    class Meta:
        model = Transaction
        fields = ['amount_usd' ,'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'click', 'comment', 'counterparty']
        
    def save(self, commit = ..., operator=None):
        transaction = super().save(commit=False)
        if self.cleaned_data['counterparty'] == 'other':
            transaction.counterparty = self.cleaned_data['other_counterparty']
        else:
            transaction.counterparty = self.cleaned_data['counterparty']
        transaction.operator = operator
        if commit:
            transaction.save()
        return transaction
    
CATEGORIES = {
    "expense_day": "Kunlik xarajatlar",
    "chicago_factory": "Chikako zavodi",
    "kvass_wholesale": "Jasur un",
    "emir_tashkent": "Elyor Toshkent",
    "salary_opt": "Oylik OPT",
    "salary_sfb": "Oylik SFB",
    "salary_msb": "Oylik MSB",
    "equipment_purchase_sfb": "Texnika xaridi SFB",
    "equipment_purchase_opt": "Texnika xaridi OPT",
    "exchange_rate_changed": "Almashdi",
    "sfb_suppliers": "SFB yetkazib beruvchilar",
}

IncomeCHoices = [
    ('almashdi', 'Almashdi'),
    ('vozvrat', 'Vozvrat rasx den'),
    ('other', 'Boshqa'),
]

class IncomeForm(forms.ModelForm):
    countryparty = forms.ChoiceField(choices=IncomeCHoices)
    other_counterparty = forms.CharField(required=False, max_length=255, label="Boshqa shaxs nomi")

    class Meta:
        model = Transaction
        fields = ['amount_usd' ,'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'click', 'comment', 'countryparty', 'other_counterparty']
        
    def save(self, commit = True, operator=None):
        transaction = super().save(commit=False)
        if self.cleaned_data['countryparty'] == 'other':
            transaction.counterparty = self.cleaned_data['other_counterparty']
        else:
            transaction.counterparty = self.cleaned_data['countryparty']
        transaction.operator = operator
        if commit:
            transaction.save()

        report = DailyReport.objects.create(
            operator=operator,
            type='income',
            is_closed=True
        )
        report.total_uzs = self.cleaned_data.get('amount_uzs', 0)
        report.total_usd = self.cleaned_data.get('amount_usd', 0)
        report.total_rub = self.cleaned_data.get('amount_rub', 0)
        report.total_uer = self.cleaned_data.get('amount_eur', 0)
        report.uzs_detail = {self.cleaned_data['payment_type']: int(self.cleaned_data.get('amount_uzs') or 0)}
        report.usd_detail = {self.cleaned_data['payment_type']: int(self.cleaned_data.get('amount_usd') or 0)}
        report.rub_detail = {self.cleaned_data['payment_type']: int(self.cleaned_data.get('amount_rub') or 0)}
        report.eur_detail = {self.cleaned_data['payment_type']: int(self.cleaned_data.get('amount_eur') or 0)}
        report.category = transaction.counterparty
        transaction.report = report
        transaction.save()
        report.save()
        return transaction

class ExpenseForm(forms.Form):
    category = forms.CharField(max_length=100)
    amount_usd = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    amount_uzs = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    amount_rub = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    amount_eur = forms.DecimalField(max_digits=15, decimal_places=2, required=False)
    payment_type = forms.ChoiceField(choices=Transaction.PAYMENT_TYPES)
    description = forms.CharField(widget=forms.Textarea, required=False)

    class Meta:
        fields = ['category', 'amount_usd', 'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'description']
        
    def save(self, commit=True, operator=None):
        if self.cleaned_data['category'] in CATEGORIES:
            category = CATEGORIES.get(self.cleaned_data['category'], 'Boshqa xarajatlar')
        else:
            category = self.cleaned_data['description']
        report = DailyReport.objects.create(
            operator=operator,
            type='expense',
            is_closed=False,
            category=category
        )
        report.total_uzs = self.cleaned_data.get('amount_uzs', 0)
        report.total_usd = self.cleaned_data.get('amount_usd', 0)
        report.total_rub = self.cleaned_data.get('amount_rub', 0)
        report.total_uer = self.cleaned_data.get('amount_eur', 0)

        report.uzs_detail = {self.cleaned_data['payment_type']: int(self.cleaned_data.get('amount_uzs') or 0)}
        report.usd_detail = {self.cleaned_data['payment_type']: int(self.cleaned_data.get('amount_usd') or 0)}
        report.rub_detail = {self.cleaned_data['payment_type']: int(self.cleaned_data.get('amount_rub') or 0)}
        report.eur_detail = {self.cleaned_data['payment_type']: int(self.cleaned_data.get('amount_eur') or 0)}
        report.save()

        return redirect('expenses_list')
