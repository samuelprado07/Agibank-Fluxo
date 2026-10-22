from django.urls import path

from .views import dashboard
from .expense_views import expense_cancel, expense_collection, expense_detail

urlpatterns = [
    path("dashboard/", dashboard, name="dashboard"),
    path("expenses/", expense_collection, name="expense-collection"),
    path("expenses/<int:expense_id>/", expense_detail, name="expense-detail"),
    path("expenses/<int:expense_id>/cancel/", expense_cancel, name="expense-cancel"),
]
