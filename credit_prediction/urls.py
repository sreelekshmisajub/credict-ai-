from django.urls import path

from . import views

app_name = "credit_prediction"

urlpatterns = [
    path("analyze/", views.create_prediction, name="analyze"),
    path("predictions/<int:prediction_id>/", views.prediction_detail, name="detail"),
]
