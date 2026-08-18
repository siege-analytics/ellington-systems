from django.urls import path

from . import views

app_name = "roster"

urlpatterns = [
    path("", views.MasterListView.as_view(), name="master_list"),
    path("<slug:slug>/", views.MasterDetailView.as_view(), name="master_detail"),
]
