import uuid
from django.db import models
from django.utils import timezone
from accounts.models import User
from families.models import Family


class AppRule(models.Model):
    """
    Parent farzandi uchun belgilagan qoida.
    Har packagega bitta qoida — limit (daqiqa) yoki to'liq block.
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family       = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='app_rules')
    child        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='app_rules')
    set_by       = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rules_set')

    package_name     = models.CharField(max_length=200)       # com.zhiliaoapp.musically
    app_label        = models.CharField(max_length=100, blank=True)  # TikTok
    is_blocked       = models.BooleanField(default=False)     # butunlay taqiq
    daily_limit_mins = models.PositiveIntegerField(null=True, blank=True)  # None = cheksiz

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('family', 'child', 'package_name')
        ordering = ['app_label']

    def __str__(self):
        s = 'BLOCKED' if self.is_blocked else f'{self.daily_limit_mins}m'
        return f'{self.child.full_name} → {self.app_label or self.package_name} [{s}]'


class DailyUsageSummary(models.Model):
    """
    Kunlik yig'indi. Android WorkManager har 15-30 daqiqada sync qilganda yangilanadi.
    Xom reportlar saqlanmaydi — to'g'ridan yig'indiga qo'shiladi (storage tejash).
    """
    id           = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    family       = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='daily_summaries')
    child        = models.ForeignKey(User, on_delete=models.CASCADE, related_name='daily_summaries')

    date         = models.DateField()
    package_name = models.CharField(max_length=200)
    app_label    = models.CharField(max_length=100, blank=True)
    total_secs   = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('child', 'date', 'package_name')
        ordering = ['-date', '-total_secs']
        indexes = [
            models.Index(fields=['child', 'date']),
        ]

    @property
    def total_mins(self) -> int:
        return self.total_secs // 60

    def __str__(self):
        return f'{self.child.full_name} / {self.package_name} / {self.date} / {self.total_mins}m'
