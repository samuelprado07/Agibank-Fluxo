from django.urls import path

from .views import dashboard
from .expense_views import expense_cancel, expense_collection, expense_detail
from .series_views import series_collection, series_detail
from .payment_views import payment
from .income_views import income_collection, income_detail, income_receipt, income_series_cancel

urlpatterns = [
    path("incomes/", income_collection, name="income-collection"),
    path("incomes/<int:income_id>/", income_detail, name="income-detail"),
    path("incomes/<int:income_id>/cancel/", income_detail, {"cancel": True}, name="income-cancel"),
    path("incomes/<int:income_id>/receipt/", income_receipt, name="income-receipt"),
    path("incomes/<int:income_id>/receipt/undo/", income_receipt, {"undo": True}, name="income-receipt-undo"),
    path("income-recurrences/<int:series_id>/cancel/", income_series_cancel, name="income-series-cancel"),
    path("expenses/<int:expense_id>/payment/", payment, name="expense-payment"),
    path("expenses/<int:expense_id>/payment/undo/", payment, {"undo": True}, name="expense-payment-undo"),
    path("recurrences/", series_collection, name="series-collection"),
    path("recurrences/<int:series_id>/", series_detail, name="series-detail"),
    path("recurrences/<int:series_id>/cancel/", series_detail, {"cancel": True}, name="series-cancel"),
    path("dashboard/", dashboard, name="dashboard"),
    path("expenses/", expense_collection, name="expense-collection"),
    path("expenses/<int:expense_id>/", expense_detail, name="expense-detail"),
    path("expenses/<int:expense_id>/cancel/", expense_cancel, name="expense-cancel"),
]
