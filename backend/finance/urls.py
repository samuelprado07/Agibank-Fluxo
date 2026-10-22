from django.urls import path

from .views import dashboard
from .expense_views import expense_cancel, expense_collection, expense_detail
from .series_views import series_collection, series_detail

urlpatterns = [
    path("recurrences/", series_collection, name="series-collection"),
    path("recurrences/<int:series_id>/", series_detail, name="series-detail"),
    path("recurrences/<int:series_id>/cancel/", series_detail, {"cancel": True}, name="series-cancel"),
    path("dashboard/", dashboard, name="dashboard"),
    path("expenses/", expense_collection, name="expense-collection"),
    path("expenses/<int:expense_id>/", expense_detail, name="expense-detail"),
    path("expenses/<int:expense_id>/cancel/", expense_cancel, name="expense-cancel"),
]
