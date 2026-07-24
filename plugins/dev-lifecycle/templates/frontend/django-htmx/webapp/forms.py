"""`webapp`'s Django forms — SHAPE-only validation, per `django.md`'s
"Forms own validation" convention: a form here validates presence/format
only. Validation for auth CORRECTNESS (does this email/password pair
actually authenticate?) and for the item demo's business rules stays with
`AuthService`/the `Item` model respectively — a form that validates
"looks well-formed" still goes through those before anything is
committed or a session is granted. See `webapp/views.py` for how each
form composes with its real validation layer."""

from __future__ import annotations

from django import forms

_INPUT_CLASSES = (
    "block w-full rounded-md border border-gray-300 px-3 py-2 text-sm "
    "shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
)


class LoginForm(forms.Form):
    """Presence + email-format only — the real authentication check is
    `AuthService.login` (`webapp/views.py`'s `LoginView`), which this form
    never duplicates or second-guesses. A shape failure here (empty
    email, malformed email, empty password) re-renders
    `templates/webapp/partials/_login_form.html` with Django's own
    per-field errors; an `AuthError` from `AuthService` re-renders the
    SAME partial with one generic, non-field error instead (see
    `LoginView`'s own docstring on why that message must not distinguish
    reasons — mirrors `core/exceptions.py`'s FIX B)."""

    email = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={"autocomplete": "email", "class": _INPUT_CLASSES}),
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "class": _INPUT_CLASSES}),
    )


class ItemForm(forms.Form):
    """Backs the `hx-post` item-create demo (`webapp/views.py`'s
    `item_create` view) — presence/length validation only, matching
    `core.models.Item`'s own field constraints (`name` required, max 200;
    `description` optional, max 2000) so a shape failure here is caught
    before it would otherwise reach the database as an `IntegrityError`."""

    name = forms.CharField(
        label="Name",
        max_length=200,
        widget=forms.TextInput(attrs={"class": _INPUT_CLASSES, "autofocus": True}),
    )
    description = forms.CharField(
        label="Description",
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={"class": _INPUT_CLASSES, "rows": 2}),
    )
