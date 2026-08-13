from django.db.models import Count, Q, Sum
from django.utils import timezone
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAdminUser
from drf_spectacular.utils import extend_schema

from accounts.models import User
from families.models import Family, FamilyMember
from app_control.models import AppRule, DailyUsageSummary


class DashboardStatsView(APIView):
    """Bosh sahifa statistikasi"""
    permission_classes = (IsAdminUser,)

    @extend_schema(summary="Dashboard statistikasi", tags=["Admin"])
    def get(self, request):
        now = timezone.now()
        last_7  = now - timedelta(days=7)
        last_30 = now - timedelta(days=30)

        total_users    = User.objects.count()
        total_parents  = User.objects.filter(role='parent').count()
        total_children = User.objects.filter(role='child').count()
        new_this_week  = User.objects.filter(created_at__gte=last_7).count()
        new_this_month = User.objects.filter(created_at__gte=last_30).count()

        total_families  = Family.objects.count()
        vip_families    = sum(1 for f in Family.objects.all() if f.is_vip_active)
        free_families   = total_families - vip_families
        trial_families  = sum(1 for f in Family.objects.all() if f.is_trial_active)

        return Response({
            'users': {
                'total':         total_users,
                'parents':       total_parents,
                'children':      total_children,
                'new_this_week': new_this_week,
                'new_this_month': new_this_month,
            },
            'families': {
                'total':   total_families,
                'vip':     vip_families,
                'free':    free_families,
                'trial':   trial_families,
            },
        })


class UserListView(APIView):
    """Barcha foydalanuvchilar"""
    permission_classes = (IsAdminUser,)

    @extend_schema(summary="Foydalanuvchilar ro'yxati", tags=["Admin"])
    def get(self, request):
        role   = request.query_params.get('role')
        search = request.query_params.get('search', '').strip()

        qs = User.objects.order_by('-created_at')
        if role:
            qs = qs.filter(role=role)
        if search:
            qs = qs.filter(
                Q(email__icontains=search) | Q(full_name__icontains=search)
            )

        data = [
            {
                'id':         str(u.id),
                'email':      u.email,
                'full_name':  u.full_name,
                'phone':      u.phone,
                'role':       u.role,
                'is_active':  u.is_active,
                'created_at': u.created_at,
                'avatar':     request.build_absolute_uri(u.avatar.url) if u.avatar else None,
            }
            for u in qs
        ]
        return Response({'count': len(data), 'results': data})


class UserDetailView(APIView):
    """Foydalanuvchi detali + block/unblock"""
    permission_classes = (IsAdminUser,)

    def _get_user(self, user_id):
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None

    @extend_schema(summary="Foydalanuvchi detali", tags=["Admin"])
    def get(self, request, user_id):
        user = self._get_user(user_id)
        if not user:
            return Response({'detail': 'Topilmadi.'}, status=404)

        families = FamilyMember.objects.filter(
            user=user, is_active=True
        ).select_related('family')

        return Response({
            'id':         str(user.id),
            'email':      user.email,
            'full_name':  user.full_name,
            'phone':      user.phone,
            'role':       user.role,
            'is_active':  user.is_active,
            'created_at': user.created_at,
            'avatar':     request.build_absolute_uri(user.avatar.url) if user.avatar else None,
            'families': [
                {
                    'id':       str(m.family.id),
                    'name':     m.family.name,
                    'role':     m.role,
                    'plan':     m.family.effective_plan,
                }
                for m in families
            ],
        })

    @extend_schema(summary="Foydalanuvchini bloklash/ochish", tags=["Admin"])
    def patch(self, request, user_id):
        user = self._get_user(user_id)
        if not user:
            return Response({'detail': 'Topilmadi.'}, status=404)
        is_active = request.data.get('is_active')
        if is_active is None:
            return Response({'detail': 'is_active maydoni kerak.'}, status=400)
        user.is_active = bool(is_active)
        user.save(update_fields=['is_active'])
        return Response({'id': str(user.id), 'is_active': user.is_active})


class FamilyListView(APIView):
    """Barcha oilalar"""
    permission_classes = (IsAdminUser,)

    @extend_schema(summary="Oilalar ro'yxati", tags=["Admin"])
    def get(self, request):
        search = request.query_params.get('search', '').strip()
        plan   = request.query_params.get('plan')

        qs = Family.objects.prefetch_related('members').order_by('-created_at')
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(invite_code__icontains=search)
            )

        data = []
        for f in qs:
            ep = f.effective_plan
            if plan and ep != plan:
                continue
            data.append({
                'id':              str(f.id),
                'name':            f.name,
                'invite_code':     f.invite_code,
                'plan':            ep,
                'is_trial':        f.is_trial_active,
                'trial_ends_at':   f.trial_ends_at,
                'vip_expires_at':  f.vip_expires_at,
                'members_count':   f.members_count,
                'children_count':  f.children_count,
                'created_by':      f.created_by.email,
                'created_at':      f.created_at,
            })

        return Response({'count': len(data), 'results': data})


class FamilyDetailView(APIView):
    """Oila detali + plan upgrade/downgrade"""
    permission_classes = (IsAdminUser,)

    def _get_family(self, family_id):
        try:
            return Family.objects.prefetch_related('members__user').get(id=family_id)
        except Family.DoesNotExist:
            return None

    @extend_schema(summary="Oila detali", tags=["Admin"])
    def get(self, request, family_id):
        family = self._get_family(family_id)
        if not family:
            return Response({'detail': 'Topilmadi.'}, status=404)

        members = [
            {
                'id':        str(m.id),
                'user_id':   str(m.user.id),
                'full_name': m.user.full_name,
                'email':     m.user.email,
                'role':      m.role,
                'is_active': m.is_active,
                'joined_at': m.joined_at,
            }
            for m in family.members.all()
        ]

        return Response({
            'id':             str(family.id),
            'name':           family.name,
            'invite_code':    family.invite_code,
            'plan':           family.effective_plan,
            'is_trial':       family.is_trial_active,
            'trial_ends_at':  family.trial_ends_at,
            'vip_expires_at': family.vip_expires_at,
            'max_children':   family.max_children,
            'created_by':     family.created_by.email,
            'created_at':     family.created_at,
            'home_address':   family.home_address,
            'members':        members,
        })

    @extend_schema(summary="Oila planini o'zgartirish", tags=["Admin"])
    def patch(self, request, family_id):
        """
        { "plan": "vip", "duration_days": 30 }  — VIP aktivlashtirish
        { "plan": "free" }                       — FREE ga tushirish
        """
        family = self._get_family(family_id)
        if not family:
            return Response({'detail': 'Topilmadi.'}, status=404)

        plan = request.data.get('plan')
        if plan not in ('vip', 'free'):
            return Response({'detail': 'plan: "vip" yoki "free" bo\'lishi kerak.'}, status=400)

        if plan == 'vip':
            from datetime import timedelta
            days = int(request.data.get('duration_days', 30))
            now  = timezone.now()
            base = family.vip_expires_at if (family.vip_expires_at and family.vip_expires_at > now) else now
            family.plan = Family.Plan.VIP
            family.vip_expires_at = base + timedelta(days=days)
        else:
            family.plan = Family.Plan.FREE
            family.vip_expires_at = None

        family.save(update_fields=['plan', 'vip_expires_at'])
        return Response({
            'id':            str(family.id),
            'plan':          family.effective_plan,
            'vip_expires_at': family.vip_expires_at,
        })


class AppStatsView(APIView):
    """Eng ko'p ishlatiladigan va taqiqlangan ilovalar reytingi"""
    permission_classes = (IsAdminUser,)

    @extend_schema(summary="Ilovalar statistikasi", tags=["Admin"])
    def get(self, request):
        # Eng ko'p ishlatiladigan ilovalar (jami sekund bo'yicha)
        top_used = (
            DailyUsageSummary.objects
            .values('package_name', 'app_label')
            .annotate(total_secs=Sum('total_secs'), users_count=Count('child', distinct=True))
            .order_by('-total_secs')[:20]
        )

        # Eng ko'p taqiqlangan ilovalar
        top_blocked = (
            AppRule.objects
            .filter(is_blocked=True)
            .values('package_name', 'app_label')
            .annotate(block_count=Count('id'))
            .order_by('-block_count')[:20]
        )

        # Eng ko'p limit qo'yilgan ilovalar
        top_limited = (
            AppRule.objects
            .filter(is_blocked=False, daily_limit_mins__isnull=False)
            .values('package_name', 'app_label')
            .annotate(limit_count=Count('id'))
            .order_by('-limit_count')[:20]
        )

        def fmt_mins(secs):
            return round(secs / 60, 1) if secs else 0

        return Response({
            'top_used': [
                {
                    'package_name': r['package_name'],
                    'app_label':    r['app_label'] or r['package_name'],
                    'total_mins':   fmt_mins(r['total_secs']),
                    'users_count':  r['users_count'],
                }
                for r in top_used
            ],
            'top_blocked': [
                {
                    'package_name': r['package_name'],
                    'app_label':    r['app_label'] or r['package_name'],
                    'block_count':  r['block_count'],
                }
                for r in top_blocked
            ],
            'top_limited': [
                {
                    'package_name': r['package_name'],
                    'app_label':    r['app_label'] or r['package_name'],
                    'limit_count':  r['limit_count'],
                }
                for r in top_limited
            ],
        })
