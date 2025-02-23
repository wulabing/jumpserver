from django.db import models
from django.utils.translation import gettext_lazy as _

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
    public = models.BooleanField(default=True, verbose_name=_('Public'))
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
