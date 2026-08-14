from django.contrib.auth import authenticate
from django.utils import timezone
from datetime import timedelta
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, PasswordResetCode
from .utils import generate_otp, send_reset_code


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    role = serializers.ChoiceField(choices=User.Role.choices, default=User.Role.PARENT)

    class Meta:
        model = User
        fields = ('email', 'full_name', 'phone', 'password', 'role')

    def validate_email(self, value):
        if not value.endswith('@gmail.com'):
            raise serializers.ValidationError('Faqat Gmail manzili qabul qilinadi.')
        return value.lower()

    def create(self, validated_data):
        user = User.objects.create_user(**validated_data)
        return user

    def to_representation(self, instance):
        refresh = RefreshToken.for_user(instance)
        request = self.context.get('request')
        avatar_url = None
        if instance.avatar:
            avatar_url = request.build_absolute_uri(instance.avatar.url) if request else instance.avatar.url
        return {
            'user': {
                'id':       str(instance.id),
                'email':    instance.email,
                'full_name': instance.full_name,
                'phone':    instance.phone,
                'role':     instance.role,
                'avatar':   avatar_url,
                'is_staff': instance.is_staff,
            },
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
        }


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(email=data['email'].lower(), password=data['password'])
        if not user:
            raise serializers.ValidationError('Email yoki parol noto\'g\'ri.')
        if not user.is_active:
            raise serializers.ValidationError('Hisob bloklangan.')
        request = self.context.get('request')
        avatar_url = None
        if user.avatar:
            avatar_url = request.build_absolute_uri(user.avatar.url) if request else user.avatar.url
        refresh = RefreshToken.for_user(user)
        return {
            'user': {
                'id':       str(user.id),
                'email':    user.email,
                'full_name': user.full_name,
                'phone':    user.phone,
                'role':     user.role,
                'avatar':   avatar_url,
                'is_staff': user.is_staff,
            },
            'access':  str(refresh.access_token),
            'refresh': str(refresh),
        }


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        value = value.lower()
        if not User.objects.filter(email=value).exists():
            # Xavfsizlik uchun xato ko'rsatmaymiz
            return value
        return value

    def save(self):
        email = self.validated_data['email']
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return  # foydalanuvchi topilmasa ham javob bir xil

        # Oldingi kodlarni o'chirish
        PasswordResetCode.objects.filter(user=user, is_used=False).delete()

        code = generate_otp()
        PasswordResetCode.objects.create(user=user, code=code)
        send_reset_code(email, code)


class PasswordResetConfirmSerializer(serializers.Serializer):
    email = serializers.EmailField()
    code = serializers.CharField(max_length=6, min_length=6)
    new_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, data):
        email = data['email'].lower()
        code = data['code']

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError('Foydalanuvchi topilmadi.')

        # Oxirgi 10 daqiqadagi ishlatilmagan kod
        expiry = timezone.now() - timedelta(minutes=10)
        reset_code = PasswordResetCode.objects.filter(
            user=user,
            code=code,
            is_used=False,
            created_at__gte=expiry,
        ).first()

        if not reset_code:
            raise serializers.ValidationError('Kod noto\'g\'ri yoki muddati o\'tgan.')

        data['user'] = user
        data['reset_code'] = reset_code
        return data

    def save(self):
        user = self.validated_data['user']
        reset_code = self.validated_data['reset_code']

        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])

        reset_code.is_used = True
        reset_code.save(update_fields=['is_used'])
