from rest_framework import serializers, viewsets
from rest_framework.permissions import IsAuthenticated

from core.models import LegacyCustomerHistory
from core.permissions import IsManagerOrStaff
from core.store_access import get_user_store


class LegacyHistorySerializer(serializers.ModelSerializer):
    visit_count = serializers.SerializerMethodField()
    history_text = serializers.CharField(read_only=True)

    class Meta:
        model = LegacyCustomerHistory
        fields = ["id", "customer", "legacy_customer_id", "display_name", "phone", "visit_count", "history_text", "link_reason"]
        read_only_fields = fields

    def get_visit_count(self, obj) -> int:
        return len(obj.entries)

    def get_fields(self):
        fields = super().get_fields()
        if self.context.get("view") and self.context["view"].action == "list":
            fields.pop("history_text", None)
        return fields


class LegacyHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LegacyCustomerHistory.objects.none()
    serializer_class = LegacyHistorySerializer
    permission_classes = [IsAuthenticated, IsManagerOrStaff]
    search_fields = ["legacy_customer_id", "display_name", "phone"]
    filterset_fields = ["customer"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return LegacyCustomerHistory.objects.none()
        return LegacyCustomerHistory.objects.filter(store=get_user_store(self.request)).order_by("display_name", "id")
