import uuid
import random
import string
from django.db import models
from django.utils import timezone
from datetime import timedelta
from accounts.models import User


def generate_family_code():
    """6 belgili unikal invite code: ABC123"""
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=6))
        if not Family.objects.filter(invite_code=code).exists():
            return code


class Family(models.Model):

    class Plan(models.TextChoices):
        FREE     = 'free',  'Freemium'
        VIP      = 'vip',   'VIP'

    # Har yangi oila 7 kun trial VIP bilan boshlanadi.
    # trial_ends_at → None bo'lsa trial tugagan (yoki hech bo'lmagan).
    # plan → trial tugagach user tanlagan plan.

    id          = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name        = models.CharField(max_length=100)
    invite_code = models.CharField(max_length=6, unique=True, editable=False)

    # Subscription
    plan             = models.CharField(max_length=10, choices=Plan.choices, default=Plan.FREE)
    trial_ends_at    = models.DateTimeField(null=True, blank=True)
    vip_expires_at   = models.DateTimeField(null=True, blank=True)  # to'liq VIP tugash vaqti

    # Uy joylashuvi (geofencing uchun asos)
    home_latitude  = models.FloatField(null=True, blank=True)
    home_longitude = models.FloatField(null=True, blank=True)
    home_address   = models.CharField(max_length=255, null=True, blank=True)

    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='created_families'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Families'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if not self.invite_code:
            self.invite_code = generate_family_code()
        if not self.trial_ends_at:
            # Yangi oila — 7 kunlik trial
            self.trial_ends_at = timezone.now() + timedelta(days=7)
        super().save(*args, **kwargs)

    # ── Plan helpers (property — DB query yo'q) ──────────────────────────────

    @property
    def is_trial_active(self) -> bool:
        """7 kunlik trial hali tugamaganmi?"""
        return self.trial_ends_at is not None and timezone.now() < self.trial_ends_at

    @property
    def is_vip_active(self) -> bool:
        """Trial yoki to'liq VIP aktiv?"""
        if self.is_trial_active:
            return True
        if self.plan == self.Plan.VIP and self.vip_expires_at:
            return timezone.now() < self.vip_expires_at
        return False

    @property
    def effective_plan(self) -> str:
        """Hozir amalda bo'lgan plan: 'vip' yoki 'free'"""
        return self.Plan.VIP if self.is_vip_active else self.Plan.FREE

    @property
    def max_children(self) -> int:
        """Qo'shish mumkin bo'lgan maksimal farzand soni"""
        return 3 if self.is_vip_active else 1

    @property
    def members_count(self) -> int:
        return self.members.filter(is_active=True).count()

    @property
    def children_count(self) -> int:
        return self.members.filter(is_active=True, role=FamilyMember.Role.CHILD).count()

    def __str__(self):
        return f'{self.name} [{self.invite_code}] ({self.effective_plan})'


class FamilyMember(models.Model):

    class Role(models.TextChoices):
        PARENT = 'parent', 'Ota-ona'
        CHILD  = 'child',  'Farzand'

    family    = models.ForeignKey(Family, on_delete=models.CASCADE, related_name='members')
    user      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='family_memberships')
    role      = models.CharField(max_length=10, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('family', 'user')
        ordering = ['joined_at']

    def __str__(self):
        return f'{self.user.full_name} — {self.family.name} ({self.role})'
