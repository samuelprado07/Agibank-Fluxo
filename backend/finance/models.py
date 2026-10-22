from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Scenario(models.Model):
    name = models.CharField(max_length=120)
    opening_date = models.DateField()
    reference_date = models.DateField()
    opening_balance = models.DecimalField(max_digits=14, decimal_places=2)
    variable_expenses_included = models.BooleanField(default=False)


class Occurrence(models.Model):
    class Direction(models.TextChoices):
        INCOME = "income", "Entrada"
        EXPENSE = "expense", "Saída"

    class Status(models.TextChoices):
        PENDING = "pending", "Previsto ou pendente"
        SETTLED = "settled", "Recebido ou pago"
        CANCELLED = "cancelled", "Cancelado"

    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="occurrences")
    description = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    due_date = models.DateField()
    direction = models.CharField(max_length=10, choices=Direction.choices)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    essential = models.BooleanField(default=False)
    category = models.CharField(max_length=60, blank=True)


class Movement(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="movements")
    occurrence = models.OneToOneField(Occurrence, null=True, blank=True, on_delete=models.PROTECT, related_name="movement")
    description = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    date = models.DateField()
    direction = models.CharField(max_length=10, choices=Occurrence.Direction.choices)
