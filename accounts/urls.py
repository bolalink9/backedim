from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    ChangePasswordView,
)

urlpatterns = [
    path('register/',               RegisterView.as_view(),             name='auth-register'),
    path('login/',                  LoginView.as_view(),                name='auth-login'),
    path('logout/',                 LogoutView.as_view(),               name='auth-logout'),
    path('token/refresh/',          TokenRefreshView.as_view(),         name='auth-token-refresh'),
    path('password-reset/',         PasswordResetRequestView.as_view(), name='auth-password-reset'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='auth-password-reset-confirm'),
    path('change-password/',        ChangePasswordView.as_view(),       name='auth-change-password'),
]
