from django.urls import path
from .views import (
    DashboardStatsView,
    UserListView,
    UserDetailView,
    FamilyListView,
    FamilyDetailView,
)

urlpatterns = [
    path('stats/',                      DashboardStatsView.as_view(), name='admin-stats'),
    path('users/',                      UserListView.as_view(),        name='admin-users'),
    path('users/<uuid:user_id>/',       UserDetailView.as_view(),      name='admin-user-detail'),
    path('families/',                   FamilyListView.as_view(),      name='admin-families'),
    path('families/<uuid:family_id>/',  FamilyDetailView.as_view(),    name='admin-family-detail'),
]
