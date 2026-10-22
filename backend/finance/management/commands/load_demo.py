from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from finance.models import Movement, Occurrence, Scenario


class Command(BaseCommand):
    help = "Carrega uma vez o cenário fictício do dashboard, sem duplicar ou apagar dados existentes."

    @transaction.atomic
    def handle(self, *args, **options):
        scenario, created = Scenario.objects.get_or_create(
            name="Demonstração — outubro de 2026",
            defaults={"opening_date": date(2026, 10, 20), "reference_date": date(2026, 10, 22), "opening_balance": "1400.00", "variable_expenses_included": False},
        )
        if not created:
            self.stdout.write("Cenário já carregado; dados preservados.")
            return
        reference = scenario.reference_date
        rows = [
            ("Conta de energia", "180.00", -1, "expense", True, "Moradia", "pending"),
            ("Medicamentos", "220.00", 2, "expense", True, "Saúde", "pending"),
            ("Aluguel", "750.00", 8, "expense", True, "Moradia", "pending"),
            ("Transporte estimado", "90.00", 12, "expense", False, "Variável", "pending"),
            ("Alimentação essencial", "180.00", 17, "expense", True, "Alimentação", "pending"),
            ("Benefício previsto", "2200.00", 20, "income", False, "Renda", "pending"),
            ("Internet", "100.00", -1, "expense", True, "Comunicação", "settled"),
            ("Assinatura cancelada", "50.00", 4, "expense", False, "Serviços", "cancelled"),
        ]
        for description, amount, offset, direction, essential, category, status in rows:
            occurrence = Occurrence.objects.create(scenario=scenario, description=description, amount=amount, due_date=reference + timedelta(days=offset), direction=direction, essential=essential, category=category, status=status)
            if status == "settled":
                Movement.objects.create(scenario=scenario, occurrence=occurrence, description=description, amount=amount, date=reference - timedelta(days=1), direction=direction)
        self.stdout.write(self.style.SUCCESS("Cenário demonstrativo carregado. Referência: 22/10/2026."))
