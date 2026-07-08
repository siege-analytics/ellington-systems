from __future__ import annotations

from django.views.generic import DetailView, ListView

from .models import Master


class MasterListView(ListView):
    model = Master
    template_name = "roster/master_list.html"
    context_object_name = "masters"


class MasterDetailView(DetailView):
    model = Master
    template_name = "roster/master_detail.html"
    context_object_name = "master"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        master: Master = ctx["master"]
        ctx["distribution_rows"] = master.distribution_rows()
        ctx["max_bucket_count"] = max(
            (row["count"] for row in ctx["distribution_rows"]), default=0
        )
        ctx["books"] = master.books.all()
        return ctx
