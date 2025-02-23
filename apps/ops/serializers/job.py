import uuid

from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from assets.models import Node, Asset
from perms.utils.user_perm import UserPermAssetUtil
from common.serializers.fields import ReadableHiddenField
from ops.mixin import PeriodTaskSerializerMixin
from ops.models import Job, JobExecution
from orgs.mixins.serializers import BulkOrgResourceModelSerializer


class JobSerializer(BulkOrgResourceModelSerializer, PeriodTaskSerializerMixin):
    creator = ReadableHiddenField(default=serializers.CurrentUserDefault())
    run_after_save = serializers.BooleanField(label=_("Run after save"), default=False, required=False)
    nodes = serializers.ListField(required=False, child=serializers.CharField())
    date_last_run = serializers.DateTimeField(label=_('Date last run'), read_only=True)
    name = serializers.CharField(label=_('Name'), max_length=128, allow_blank=True, required=False)
    assets = serializers.PrimaryKeyRelatedField(label=_('Assets'), queryset=Asset.objects, many=True,
                                                required=False)

    def to_internal_value(self, data):
        instant = data.get('instant', False)
        if instant:
            _uid = str(uuid.uuid4()).split('-')[-1]
            data['name'] = f'job-{_uid}'
        return super().to_internal_value(data)

    def get_request_user(self):
        request = self.context.get('request')
        user = request.user if request else None
        return user

    def create(self, validated_data):
        assets = validated_data.__getitem__('assets')
        node_ids = validated_data.pop('nodes', None)
        if node_ids:
            user = self.get_request_user()
            perm_util = UserPermAssetUtil(user=user)
            for node_id in node_ids:
                node, node_assets = perm_util.get_node_all_assets(node_id)
                assets.extend(node_assets.exclude(id__in=[asset.id for asset in assets]))
        return super().create(validated_data)

    class Meta:
        model = Job
        read_only_fields = [
            "id", "date_last_run", "date_created", "date_updated", "average_time_cost"
        ]
        fields = read_only_fields + [
            "name", "instant", "type", "module",
            "args", "playbook", "assets",
            "runas_policy", "runas", "creator",
            "use_parameter_define", "parameters_define",
            "timeout", "chdir", "comment", "summary",
            "is_periodic", "interval", "crontab", "nodes",
            "run_after_save",
        ]


class JobExecutionSerializer(BulkOrgResourceModelSerializer):
    creator = ReadableHiddenField(default=serializers.CurrentUserDefault())
    job_type = serializers.ReadOnlyField(label=_("Job type"))
    material = serializers.ReadOnlyField(label=_("Command"))
    is_success = serializers.ReadOnlyField(label=_("Is success"))
    is_finished = serializers.ReadOnlyField(label=_("Is finished"))
    time_cost = serializers.ReadOnlyField(label=_("Time cost"))

    class Meta:
        model = JobExecution
        read_only_fields = ["id", "task_id", "timedelta", "time_cost",
                            'is_finished', 'date_start', 'date_finished',
                            'date_created', 'is_success', 'job_type',
                            'summary', 'material']
        fields = read_only_fields + [
            "job", "parameters", "creator"
        ]
