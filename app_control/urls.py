from django.urls import path
from .views import SyncView, ChildRulesView, ParentChildUsageView

urlpatterns = [
    # Bola telefoni — WorkManager chaqiradi
    path('sync/',                           SyncView.as_view(),            name='app-sync'),
    path('rules/',                          ChildRulesView.as_view(),      name='app-rules-child'),

    # Parent — farzandni kuzatish va boshqarish
    path('children/<uuid:child_id>/usage/', ParentChildUsageView.as_view(), name='app-child-usage'),
]
