from django import forms
from django.contrib.auth.forms import UserChangeForm
from .models import Company, User, Transaction



class UserRegisterForm(forms.ModelForm):    
    password = forms.CharField(widget=forms.PasswordInput)
    company_name = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ['username', 'shift', 'role', 'company_name', 'password']

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
        fields = ['user_id', 'shift', 'username', 'new_password', 'company_name']

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

    class Meta:
        model = Transaction
        fields = ['amount_usd' ,'amount_uzs', 'amount_rub', 'amount_eur', 'payment_type', 'counterparty']
        
    def save(self, commit = ..., operator=None):
        transaction = super().save(commit=False)
        transaction.operator = operator
        if commit:
            transaction.save()
        return transaction