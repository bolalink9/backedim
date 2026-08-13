from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

from families.models import FamilyMember
from accounts.models import User
from .models import AppRule, DailyUsageSummary
from .serializers import (
    AppRuleSerializer,
    AppRuleWriteSerializer,
    SyncSerializer,
    DailyUsageSerializer,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def get_child_in_family(child_id, parent_user):
    """
    Parent farzandini tekshiradi:
    ikkalasi ham bir oilada aktiv a'zo bo'lishi kerak.
    """
    parent_family_ids = FamilyMember.objects.filter(
        user=parent_user, is_active=True, role=FamilyMember.Role.PARENT
    ).values_list('family_id', flat=True)

    try:
        child = User.objects.get(id=child_id, role='child')
        member = FamilyMember.objects.get(
            user=child, family_id__in=parent_family_ids, is_active=True
        )
        return child, member.family
    except (User.DoesNotExist, FamilyMember.DoesNotExist):
        return None, None


def require_vip(family):
    """App control — faqat VIP planda."""
    return family.is_vip_active


# ── views ─────────────────────────────────────────────────────────────────────

class SyncView(APIView):
    """
    CHILD tomonidan chaqiriladi (bola telefoni).
    UsageStatsManager ma'lumotlarini yuboradi, qoidalarni oladi.
    WorkManager har 15-30 daqiqada chaqiradi.
    """
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Ilova statistikasini sync qilish + qoidalarni olish",
        description=(
            "Bola telefoni bugungi usage ma'lumotlarini yuboradi. "
            "Javobda shu bolaga qo'yilgan barcha qoidalar qaytadi. "
            "Android Accessibility/DevicePolicy bu qoidalar asosida ilovalarni bloklaydi."
        ),
        request=SyncSerializer,
        tags=["App Control — Child"],
    )
    def post(self, request):
        if request.user.role != 'child':
            return Response(
                {'detail': 'Faqat child role uchun.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Bolaning oilasini topamiz
        membership = FamilyMember.objects.filter(
            user=request.user, is_active=True
        ).select_related('family').first()

        if not membership:
            return Response({'detail': 'Oila topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        family = membership.family

        if not require_vip(family):
            # FREE planda qoidalar yo'q — bo'sh list qaytaradi
            return Response({'rules': []})

        serializer = SyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        rules = serializer.save(family=family, child=request.user)

        return Response({'rules': rules})


class ChildRulesView(APIView):
    """
    CHILD tomonidan — ilova ochilganda joriy qoidalarni oladi.
    Offline holatda ham ishlashi uchun Android keshida saqlaydi.
    """
    permission_classes = (IsAuthenticated,)

    @extend_schema(
        summary="Joriy qoidalarni olish (bola uchun)",
        tags=["App Control — Child"],
    )
    def get(self, request):
        if request.user.role != 'child':
            return Response({'detail': 'Faqat child role uchun.'}, status=403)

        membership = FamilyMember.objects.filter(
            user=request.user, is_active=True
        ).select_related('family').first()

        if not membership or not require_vip(membership.family):
            return Response({'rules': []})

        rules = AppRule.objects.filter(family=membership.family, child=request.user)
        return Response({'rules': AppRuleSerializer(rules, many=True).data})


class ParentChildUsageView(APIView):
    """
    PARENT tomonidan:
      GET  — farzandning ilova statistikasini ko'radi
      POST — qoida qo'yadi yoki yangilaydi
    """
    permission_classes = (IsAuthenticated,)

    def _check(self, request, child_id):
        if request.user.role != 'parent':
            return None, None, Response(
                {'detail': 'Faqat parent uchun.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        child, family = get_child_in_family(child_id, request.user)
        if not child:
            return None, None, Response(
                {'detail': 'Farzand topilmadi yoki siz bir oilada emassiz.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if not require_vip(family):
            return None, None, Response(
                {'detail': 'Bu funksiya faqat VIP planda mavjud.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return child, family, None

    @extend_schema(
        summary="Farzand ilova statistikasi",
        description="Bugungi yoki tanlangan kun uchun har bir ilovaning qancha vaqt ishlatilgani.",
        parameters=[
            OpenApiParameter('date', str, description='YYYY-MM-DD, default: bugun'),
        ],
        tags=["App Control — Parent"],
    )
    def get(self, request, child_id):
        child, family, err = self._check(request, child_id)
        if err:
            return err

        date_str = request.query_params.get('date')
        try:
            from datetime import date as dt_date
            query_date = dt_date.fromisoformat(date_str) if date_str else timezone.localdate()
        except ValueError:
            return Response({'detail': 'Noto\'g\'ri sana formati. YYYY-MM-DD'}, status=400)

        usage = DailyUsageSummary.objects.filter(child=child, date=query_date)
        rules = AppRule.objects.filter(family=family, child=child)

        # Usage + rule ni birlashtirgan javob
        rules_map = {r.package_name: r for r in rules}
        result = []
        for u in usage:
            rule = rules_map.get(u.package_name)
            result.append({
                'package_name':    u.package_name,
                'app_label':       u.app_label,
                'total_secs':      u.total_secs,
                'total_mins':      u.total_mins,
                'is_blocked':      rule.is_blocked if rule else False,
                'daily_limit_mins': rule.daily_limit_mins if rule else None,
                'limit_reached':   (
                    rule is not None
                    and rule.daily_limit_mins is not None
                    and u.total_mins >= rule.daily_limit_mins
                ),
            })

        result.sort(key=lambda x: x['total_secs'], reverse=True)
        return Response({'date': query_date, 'usage': result})

    @extend_schema(
        summary="Ilovaga qoida qo'yish / yangilash",
        description=(
            "is_blocked=true → butunlay taqiq. "
            "daily_limit_mins=60 → kunlik 60 daqiqa limit. "
            "is_blocked=false, daily_limit_mins=null → qoida o'chiriladi."
        ),
        request=AppRuleWriteSerializer,
        tags=["App Control — Parent"],
    )
    def post(self, request, child_id):
        child, family, err = self._check(request, child_id)
        if err:
            return err

        serializer = AppRuleWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Agar ikkalasi ham False/None bo'lsa — qoidani o'chiramiz
        if not serializer.validated_data.get('is_blocked') and \
           serializer.validated_data.get('daily_limit_mins') is None:
            AppRule.objects.filter(
                family=family,
                child=child,
                package_name=serializer.validated_data['package_name'],
            ).delete()
            return Response({'detail': 'Qoida o\'chirildi.'})

        rule = serializer.save(family=family, child=child, set_by=request.user)
        return Response(AppRuleSerializer(rule).data, status=status.HTTP_200_OK)
