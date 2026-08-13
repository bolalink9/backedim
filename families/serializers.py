from rest_framework import serializers
from .models import Family, FamilyMember
from accounts.models import User


class MemberUserSerializer(serializers.ModelSerializer):
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'full_name', 'role', 'avatar')

    def get_avatar(self, obj):
        if not obj.avatar:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.avatar.url)
        return obj.avatar.url


class FamilyMemberSerializer(serializers.ModelSerializer):
    user = MemberUserSerializer(read_only=True)

    class Meta:
        model = FamilyMember
        fields = ('id', 'user', 'role', 'joined_at')


class FamilyPlanSerializer(serializers.ModelSerializer):
    """Oila plan holati — frontend uchun qulay format"""
    effective_plan  = serializers.CharField(read_only=True)
    is_vip_active   = serializers.BooleanField(read_only=True)
    is_trial_active = serializers.BooleanField(read_only=True)
    max_children    = serializers.IntegerField(read_only=True)

    class Meta:
        model = Family
        fields = (
            'plan',
            'effective_plan',
            'is_vip_active',
            'is_trial_active',
            'trial_ends_at',
            'vip_expires_at',
            'max_children',
        )


class FamilySerializer(serializers.ModelSerializer):
    members         = FamilyMemberSerializer(many=True, read_only=True)
    members_count   = serializers.IntegerField(read_only=True)
    children_count  = serializers.IntegerField(read_only=True)
    subscription    = FamilyPlanSerializer(source='*', read_only=True)

    class Meta:
        model = Family
        fields = (
            'id', 'name', 'invite_code',
            'home_latitude', 'home_longitude', 'home_address',
            'subscription',
            'members_count', 'children_count',
            'members', 'created_at',
        )
        read_only_fields = ('id', 'invite_code', 'created_at')


class CreateFamilySerializer(serializers.ModelSerializer):
    class Meta:
        model = Family
        fields = ('name', 'home_latitude', 'home_longitude', 'home_address')

    def create(self, validated_data):
        user = self.context['request'].user
        family = Family.objects.create(created_by=user, **validated_data)
        FamilyMember.objects.create(family=family, user=user, role=FamilyMember.Role.PARENT)
        return family

    def to_representation(self, instance):
        return FamilySerializer(instance, context=self.context).data


class JoinFamilySerializer(serializers.Serializer):
    invite_code  = serializers.CharField(max_length=6, min_length=6)
    display_name = serializers.CharField(max_length=100, required=False)

    def validate_invite_code(self, value):
        value = value.upper()
        try:
            self.family = Family.objects.get(invite_code=value)
        except Family.DoesNotExist:
            raise serializers.ValidationError("Kod noto'g'ri yoki muddati o'tgan.")
        return value

    def validate(self, data):
        user = self.context['request'].user

        if FamilyMember.objects.filter(family=self.family, user=user).exists():
            raise serializers.ValidationError("Siz allaqachon bu oilaga a'zo siz.")

        # Plan cheklovini tekshirish
        if self.family.children_count >= self.family.max_children:
            raise serializers.ValidationError(
                f"Bu oila {self.family.max_children} ta farzand limitiga yetgan. "
                f"Ko'proq qo'shish uchun VIP planga o'ting."
            )
        return data

    def save(self):
        user = self.context['request'].user
        display_name = self.validated_data.get('display_name')

        if display_name:
            user.full_name = display_name
            user.save(update_fields=['full_name'])

        return FamilyMember.objects.create(
            family=self.family,
            user=user,
            role=FamilyMember.Role.CHILD,
        )


class UpgradePlanSerializer(serializers.Serializer):
    """
    VIP aktivatsiya uchun.
    Hozir manual (admin yoki to'lov callback'dan chaqiriladi).
    """
    duration_days = serializers.IntegerField(default=30, min_value=1)

    def save(self, family: Family):
        from django.utils import timezone
        from datetime import timedelta

        days = self.validated_data['duration_days']
        now = timezone.now()

        # Agar avvalgi VIP hali tugamagan bo'lsa — ustiga qo'shamiz
        base = family.vip_expires_at if (family.vip_expires_at and family.vip_expires_at > now) else now
        family.plan = Family.Plan.VIP
        family.vip_expires_at = base + timedelta(days=days)
        family.save(update_fields=['plan', 'vip_expires_at'])
        return family


class DowngradeToFreeSerializer(serializers.Serializer):
    """Trial tugagach FREE planga tushish"""

    def save(self, family: Family):
        family.plan = Family.Plan.FREE
        family.vip_expires_at = None
        family.save(update_fields=['plan', 'vip_expires_at'])
        return family
