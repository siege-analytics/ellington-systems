from __future__ import annotations

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

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


class InviteRedemptionForm(forms.Form):
    username = forms.CharField(
        max_length=150,
        help_text="Login handle. Letters, digits, and @/./+/-/_ only.",
    )
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    password_confirm = forms.CharField(
        widget=forms.PasswordInput, label="Confirm password"
    )

    def clean_username(self) -> str:
        from django.contrib.auth import get_user_model
        username = self.cleaned_data["username"].strip()
        if get_user_model().objects.filter(username=username).exists():
            raise ValidationError("That username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get("password")
        pw2 = cleaned.get("password_confirm")
        if pw and pw2 and pw != pw2:
            self.add_error("password_confirm", "Passwords do not match.")
        if pw:
            try:
                validate_password(pw)
            except ValidationError as exc:
                self.add_error("password", exc)
        return cleaned
