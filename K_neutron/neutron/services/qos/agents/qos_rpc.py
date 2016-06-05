# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2013 OpenStack Foundation
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#

from oslo_config import cfg
from oslo_log import log as logging
from oslo_utils import importutils

from neutron.common import topics

LOG = logging.getLogger(__name__)
QOS_RPC_VERSION = "1.1"


QoSOpts = [
    cfg.StrOpt(
        'qos_driver',
        default='neutron.services.qos.drivers.ovs_qos.OVSHybridQoSDriver'),
    cfg.StrOpt(
        'floating_ip_qos_driver')
]

cfg.CONF.register_opts(QoSOpts, "qos")


class QoSAgentRpcApiMixin(object):
    """Agent side of the QoS Plugin RPC API."""

    def _get_qos_topic(self):
        return topics.get_topic_name(self.topic,
                                     topics.QOS,
                                     topics.UPDATE)

    def network_qos_deleted(self, context, qos_id, network_id):
        cctxt = self.client.prepare(version=QOS_RPC_VERSION,
                                    topic=self._get_qos_topic(),
                                    fanout=True)
        cctxt.cast(context, 'network_qos_deleted',
                   qos_id=qos_id, network_id=network_id)

    def network_qos_updated(self, context, qos_id, network_id):
        cctxt = self.client.prepare(version=QOS_RPC_VERSION,
                                    topic=self._get_qos_topic(),
                                    fanout=True)
        cctxt.cast(context, 'network_qos_updated',
                   qos_id=qos_id, network_id=network_id)

    def port_qos_deleted(self, context, qos_id, port_id):
        cctxt = self.client.prepare(version=QOS_RPC_VERSION,
                                    topic=self._get_qos_topic(),
                                    fanout=True)
        cctxt.cast(context, 'port_qos_deleted',
                   port_id=port_id, qos_id=qos_id)

    def port_qos_updated(self, context, qos_id, port_id):
        cctxt = self.client.prepare(version=QOS_RPC_VERSION,
                                    topic=self._get_qos_topic(),
                                    fanout=True)
        cctxt.cast(context, 'port_qos_updated',
                   qos_id=qos_id, port_id=port_id)


class QoSServerRpcApiMixin(object):
    """A mix-in that enables QoS support in the plugin rpc."""

    def get_policy_for_qos(self, context, qos_id):
        LOG.debug(_("Get policy for QoS ID: %s"
                    "via RPC"), qos_id)
        cctxt = self.client.prepare(version='1.0')
        return cctxt.call(context, 'get_policy_for_qos', qos_id=qos_id)

    def get_port_and_qos_policy(self, context, port_id):
        LOG.debug(_("Get port and QoS policies of Port ID: %s "
                    "via RPC"), port_id)
        cctxt = self.client.prepare(version='1.0')
        return cctxt.call(context, 'get_port_and_qos_policy', port_id=port_id)


class QoSAgentRpcMixin(object):

    def init_qos(self, *args, **kwargs):
        qos_driver = cfg.CONF.qos.qos_driver
        LOG.debug(_("Starting QoS driver %s"), qos_driver)
        self.qos = importutils.import_object(qos_driver, *args, **kwargs)

    def network_qos_deleted(self, context, qos_id, network_id):
        self.qos.delete_qos_for_network(network_id)

    def network_qos_updated(self, context, qos_id, network_id):
        qos_policy = self.plugin_rpc.get_policy_for_qos(context, qos_id)
        self.qos.network_qos_updated(qos_policy, network_id)

    def port_qos_updated(self, context, qos_id, port_id, **kwargs):
        qos_policy = self.plugin_rpc.get_policy_for_qos(context, qos_id)
        self.qos.port_qos_updated(qos_policy, port_id,
                                  context=kwargs.get('ctx', None))

    def port_qos_deleted(self, context, qos_id, port_id, **kwargs):
        self.qos.delete_qos_for_port(port_id, context=kwargs.get('ctx', None))

    def port_qos_sync(self, context, ports_dict):
        self.qos.port_qos_sync(ports_dict)


class QoSAgentRpcCallbackMixin(object):

    # TODO(scollins) See if we need this - copied from
    # SecurityGroupAgentRpcCallbackMixin
    qos_agent = None

    def network_qos_updated(self, context, **kwargs):
        qos_id = kwargs.get('qos_id', '')
        network_id = kwargs.get('network_id', '')
        LOG.debug(_('QoS %(qos_id)s updated on remote: %(network_id)s')
                  % kwargs)
        self.qos_agent.network_qos_updated(context, qos_id, network_id)

    def network_qos_deleted(self, context, **kwargs):
        qos_id = kwargs.get('qos_id', '')
        network_id = kwargs.get('network_id', '')
        LOG.debug(_('QoS %(qos_id)s updated on remote: %(network_id)s')
                  % kwargs)
        self.qos_agent.network_qos_deleted(context, qos_id, network_id)

    def port_qos_deleted(self, context, **kwargs):
        qos_id = kwargs.get('qos_id', '')
        port_id = kwargs.get('port_id', '')
        if self.int_br.get_vif_port_by_id(port_id):
            LOG.debug(_('QoS %(qos_id)s updated on remote: %(port_id)s')
                      % kwargs)
            self.qos_agent.port_qos_deleted(context, qos_id, port_id)

    def port_qos_updated(self, context, **kwargs):
        qos_id = kwargs.get('qos_id', '')
        port_id = kwargs.get('port_id', '')
        if self.int_br.get_vif_port_by_id(port_id):
            LOG.debug(_('QoS %(qos_id)s updated on remote: %(port_id)s')
                      % kwargs)
            self.qos_agent.port_qos_updated(context, qos_id, port_id)
