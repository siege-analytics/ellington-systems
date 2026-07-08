from django.urls import path

from . import views

app_name = "confirmations"

urlpatterns = [
    path("<slug:master_slug>/", views.review_master, name="review_master"),
    path(
        "<slug:master_slug>/note/<str:note_id>/",
        views.review_note,
        name="review_note",
    ),
]
