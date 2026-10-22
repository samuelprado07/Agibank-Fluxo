from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
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
    series = models.ForeignKey("ExpenseSeries", null=True, blank=True, on_delete=models.PROTECT, related_name="occurrences")
    competence = models.DateField(null=True, blank=True)
    is_exception = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=("series", "competence"), name="unique_expense_series_month")]


class Movement(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="movements")
    occurrence = models.OneToOneField(Occurrence, null=True, blank=True, on_delete=models.PROTECT, related_name="movement")
    description = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    date = models.DateField()
    direction = models.CharField(max_length=10, choices=Occurrence.Direction.choices)


class ExpenseSeries(models.Model):
    scenario = models.ForeignKey(Scenario, on_delete=models.CASCADE, related_name="expense_series")
    description = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    category = models.CharField(max_length=60, blank=True)
    essential = models.BooleanField(default=False)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    cancelled_from = models.DateField(null=True, blank=True)
    due_day = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(31)])


class ExpenseSeriesRevision(models.Model):
    series = models.ForeignKey(ExpenseSeries, on_delete=models.PROTECT, related_name="revisions")
    effective_from = models.DateField()
    values = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class ExpenseSeriesHistory(models.Model):
    series = models.ForeignKey(ExpenseSeries, on_delete=models.PROTECT, related_name="history")
    action = models.CharField(max_length=20)
    before = models.JSONField()
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class ExpenseHistory(models.Model):
    occurrence = models.ForeignKey(Occurrence, on_delete=models.PROTECT, related_name="history")
    action = models.CharField(max_length=20)
    before = models.JSONField()
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class ExpenseSeriesExclusion(models.Model):
    series = models.ForeignKey(ExpenseSeries, on_delete=models.PROTECT, related_name="exclusions")
    competence = models.DateField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=("series", "competence"), name="unique_series_excluded_month")]
