import base64
import json
import os
import urllib.parse

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

from assets.const import CloudTypes
from common.api import JMSModelViewSet
from common.exceptions import JMSException
from common.utils import random_string, get_logger
from common.utils.django import get_request_os
from common.utils.http import is_true
from orgs.mixins.api import RootOrgViewMixin
from perms.models import ActionChoices
from terminal.connect_methods import NativeClient, ConnectMethodUtil
from terminal.models import EndpointRule
from ..models import ConnectionToken, date_expired_default
from ..serializers import (
    ConnectionTokenSerializer, ConnectionTokenSecretSerializer,
    SuperConnectionTokenSerializer, ConnectTokenAppletOptionSerializer
)

__all__ = ['ConnectionTokenViewSet', 'SuperConnectionTokenViewSet']
logger = get_logger(__name__)


class RDPFileClientProtocolURLMixin:
    request: Request
    get_serializer: callable

    def get_rdp_file_info(self, token: ConnectionToken):
        rdp_options = {
            'full address:s': '',
            'username:s': '',
            'use multimon:i': '0',
            'session bpp:i': '32',
            'audiomode:i': '0',
            'disable wallpaper:i': '0',
            'disable full window drag:i': '0',
            'disable menu anims:i': '0',
            'disable themes:i': '0',
            'alternate shell:s': '',
            'shell working directory:s': '',
            'authentication level:i': '2',
            'connect to console:i': '0',
            'disable cursor setting:i': '0',
            'allow font smoothing:i': '1',
            'allow desktop composition:i': '1',
            'redirectprinters:i': '0',
            'prompt for credentials on client:i': '0',
            'autoreconnection enabled:i': '1',
            'bookmarktype:i': '3',
            'use redirection server name:i': '0',
            'smart sizing:i': '1',
        }

        # 设置磁盘挂载
        drives_redirect = is_true(self.request.query_params.get('drives_redirect'))
        if drives_redirect:
            if ActionChoices.contains(token.actions, ActionChoices.transfer()):
                rdp_options['drivestoredirect:s'] = '*'

        # 设置全屏
        full_screen = is_true(self.request.query_params.get('full_screen'))
        rdp_options['screen mode id:i'] = '2' if full_screen else '1'

        # 设置 RDP Server 地址
        endpoint = self.get_smart_endpoint(protocol='rdp', asset=token.asset)
        rdp_options['full address:s'] = f'{endpoint.host}:{endpoint.rdp_port}'

        # 设置用户名
        rdp_options['username:s'] = '{}|{}'.format(token.user.username, str(token.id))
        # rdp_options['domain:s'] = token.account_ad_domain

        # 设置宽高
        height = self.request.query_params.get('height')
        width = self.request.query_params.get('width')
        if width and height:
            rdp_options['desktopwidth:i'] = width
            rdp_options['desktopheight:i'] = height
            rdp_options['winposstr:s:'] = f'0,1,0,0,{width},{height}'

        # 设置其他选项
        rdp_options['session bpp:i'] = os.getenv('JUMPSERVER_COLOR_DEPTH', '32')
        rdp_options['audiomode:i'] = self.parse_env_bool('JUMPSERVER_DISABLE_AUDIO', 'false', '2', '0')

        # 设置远程应用, 不是 Mstsc
        if token.connect_method != NativeClient.mstsc:
            remote_app_options = token.get_remote_app_option()
            rdp_options.update(remote_app_options)

        # 文件名
        name = token.asset.name
        prefix_name = f'{token.user.username}-{name}'
        filename = self.get_connect_filename(prefix_name)

        content = ''
        for k, v in rdp_options.items():
            content += f'{k}:{v}\n'

        return filename, content

    @staticmethod
    def get_connect_filename(prefix_name):
        prefix_name = prefix_name.replace('/', '_')
        prefix_name = prefix_name.replace('\\', '_')
        prefix_name = prefix_name.replace('.', '_')
        filename = f'{prefix_name}-jumpserver'
        filename = urllib.parse.quote(filename)
        return filename

    @staticmethod
    def parse_env_bool(env_key, env_default, true_value, false_value):
        return true_value if is_true(os.getenv(env_key, env_default)) else false_value

    def get_client_protocol_data(self, token: ConnectionToken):
        _os = get_request_os(self.request)

        connect_method_name = token.connect_method
        connect_method_dict = ConnectMethodUtil.get_connect_method(
            token.connect_method, token.protocol, _os
        )
        if connect_method_dict is None:
            raise ValueError('Connect method not support: {}'.format(connect_method_name))

        data = {
            'id': str(token.id),
            'value': token.value,
            'protocol': token.protocol,
            'command': '',
            'file': {}
        }

        if connect_method_name == NativeClient.mstsc or connect_method_dict['type'] == 'applet':
            filename, content = self.get_rdp_file_info(token)
            data.update({
                'protocol': 'rdp',
                'file': {
                    'name': filename,
                    'content': content,
                }
            })
        else:
            endpoint = self.get_smart_endpoint(
                protocol=connect_method_dict['endpoint_protocol'],
                asset=token.asset
            )
            cmd = NativeClient.get_launch_command(connect_method_name, token, endpoint)
            data.update({'command': cmd})
        return data

    def get_smart_endpoint(self, protocol, asset=None):
        target_ip = asset.get_target_ip() if asset else ''
        endpoint = EndpointRule.match_endpoint(
            target_instance=asset, target_ip=target_ip, protocol=protocol, request=self.request
        )
        return endpoint


class ExtraActionApiMixin(RDPFileClientProtocolURLMixin):
    request: Request
    get_object: callable
    get_serializer: callable
    perform_create: callable
    validate_exchange_token: callable

    @action(methods=['POST', 'GET'], detail=True, url_path='rdp-file')
    def get_rdp_file(self, *args, **kwargs):
        token = self.get_object()
        token.is_valid()
        filename, content = self.get_rdp_file_info(token)
        filename = '{}.rdp'.format(filename)
        response = HttpResponse(content, content_type='application/octet-stream')
        response['Content-Disposition'] = 'attachment; filename*=UTF-8\'\'%s' % filename
        return response

    @action(methods=['POST', 'GET'], detail=True, url_path='client-url')
    def get_client_protocol_url(self, *args, **kwargs):
        token = self.get_object()
        token.is_valid()
        try:
            protocol_data = self.get_client_protocol_data(token)
        except ValueError as e:
            return Response(data={'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        protocol_data = json.dumps(protocol_data).encode()
        protocol_data = base64.b64encode(protocol_data).decode()
        data = {
            'url': 'jms://{}'.format(protocol_data)
        }
        return Response(data=data)

    @action(methods=['PATCH'], detail=True)
    def expire(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.expire()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=['POST'], detail=False)
    def exchange(self, request, *args, **kwargs):
        pk = request.data.get('id', None) or request.data.get('pk', None)
        # 只能兑换自己使用的 Token
        instance = get_object_or_404(ConnectionToken, pk=pk, user=request.user)
        instance.id = None
        self.validate_exchange_token(instance)
        instance.date_expired = date_expired_default()
        instance.save()
        serializer = self.get_serializer(instance)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConnectionTokenViewSet(ExtraActionApiMixin, RootOrgViewMixin, JMSModelViewSet):
    filterset_fields = (
        'user_display', 'asset_display'
    )
    search_fields = filterset_fields
    serializer_classes = {
        'default': ConnectionTokenSerializer,
    }
    rbac_perms = {
        'list': 'authentication.view_connectiontoken',
        'retrieve': 'authentication.view_connectiontoken',
        'create': 'authentication.add_connectiontoken',
        'exchange': 'authentication.add_connectiontoken',
        'expire': 'authentication.change_connectiontoken',
        'get_rdp_file': 'authentication.add_connectiontoken',
        'get_client_protocol_url': 'authentication.add_connectiontoken',
    }

    def get_queryset(self):
        queryset = ConnectionToken.objects \
            .filter(user=self.request.user) \
            .filter(date_expired__gt=timezone.now())
        return queryset

    def get_user(self, serializer):
        return self.request.user

    def perform_create(self, serializer):
        self.validate_serializer(serializer)
        return super().perform_create(serializer)

    def validate_serializer(self, serializer):
        data = serializer.validated_data
        user = self.get_user(serializer)
        asset = data.get('asset')
        account_name = data.get('account')
        _data = self._validate(user, asset, account_name)
        data.update(_data)
        return serializer

    def validate_exchange_token(self, token):
        user = token.user
        asset = token.asset
        account_name = token.account
        _data = self._validate(user, asset, account_name)
        for k, v in _data.items():
            setattr(token, k, v)
        return token

    def _validate(self, user, asset, account_name):
        data = dict()
        data['org_id'] = asset.org_id
        data['user'] = user
        data['value'] = random_string(16)
        account = self._validate_perm(user, asset, account_name)
        if account.has_secret:
            data['input_secret'] = ''

        if account.username != '@INPUT':
            data['input_username'] = ''
        if account.username == '@USER':
            data['input_username'] = user.username

        ticket = self._validate_acl(user, asset, account)
        if ticket:
            data['from_ticket'] = ticket
            data['is_active'] = False
        return data

    @staticmethod
    def _validate_perm(user, asset, account_name):
        from perms.utils.account import PermAccountUtil
        account = PermAccountUtil().validate_permission(user, asset, account_name)
        if not account or not account.actions:
            msg = _('Account not found')
            raise JMSException(code='perm_account_invalid', detail=msg)
        if account.date_expired < timezone.now():
            msg = _('Permission expired')
            raise JMSException(code='perm_expired', detail=msg)
        return account

    def _validate_acl(self, user, asset, account):
        from acls.models import LoginAssetACL
        acl = LoginAssetACL.filter_queryset(user, asset, account).valid().first()
        if not acl:
            return
        if acl.is_action(acl.ActionChoices.accept):
            return
        if acl.is_action(acl.ActionChoices.reject):
            msg = _('ACL action is reject')
            raise JMSException(code='acl_reject', detail=msg)
        if acl.is_action(acl.ActionChoices.review):
            if not self.request.query_params.get('create_ticket'):
                msg = _('ACL action is review')
                raise JMSException(code='acl_review', detail=msg)

            ticket = LoginAssetACL.create_login_asset_review_ticket(
                user=user, asset=asset, account_username=account.username,
                assignees=acl.reviewers.all(), org_id=asset.org_id
            )
            return ticket


class SuperConnectionTokenViewSet(ConnectionTokenViewSet):
    serializer_classes = {
        'default': SuperConnectionTokenSerializer,
        'get_secret_detail': ConnectionTokenSecretSerializer,
    }
    rbac_perms = {
        'create': 'authentication.add_superconnectiontoken',
        'renewal': 'authentication.add_superconnectiontoken',
        'get_secret_detail': 'authentication.view_connectiontokensecret',
        'get_applet_info': 'authentication.view_superconnectiontoken',
        'release_applet_account': 'authentication.view_superconnectiontoken',
    }

    def get_queryset(self):
        return ConnectionToken.objects.all()

    def get_user(self, serializer):
        return serializer.validated_data.get('user')

    @action(methods=['PATCH'], detail=False)
    def renewal(self, request, *args, **kwargs):
        from common.utils.timezone import as_current_tz

        token_id = request.data.get('id') or ''
        token = get_object_or_404(ConnectionToken, pk=token_id)
        date_expired = as_current_tz(token.date_expired)
        if token.is_expired:
            raise PermissionDenied('Token is expired at: {}'.format(date_expired))
        token.renewal()
        data = {
            'ok': True,
            'msg': f'Token is renewed, date expired: {date_expired}'
        }
        return Response(data=data, status=status.HTTP_200_OK)

    @action(methods=['POST'], detail=False, url_path='secret')
    def get_secret_detail(self, request, *args, **kwargs):
        """ 非常重要的 api, 在逻辑层再判断一下 rbac 权限, 双重保险 """
        rbac_perm = 'authentication.view_connectiontokensecret'
        if not request.user.has_perm(rbac_perm):
            raise PermissionDenied('Not allow to view secret')

        token_id = request.data.get('id') or ''
        token = get_object_or_404(ConnectionToken, pk=token_id)
        if token.is_expired:
            raise ValidationError({'id': 'Token is expired'})

        token.is_valid()
        serializer = self.get_serializer(instance=token)
        expire_now = request.data.get('expire_now', True)

        # TODO 暂时特殊处理 k8s 不过期
        if token.asset.type == CloudTypes.K8S:
            expire_now = False

        if expire_now:
            token.expire()
        return Response(serializer.data, status=status.HTTP_200_OK)

    @action(methods=['POST'], detail=False, url_path='applet-option')
    def get_applet_info(self, *args, **kwargs):
        token_id = self.request.data.get('id')
        token = get_object_or_404(ConnectionToken, pk=token_id)
        if token.is_expired:
            return Response({'error': 'Token expired'}, status=status.HTTP_400_BAD_REQUEST)
        data = token.get_applet_option()
        serializer = ConnectTokenAppletOptionSerializer(data)
        return Response(serializer.data)

    @action(methods=['DELETE', 'POST'], detail=False, url_path='applet-account/release')
    def release_applet_account(self, *args, **kwargs):
        account_id = self.request.data.get('id')
        released = ConnectionToken.release_applet_account(account_id)

        if released:
            logger.debug('Release applet account success: {}'.format(account_id))
            return Response({'msg': 'released'})
        else:
            logger.error('Release applet account error: {}'.format(account_id))
            return Response({'error': 'not found or expired'}, status=400)
