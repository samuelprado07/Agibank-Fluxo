from django import forms

from .models import Occurrence


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Occurrence
        fields = ("description", "amount", "category", "due_date", "essential", "is_estimate")
        widgets = {"due_date": forms.DateInput(format="%Y-%m-%d")}

    def clean_description(self):
        return self.cleaned_data["description"].strip()
