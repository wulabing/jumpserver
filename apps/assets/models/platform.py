from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from assets.const import AllTypes
from assets.const import Protocol
from common.db.fields import JsonDictTextField
from common.db.models import JMSBaseModel

__all__ = ['Platform', 'PlatformProtocol', 'PlatformAutomation']


class PlatformProtocol(models.Model):
    name = models.CharField(max_length=32, verbose_name=_('Name'))
    port = models.IntegerField(verbose_name=_('Port'))
    primary = models.BooleanField(default=False, verbose_name=_('Primary'))
    required = models.BooleanField(default=False, verbose_name=_('Required'))
    default = models.BooleanField(default=False, verbose_name=_('Default'))
    setting = models.JSONField(verbose_name=_('Setting'), default=dict)
    platform = models.ForeignKey('Platform', on_delete=models.CASCADE, related_name='protocols')

    def __str__(self):
        return '{}/{}'.format(self.name, self.port)

    @property
    def secret_types(self):
        return Protocol.settings().get(self.name, {}).get('secret_types')


class PlatformAutomation(models.Model):
    ansible_enabled = models.BooleanField(default=False, verbose_name=_("Enabled"))
    ansible_config = models.JSONField(default=dict, verbose_name=_("Ansible config"))
    ping_enabled = models.BooleanField(default=False, verbose_name=_("Ping enabled"))
    ping_method = models.CharField(max_length=32, blank=True, null=True, verbose_name=_("Ping method"))
    gather_facts_enabled = models.BooleanField(default=False, verbose_name=_("Gather facts enabled"))
    gather_facts_method = models.TextField(max_length=32, blank=True, null=True, verbose_name=_("Gather facts method"))
    change_secret_enabled = models.BooleanField(default=False, verbose_name=_("Change secret enabled"))
    change_secret_method = models.TextField(
        max_length=32, blank=True, null=True, verbose_name=_("Change secret method")
    )
    push_account_enabled = models.BooleanField(default=False, verbose_name=_("Push account enabled"))
    push_account_method = models.TextField(
        max_length=32, blank=True, null=True, verbose_name=_("Push account method")
    )
    verify_account_enabled = models.BooleanField(default=False, verbose_name=_("Verify account enabled"))
    verify_account_method = models.TextField(
        max_length=32, blank=True, null=True, verbose_name=_("Verify account method"))
    gather_accounts_enabled = models.BooleanField(default=False, verbose_name=_("Gather facts enabled"))
    gather_accounts_method = models.TextField(
        max_length=32, blank=True, null=True, verbose_name=_("Gather facts method")
    )
    params = models.JSONField(default=dict, verbose_name=_("Params"))

    @staticmethod
    def get_empty_serializer():
        serializer_name = 'EmptySerializer'
        return type(serializer_name, (serializers.Serializer,), {})

    @classmethod
    def generate_params_serializer(cls, instance, ansible_method_id):
        serializer_class = cls.get_empty_serializer()

        if instance is None:
            return serializer_class

        info = instance.__dict__
        if not instance.ansible_enabled:
            return serializer_class
        info.pop('ansible_enabled', None)

        allow_ansible_method_ids = []
        for k, v in info.items():
            if k.endswith('_enabled') and info[k]:
                allow_ansible_method_ids.append(info[k.strip('_enabled') + '_method'])

        if ansible_method_id not in allow_ansible_method_ids:
            return serializer_class
        return cls.get_ansible_serializer(ansible_method_id)

    @classmethod
    def get_ansible_serializer(cls, ansible_method_id):
        serializer_class = cls.get_empty_serializer()
        platform_automation_methods = AllTypes.get_automation_methods()
        for i in platform_automation_methods:
            if i['id'] != ansible_method_id:
                continue
            return i['serializer'] if i['serializer'] else serializer_class
        return serializer_class


class Platform(JMSBaseModel):
    """
    对资产提供 约束和默认值
    对资产进行抽象
    """

    class CharsetChoices(models.TextChoices):
        utf8 = 'utf-8', 'UTF-8'
        gbk = 'gbk', 'GBK'

    id = models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')
    name = models.SlugField(verbose_name=_("Name"), unique=True, allow_unicode=True)
    category = models.CharField(default='host', max_length=32, verbose_name=_("Category"))
    type = models.CharField(max_length=32, default='linux', verbose_name=_("Type"))
    meta = JsonDictTextField(blank=True, null=True, verbose_name=_("Meta"))
    internal = models.BooleanField(default=False, verbose_name=_("Internal"))
    # 资产有关的
    charset = models.CharField(
        default=CharsetChoices.utf8, choices=CharsetChoices.choices, max_length=8, verbose_name=_("Charset")
    )
    domain_enabled = models.BooleanField(default=True, verbose_name=_("Domain enabled"))
    # 账号有关的
    su_enabled = models.BooleanField(default=False, verbose_name=_("Su enabled"))
    su_method = models.CharField(max_length=32, blank=True, null=True, verbose_name=_("Su method"))
    automation = models.OneToOneField(PlatformAutomation, on_delete=models.CASCADE, related_name='platform',
                                      blank=True, null=True, verbose_name=_("Automation"))

    @property
    def type_constraints(self):
        return AllTypes.get_constraints(self.category, self.type)

    @classmethod
    def default(cls):
        linux, created = cls.objects.get_or_create(
            defaults={'name': 'Linux'}, name='Linux'
        )
        return linux.id

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Platform")
        # ordering = ('name',)
