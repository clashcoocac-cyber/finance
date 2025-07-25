from django import forms
from django.contrib.auth.forms import UserChangeForm
from .models import Company, User



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
    password = None  # Parolni o'zgartirish formda bo'lmaydi
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role', 'company']
