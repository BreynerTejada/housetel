from django.urls import path

from apps.accounts.api.team_views import AcceptInvitationView, PublicInvitationView

app_name = "accounts_public"

urlpatterns = [
    path("invitations/<str:token>/", PublicInvitationView.as_view(), name="invitation"),
    path("invitations/<str:token>/accept/", AcceptInvitationView.as_view(), name="invitation-accept"),
]
