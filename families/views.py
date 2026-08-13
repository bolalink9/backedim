from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Family, FamilyMember
from .serializers import (
    CreateFamilySerializer,
    FamilySerializer,
    FamilyPlanSerializer,
    JoinFamilySerializer,
    UpgradePlanSerializer,
    DowngradeToFreeSerializer,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_family_for_member(family_id, user) -> Family | None:
    """Foydalanuvchi bu oilaga aktiv a'zo bo'lsa qaytaradi, aks holda None."""
    try:
        member = FamilyMember.objects.select_related('family').get(
            family_id=family_id, user=user, is_active=True
        )
        return member.family
    except FamilyMember.DoesNotExist:
        return None


def get_family_for_parent(family_id, user) -> Family | None:
    """Faqat parent role uchun."""
    try:
        member = FamilyMember.objects.select_related('family').get(
            family_id=family_id, user=user, is_active=True, role=FamilyMember.Role.PARENT
        )
        return member.family
    except FamilyMember.DoesNotExist:
        return None


# ── Views ─────────────────────────────────────────────────────────────────────

class CreateFamilyView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Oila yaratish",
        description="Faqat parent uchun. 7 kunlik VIP trial avtomatik boshlanadi.",
        request=CreateFamilySerializer,
        responses={201: FamilySerializer},
        tags=["Family"],
    )
    def post(self, request):
        if request.user.role != 'parent':
            return Response(
                {'detail': 'Faqat ota-ona oila yarata oladi.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = CreateFamilySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        family = serializer.save()
        return Response(serializer.to_representation(family), status=status.HTTP_201_CREATED)


class MyFamiliesView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Mening oilalarim",
        description="Foydalanuvchi a'zo bo'lgan barcha oilalar (plan ma'lumotlari bilan).",
        responses={200: FamilySerializer(many=True)},
        tags=["Family"],
    )
    def get(self, request):
        family_ids = FamilyMember.objects.filter(
            user=request.user, is_active=True
        ).values_list('family_id', flat=True)

        families = Family.objects.filter(id__in=family_ids)
        serializer = FamilySerializer(families, many=True, context={'request': request})
        return Response(serializer.data)


class FamilyDetailView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Oila ma'lumotlari",
        description="To'liq oila ma'lumoti, a'zolar va plan holati.",
        responses={200: FamilySerializer},
        tags=["Family"],
    )
    def get(self, request, family_id):
        family = get_family_for_member(family_id, request.user)
        if not family:
            return Response({'detail': 'Topilmadi.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = FamilySerializer(family, context={'request': request})
        return Response(serializer.data)

    @extend_schema(
        summary="Oilani o'chirish",
        description=(
            "Faqat oilani yaratgan parent o'chira oladi. "
            "Barcha a'zolar, qoidalar, usage ma'lumotlari kaskad o'chadi."
        ),
        responses={204: OpenApiResponse(description="O'chirildi")},
        tags=["Family"],
    )
    def delete(self, request, family_id):
        try:
            family = Family.objects.get(id=family_id)
        except Family.DoesNotExist:
            return Response({'detail': 'Topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        if family.created_by != request.user:
            return Response(
                {'detail': 'Faqat oilani yaratgan parent o\'chira oladi.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        family.delete()  # CASCADE: FamilyMember, AppRule, DailyUsageSummary hammasi o'chadi
        return Response(status=status.HTTP_204_NO_CONTENT)


class JoinFamilyView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Oilaga qo'shilish",
        description=(
            "Invite code orqali oilaga child sifatida qo'shilish. "
            "FREE planda max 1 ta, VIP planda max 3 ta farzand qo'shilishi mumkin."
        ),
        request=JoinFamilySerializer,
        responses={200: FamilySerializer},
        tags=["Family"],
    )
    def post(self, request):
        serializer = JoinFamilySerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        member = serializer.save()
        family_data = FamilySerializer(member.family, context={'request': request}).data
        return Response(family_data, status=status.HTTP_200_OK)


class FamilyMembersView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Oila a'zolari",
        description="Oiladagi barcha aktiv a'zolar ro'yxati.",
        responses={200: FamilySerializer},
        tags=["Family"],
    )
    def get(self, request, family_id):
        family = get_family_for_member(family_id, request.user)
        if not family:
            return Response({'detail': "Ruxsat yo'q."}, status=status.HTTP_403_FORBIDDEN)

        members = FamilyMember.objects.filter(
            family=family, is_active=True
        ).select_related('user')

        from .serializers import FamilyMemberSerializer
        serializer = FamilyMemberSerializer(members, many=True, context={'request': request})
        return Response(serializer.data)


class FamilyPlanView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Oila plan holati",
        description="Hozirgi plan, trial qolgan vaqt, max farzand soni.",
        responses={200: FamilyPlanSerializer},
        tags=["Family / Plan"],
    )
    def get(self, request, family_id):
        family = get_family_for_member(family_id, request.user)
        if not family:
            return Response({'detail': 'Topilmadi.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = FamilyPlanSerializer(family)
        return Response(serializer.data)


class UpgradePlanView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="VIP planga o'tish",
        description=(
            "To'lov tizimi callback'dan yoki admin tomonidan chaqiriladi. "
            "duration_days — necha kun VIP qo'shilishi (default 30)."
        ),
        request=UpgradePlanSerializer,
        responses={200: FamilyPlanSerializer},
        tags=["Family / Plan"],
    )
    def post(self, request, family_id):
        family = get_family_for_parent(family_id, request.user)
        if not family:
            return Response(
                {'detail': "Faqat oila parenti VIP aktivlashtirishhi mumkin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UpgradePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated_family = serializer.save(family=family)
        return Response(FamilyPlanSerializer(updated_family).data, status=status.HTTP_200_OK)


class DowngradePlanView(APIView):
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="FREE planga tushish",
        description="Trial tugagach yoki ixtiyoriy ravishda FREE planga o'tish.",
        responses={200: FamilyPlanSerializer},
        tags=["Family / Plan"],
    )
    def post(self, request, family_id):
        family = get_family_for_parent(family_id, request.user)
        if not family:
            return Response(
                {'detail': "Faqat oila parenti plan o'zgartirishi mumkin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = DowngradeToFreeSerializer(data={})
        serializer.is_valid(raise_exception=True)
        updated_family = serializer.save(family=family)
        return Response(FamilyPlanSerializer(updated_family).data, status=status.HTTP_200_OK)
