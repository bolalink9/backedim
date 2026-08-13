from django.utils import timezone
from rest_framework import serializers
from .models import AppRule, DailyUsageSummary


class AppRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model  = AppRule
        fields = (
            'package_name', 'app_label',
            'is_blocked', 'daily_limit_mins',
            'updated_at',
        )
        read_only_fields = ('updated_at',)


class AppRuleWriteSerializer(serializers.Serializer):
    """Parent ilovaga qoida qo'yadi yoki yangilaydi."""
    package_name     = serializers.CharField(max_length=200)
    app_label        = serializers.CharField(max_length=100, required=False, default='')
    is_blocked       = serializers.BooleanField(default=False)
    daily_limit_mins = serializers.IntegerField(min_value=1, allow_null=True, required=False)

    def validate(self, data):
        if data.get('is_blocked') and data.get('daily_limit_mins'):
            raise serializers.ValidationError(
                "Bir vaqtda is_blocked=true va daily_limit_mins bo'lishi mumkin emas."
            )
        return data

    def save(self, family, child, set_by):
        rule, _ = AppRule.objects.update_or_create(
            family=family,
            child=child,
            package_name=self.validated_data['package_name'],
            defaults={
                'app_label':        self.validated_data.get('app_label', ''),
                'is_blocked':       self.validated_data['is_blocked'],
                'daily_limit_mins': self.validated_data.get('daily_limit_mins'),
                'set_by':           set_by,
            },
        )
        return rule


class UsageItemSerializer(serializers.Serializer):
    """Bitta ilovaning sync ma'lumoti — Android dan keladi."""
    package_name = serializers.CharField(max_length=200)
    app_label    = serializers.CharField(max_length=100, required=False, default='')
    total_secs   = serializers.IntegerField(min_value=0)  # bugun bosidan hozirga qadar jami


class SyncSerializer(serializers.Serializer):
    """
    Bola telefoni har 15-30 daqiqada shu so'rovni yuboradi.
    Android UsageStatsManager bugungi jami sekundlarni beradi —
    biz old qiymat bilan farqni hisoblamaymiz, to'g'ridan yig'indini yozamiz.
    """
    date  = serializers.DateField()   # YYYY-MM-DD  (qurilma sanasi)
    usage = UsageItemSerializer(many=True)

    def save(self, family, child):
        today = self.validated_data['date']
        rules_response = []

        for item in self.validated_data['usage']:
            pkg   = item['package_name']
            label = item.get('app_label', '')
            secs  = item['total_secs']

            # Kunlik yig'indini upsert qilamiz
            DailyUsageSummary.objects.update_or_create(
                child=child,
                date=today,
                package_name=pkg,
                defaults={
                    'family':    family,
                    'app_label': label,
                    'total_secs': secs,
                },
            )

        # Barcha qoidalarni qaytaramiz — Android shu asosda ilovani bloklaydi
        rules = AppRule.objects.filter(family=family, child=child)
        return AppRuleSerializer(rules, many=True).data


class DailyUsageSerializer(serializers.ModelSerializer):
    total_mins = serializers.IntegerField(read_only=True)

    class Meta:
        model  = DailyUsageSummary
        fields = ('package_name', 'app_label', 'total_secs', 'total_mins', 'date')
