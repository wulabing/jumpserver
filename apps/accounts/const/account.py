from django.db.models import TextChoices
from django.utils.translation import ugettext_lazy as _


class SecretType(TextChoices):
    PASSWORD = 'password', _('Password')
    SSH_KEY = 'ssh_key', _('SSH key')
    ACCESS_KEY = 'access_key', _('Access key')
    TOKEN = 'token', _('Token')


class AliasAccount(TextChoices):
    ALL = '@ALL', _('All')
    INPUT = '@INPUT', _('Manual input')
    USER = '@USER', _('Dynamic user')


class Source(TextChoices):
    LOCAL = 'local', _('Local')
    COLLECTED = 'collected', _('Collected')


class AccountInvalidPolicy(TextChoices):
    SKIP = 'skip', _('Skip')
    UPDATE = 'update', _('Update')
    ERROR = 'error', _('Failed')
