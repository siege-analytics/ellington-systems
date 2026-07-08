from __future__ import annotations

from django import forms

from ellington_web.roster.models import GRANULARITY_LEVELS

from .models import Confirmation


class ConfirmationForm(forms.ModelForm):
    corrected_granularity_level = forms.ChoiceField(
        choices=[("", "— unchanged —")] + GRANULARITY_LEVELS,
        required=False,
    )

    class Meta:
        model = Confirmation
        fields = [
            "verdict",
            "corrected_granularity_level",
            "corrected_function_role",
            "comment",
        ]
        widgets = {
            "comment": forms.Textarea(attrs={"rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        verdict = cleaned.get("verdict")
        comment = (cleaned.get("comment") or "").strip()
        if verdict in {
            Confirmation.Verdict.NUANCE,
            Confirmation.Verdict.REREVIEW,
        } and not comment:
            self.add_error(
                "comment",
                "A comment is required when adding nuance or flagging for re-review.",
            )
        if verdict == Confirmation.Verdict.CORRECT and not (
            cleaned.get("corrected_granularity_level")
            or (cleaned.get("corrected_function_role") or "").strip()
        ):
            self.add_error(
                "verdict",
                "Corrections must specify a new bucket or a new function role.",
            )
        return cleaned
