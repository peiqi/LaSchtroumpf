# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2014 OpenStack Foundation
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

import math

from neutron.agent.linux import ip_lib
from neutron.common import constants
from neutron.services.qos.drivers import qos_base
from oslo_log import log as logging


LOG = logging.getLogger(__name__)


class FloatingIpLinuxTcQoSDriver(qos_base.QoSDriver):

    MIN_CLASS_ID = 1
    MAX_CLASS_ID = 0xFFF
    MAX_INBOUND_POLICY_CLASS_ID = int(math.ceil(
                                    float(MAX_CLASS_ID - MIN_CLASS_ID) / 2))
    RATE_LIMIT_MULTIPLIER = 1000  # 'k'
    DEFAULT_BURST = 16000
    PRIO = 1
    LOOP_INTERVAL = 10  # seconds

    def __init__(self, root_helper):
        LOG.info(_("Starting Linux TC QoS driver for Floating IP ports"))
        self.root_helper = root_helper
        self.router_gateway_class_id_map = {}
        self.router_gateway_available_class_id = {}
        self.existing_floating_ports = {}

    def has_router_gateway(self, gw_port_id):
        '''Has router gateway in local database.

        :param gw_port_id: gw port id
        :returns True: has router gateway, False: no router gateway
        '''
        return gw_port_id in self.router_gateway_class_id_map

    def _compare_port_details(self, port_details_1, port_details_2):
        '''Compare port details.

        :param port_details_1: port details 1 to be compared
        :param port_details_2: port details 2 to be compared
        :returns True: match, False: not match
        '''
        keys_to_compare = set(['router_id',
                               'gw_port_id',
                               'ns_name',
                               'floating_port_id',
                               'floating_ip_address',
                               'inbound_rate',
                               'outbound_rate',
                               ])
        for key in keys_to_compare:
            if port_details_1.get(key, None) != port_details_2.get(key, None):
                return False
        return True

    def cb_update_floating_port(self, updated_floating_ports):
        '''Update floating port details by l3_agent.

        :param updated_floating_ports: updated floating ports details
        '''
        LOG.info(_("Update floating ip port from L3 agent"))
        LOG.debug(updated_floating_ports)

        updated_floating_ports_set = set(updated_floating_ports.keys())
        existing_floating_ports_set = set(self.existing_floating_ports.keys())

        new_floating_ports = updated_floating_ports_set - \
            existing_floating_ports_set
        stale_floating_ports = existing_floating_ports_set - \
            updated_floating_ports_set
        changed_floating_ports = existing_floating_ports_set & \
            updated_floating_ports_set

        # process stale floating ports
        for _floating_ip_port in stale_floating_ports:
            port_details = self.existing_floating_ports[_floating_ip_port]
            floating_port_id = _floating_ip_port[1]
            self.delete_qos_for_port(floating_port_id, context=port_details)

        # process new floating ports
        for _floating_ip_port in new_floating_ports:
            port_details = updated_floating_ports[_floating_ip_port]
            floating_port_id = _floating_ip_port[1]

            inbound_rate = port_details.get('inbound_rate', None)
            # outbound_rate = port_details.get('outbound_rate', None)
            # TODO(qos): need to support outbound rate
            policy = {constants.TYPE_QOS_RATELIMIT: inbound_rate}
            self.port_qos_updated(policy, floating_port_id,
                                  context=port_details)

        # process floating ports that port configurations may changed
        for _floating_ip_port in changed_floating_ports:
            existing_port_details = \
                self.existing_floating_ports[_floating_ip_port]
            updated_port_details = updated_floating_ports[_floating_ip_port]
            if not self._compare_port_details(existing_port_details,
                                              updated_port_details):
                floating_port_id = _floating_ip_port[1]
                self.port_qos_updated(policy, floating_port_id,
                                      context=updated_port_details)

    def update_floating_ip(self, ns_name, floating_port_id, ctx):
        '''Update floating ip in local database.

        :param ns_name: net namespace name
        :param floating_port_id: floating ip port id
        :param ctx: context
        '''
        self.existing_floating_ports[(ns_name, floating_port_id)] = ctx

    def delete_floating_ip(self, ns_name, floating_port_id):
        '''Delete floating ip in local database.

        :param ns_name: net namespace name
        :param floating_port_id: floating port id
        '''
        self.existing_floating_ports.pop((ns_name, floating_port_id), None)

    def provision_class_id(self, gw_port_id, floating_ip):
        '''Provision class id for tc.

        :param gw_port_id: gw port id
        :param floating_ip: floating ip address
        '''
        LOG.info(_("Provision class id for gw_port_id: %(gw_port_id)s, "
                   "floating_ip: %(floating_ip)s"),
                 {'gw_port_id': gw_port_id, 'floating_ip': floating_ip})

        class_id = None
        if gw_port_id in self.router_gateway_class_id_map:
            # check if class id is already allocated for floating ip
            floating_ip_class_id_map = \
                self.router_gateway_class_id_map[gw_port_id]
            if floating_ip in floating_ip_class_id_map:
                # found class id for floating ip
                return floating_ip_class_id_map[floating_ip]

            # allocate new class id for floating ip
            available_class_id = self.router_gateway_available_class_id.get(
                                    gw_port_id, {})
            if not available_class_id:
                LOG.error(_("No local Class ID available for gw_port_id=%s"),
                          gw_port_id)
                return None
            class_id = available_class_id.pop()
            floating_ip_class_id_map[floating_ip] = class_id
        else:
            # allocate new gw_port_id
            available_class_id = set(xrange(
                FloatingIpLinuxTcQoSDriver.MIN_CLASS_ID,
                FloatingIpLinuxTcQoSDriver.MAX_INBOUND_POLICY_CLASS_ID))
            if not available_class_id:
                LOG.error(_("No local Class ID available for gw_port_id=%s"),
                          gw_port_id)
                return None
            class_id = available_class_id.pop()
            floating_ip_class_id_map = {floating_ip: class_id}
            self.router_gateway_class_id_map[gw_port_id] = \
                floating_ip_class_id_map
            self.router_gateway_available_class_id[gw_port_id] = \
                available_class_id
        LOG.info(_("Provisioned class id: %(class_id)u for "
                   "gw_port_id: %(gw_port_id)s, %(floating_ip)s"),
                 {'class_id': class_id,
                  'gw_port_id': gw_port_id,
                  'floating_ip': floating_ip})
        return class_id

    def reclaim_class_id(self, gw_port_id, floating_ip):
        '''Reclaim class id for tc.

        :param gw_port_id: gw port id
        :param floating_ip: floating ip address
        '''
        LOG.info(_("Reclaim class id for gw_port_id: %(gw_port_id)s, "
                   "floating_ip: %(floating_ip)s"),
                 {'gw_port_id': gw_port_id, 'floating_ip': floating_ip})

        if ((gw_port_id not in self.router_gateway_class_id_map) or
                (gw_port_id not in self.router_gateway_available_class_id)):
            return
        class_id = self.router_gateway_class_id_map[gw_port_id].pop(
            floating_ip, None)
        if class_id is not None:
            self.router_gateway_available_class_id[gw_port_id].add(class_id)
        if not self.router_gateway_class_id_map[gw_port_id]:
            del self.router_gateway_class_id_map[gw_port_id]
            del self.router_gateway_available_class_id[gw_port_id]
        LOG.info(_("Reclaimed class id: %(class_id)u for "
                   "gw_port_id: %(gw_port_id)s, %(floating_ip)s"),
                 {'class_id': class_id,
                  'gw_port_id': gw_port_id,
                  'floating_ip': floating_ip})

    def get_class_id(self, gw_port_id, floating_ip):
        '''Get class id for tc.

        :param gw_port_id: gw class id
        :param floating_ip: floating ip address
        :returns class id
        '''
        if ((gw_port_id not in self.router_gateway_class_id_map) or
                (gw_port_id not in self.router_gateway_available_class_id)):
            return None
        return self.router_gateway_class_id_map[gw_port_id].get(floating_ip,
                                                                None)

    def print_class_id_mapping(self, gw_port_id=None, floating_ip=None):
        '''Print class id mappings for debug purpose.

        :param gw_port_id: gw port id
        :param floating_ip: floating ip address
        '''
        if gw_port_id is None:
            LOG.debug(_("Print mappings for router gateway and class id:"))
            LOG.debug(self.router_gateway_class_id_map)
        else:
            if floating_ip is None:
                LOG.debug(_("\nPrint mappings of floating ip and class id for \
                    gw_port_id: %u"), gw_port_id)
                # LOG.debug(_("%s", self.router_gateway_class_id_map.get(
                #     gw_port_id, None)))
            else:
                LOG.debug(_("\nPrint mappings of floating ip: %(floating_ip)s "
                            "and class id for gw_port_id: %(gw_port_id)u"),
                          {"floating_ip": floating_ip,
                           "gw_port_id": gw_port_id})
                floating_ip_class_id_map = \
                    self.router_gateway_class_id_map.get(gw_port_id, None)
                if floating_ip_class_id_map is None:
                    LOG.debug(_("No floating ip is found"))
                else:
                    LOG.debug(_("Class id: %u"),
                              floating_ip_class_id_map[floating_ip])

    def print_available_class_id(self, gw_port_id=None):
        '''Print available class id for debug purpose.

        :param gw_port_id: gw port id
        '''
        if gw_port_id is None:
            LOG.debug(_("Print available class id for gw_port_id:"))
            LOG.debug(self.router_gateway_available_class_id)
        else:
            LOG.debug(_("Print available class id for gw_port_id: %s"),
                      gw_port_id)
            LOG.debug(self.router_gateway_available_class_id.get(gw_port_id,
                                                                 None))

    def delete_qdisc_for_router_gateway(self, gw_port_id, ns_name=None):
        '''Delete qdisc for router gateway.

        :param gw_port_id: gw port id
        :param ns_name: net namespace name
        '''
        LOG.debug(_("Delete qdisc for gw_port_id: %(gw_port_id)s, "
                    "ns_name: %(ns_name)s"),
                  {'gw_port_id': gw_port_id, 'ns_name': ns_name})
        ns_wrapper = ip_lib.IPWrapper(namespace=ns_name)
        # delete all class ids for gw_port_id
        try:
            ns_wrapper.netns.execute(['tc', 'qdisc', 'delete',
                                      'dev', gw_port_id, 'root'],
                                     check_exit_code=False)
        except Exception:
            # LOG.warn('Failed to apply tc root on gw_port_id: %s\n%s' %
            #    (gw_port_id, e))
            pass

        try:
            ns_wrapper.netns.execute(['tc', 'qdisc', 'delete',
                                      'dev', gw_port_id,
                                      'parent', 'ffff:'],
                                     check_exit_code=False)
        except Exception:
            # LOG.warn('Failed to apply tc ingress on gw_port_id: %s\n%s' %
            # (gw_port_id, e))
            pass

    def update_qdisc_for_router_gateway(self, gw_port_id, ns_name=None):
        '''Update tc qdisc for route gateway 'qg-' port.

        :param gw_port_id: gw port id
        :param ns_name: net namespace name
        '''
        ns_wrapper = ip_lib.IPWrapper(namespace=ns_name)
        try:
            ns_wrapper.netns.execute(['tc', 'qdisc', 'delete',
                                      'dev', gw_port_id, 'root',
                                      'handle', '1:', 'htb', 'r2q', '1'],
                                     check_exit_code=False)
        except Exception:
            # LOG.warn(_("Failed to apply tc on gw_port_id: %s\n%s") %
            # (gw_port_id, e))
            # return False
            pass
        try:
            ns_wrapper.netns.execute(['tc', 'qdisc', 'add',
                                      'dev', gw_port_id, 'root',
                                      'handle', '1:', 'htb', 'r2q', '1'],
                                     check_exit_code=False)
        except Exception:
            # LOG.warn(_("Failed to apply tc on gw_port_id: %s\n%s") %
            # (gw_port_id, e))
            # return False
            pass
        try:
            ns_wrapper.netns.execute(['tc', 'qdisc', 'add',
                                      'dev', gw_port_id,
                                      'handle', 'ffff:', 'ingress'],
                                     check_exit_code=False)
        except Exception:
            # LOG.warn(_("Failed to apply tc on gw_port_id: %s\n%s") %
            # (gw_port_id, e))
            # return False
            pass
        return True

    def _update_policy_for_router_gateway(self,
                                          gw_port_id,
                                          floating_ip,
                                          class_id,
                                          inbound_policy=None,
                                          outbound_policy=None,
                                          ns_name=None):
        '''Update policy for router gateway.

        :param gw_port_id: gw port id
        :param floating_ip: floating ip address
        :param class_id: class id for tc
        :param inbound_policy: inbound policy
        :param outbound_policy: outbound policy
        :param ns_name: net namespace name
        '''
        ns_wrapper = ip_lib.IPWrapper(namespace=ns_name)

        # 1. apply inbound ratelimit
        if inbound_policy:
            inbound_ratelimit = '%u' % (inbound_policy['ratelimit'] *
                FloatingIpLinuxTcQoSDriver.RATE_LIMIT_MULTIPLIER)
            inbound_burst = '%u' % (inbound_policy['burst'])
            inbound_class_id = FloatingIpLinuxTcQoSDriver.MIN_CLASS_ID - 1 + \
                class_id
            try:
                ns_wrapper.netns.execute(['tc', 'filter', 'delete',
                                          'dev', gw_port_id, 'parent', 'ffff:',
                                          'protocol', 'ip',
                                          'prio',
                                          FloatingIpLinuxTcQoSDriver.PRIO,
                                          'handle', '800::%x' %
                                          inbound_class_id,
                                          'u32'],
                                         check_exit_code=False)
                ns_wrapper.netns.execute(['tc', 'filter', 'replace',
                                          'dev', gw_port_id, 'parent', 'ffff:',
                                          'protocol', 'ip',
                                          'prio',
                                          FloatingIpLinuxTcQoSDriver.PRIO,
                                          'handle', '800::%x' %
                                          inbound_class_id,
                                          'u32', 'match',
                                          'ip', 'dst', floating_ip,
                                          'police', 'rate', inbound_ratelimit,
                                          'burst', inbound_burst, 'drop',
                                          'flowid', inbound_class_id],
                                         check_exit_code=False)
            except Exception as e:
                LOG.warn(_("Failed to apply tc on gw_port_id: %(gw_port_id)s, "
                           "floating_ip: %(floating_ip)s, "
                           "inbound_ratelimit: %(inbound_ratelimit)s, "
                           "inbound_burst: %(inbound_burst)s"
                           "\n%(e)s") %
                         ({"gw_port_id": gw_port_id,
                           "floating_ip": floating_ip,
                           "inbound_ratelimit": inbound_ratelimit,
                           "inbound_burst": inbound_burst,
                           "e": e}))
                return False

        # 2. apply outbound ratelimit
        if outbound_policy:
            outbound_ratelimit = '%u' % (outbound_policy['ratelimit'] *
                FloatingIpLinuxTcQoSDriver.RATE_LIMIT_MULTIPLIER)
            outbound_burst = '%u' % (outbound_policy['burst'])
            outbound_class_id = \
                FloatingIpLinuxTcQoSDriver.MAX_INBOUND_POLICY_CLASS_ID + \
                class_id
            try:
                ns_wrapper.netns.execute(['tc', 'class', 'replace',
                                          'dev', gw_port_id, 'parent', '1:',
                                          'classid',
                                          '1:%x' % outbound_class_id,
                                          'htb',
                                          'rate', outbound_ratelimit,
                                          'burst', outbound_burst],
                                         check_exit_code=True)
                ns_wrapper.netns.execute(['tc', 'filter', 'delete',
                                          'dev', gw_port_id, 'parent', '1:',
                                          'protocol', 'ip',
                                          'prio',
                                          FloatingIpLinuxTcQoSDriver.PRIO,
                                          'handle', '800::%x' %
                                          outbound_class_id,
                                          'u32', 'match',
                                          'ip', 'src', floating_ip,
                                          'classid', '1:%x' %
                                          outbound_class_id],
                                         # force to delete filter
                                         check_exit_code=False)
                ns_wrapper.netns.execute(['tc', 'filter', 'replace',
                                          'dev', gw_port_id, 'parent', '1:',
                                          'protocol', 'ip',
                                          'prio',
                                          FloatingIpLinuxTcQoSDriver.PRIO,
                                          'handle', '800::%x' %
                                          outbound_class_id,
                                          'u32', 'match',
                                          'ip', 'src', floating_ip,
                                          'classid', '1:%x' %
                                          outbound_class_id],
                                         check_exit_code=False)
            except Exception as e:
                LOG.warn(_("Failed to apply tc on gw_port_id: %(gw_port_id)s, "
                           "floating_ip: %(floating_ip)s, "
                           "class_id: %(outbound_class_id)u, "
                           "outbound_ratelimit: %(outbound_ratelimit)s, "
                           "outbound_burst: %(outbound_burst)s"
                           "\n%(e)s") %
                         ({"gw_port_id": gw_port_id,
                          "floating_ip": floating_ip,
                          "outbound_class_id": outbound_class_id,
                          "outbound_ratelimit": outbound_ratelimit,
                          "outbound_burst": outbound_burst,
                          "e": e}))
                return False
        return True

    def delete_policy_for_router_gateway(self, gw_port_id, floating_ip,
                                         class_id, ns_name=None):
        '''Delete policy for router gateway.

        :param gw_port_id: gw port id
        :param floating_ip: floating ip address
        :param class_id: class id for tc
        :param ns_name: net ns_name name
        '''
        ns_wrapper = ip_lib.IPWrapper(namespace=ns_name)
        # 1. if gw_port_id is None, delete qdisc and all related classes
        # and filters
        if not gw_port_id:
            # delete all class ids for gw_port_id
            self.delete_qdisc_for_router_gateway(gw_port_id, ns_name)

        # 2. delete specific class id for gw_port_id
        # 2.1 delete inbound ratelimit
        inbound_class_id = FloatingIpLinuxTcQoSDriver.MIN_CLASS_ID - 1 + \
            class_id
        try:
            ns_wrapper.netns.execute(['tc', 'filter', 'delete',
                                      'dev', gw_port_id, 'parent', 'ffff:',
                                      'protocol', 'ip',
                                      'prio', FloatingIpLinuxTcQoSDriver.PRIO,
                                      'handle', '800::%x' % inbound_class_id,
                                      'u32'],
                                     check_exit_code=False)
        except Exception as e:
            LOG.warn(_("Failed to delete tc on gw_port_id: %(gw_port_id)s, "
                       "floating_ip: %(floating_ip)s, "
                       "class_id: %(inbound_class_id)s"
                       "\n%(e)s") %
                     ({"gw_port_id": gw_port_id,
                      "floating_ip": floating_ip,
                      "inbound_class_id": inbound_class_id,
                      "e": e}))
            return False

        # 2.2 delete outbound ratelimit
        outbound_class_id = \
            FloatingIpLinuxTcQoSDriver.MAX_INBOUND_POLICY_CLASS_ID + \
            class_id
        try:
            ns_wrapper.netns.execute(['tc', 'filter', 'delete',
                                      'dev', gw_port_id, 'parent', '1:',
                                      'protocol', 'ip',
                                      'prio', FloatingIpLinuxTcQoSDriver.PRIO,
                                      'handle', '800::%x' % outbound_class_id,
                                      'u32', 'match',
                                      'ip', 'src', floating_ip,
                                      'classid', '1:%x' % outbound_class_id],
                                     check_exit_code=False)
            ns_wrapper.netns.execute(['tc', 'class', 'delete',
                                      'dev', gw_port_id, 'parent', '1:',
                                      'classid', '1:%x' % outbound_class_id],
                                     check_exit_code=False)
        except Exception as e:
            LOG.warn(_("Failed to delete tc on gw_port_id: %(gw_port_id)s, "
                       "floating_ip: %(floating_ip)s, "
                       "class_id: %(outbound_class_id)s"
                       "\n%(e)s") %
                     ({"gw_port_id": gw_port_id,
                      "floating_ip": floating_ip,
                      "outbound_class_id": outbound_class_id,
                      "e": e}))
            return False

        # 3. delete qdisc and all related classes and filters if router_gateway
        # is not existed in router_gateway_class_id_map
        if not self.has_router_gateway(gw_port_id):
            # delete all class ids for gw_port_id
            self.delete_qdisc_for_router_gateway(gw_port_id, ns_name)
        return True

    def delete_qos_for_network(self, network_id):
        '''Delete qos for network.

        :param network_id: network id
        '''
        # not support network QoS
        pass

    def network_qos_updated(self, policy, network_id):
        '''Update qos for network.

        :param policy: qos policy
        :param network_id: network id
        '''
        # not support network QoS
        pass

    def validate_context_details(self, policy, context):
        '''Validate qos policy and port details context.

        :param policy: qos policy
        :param context: port details context
        :returns: validated context or None for illegal context
        '''
        floating_port_id = context.get('floating_port_id', None)
        if floating_port_id is None:
            LOG.warn(_("floating_port_id should be specified"))
            return None

        gw_port_id = context.get('gw_port_id', None)
        if gw_port_id is None:
            LOG.warn(_("gw_port_id should be specified"))
            return None

        floating_ip = context.get('floating_ip_address', None)
        if floating_ip is None:
            LOG.warn(_("floating_ip should be specified for gw_port_id: "
                       "%(gw_port_id)s"),
                     {'gw_port_id': gw_port_id})
            return None

        ns_name = context.get('ns_name', None)
        if ns_name is None:
            LOG.warn(_("namespace should be specified for gw_port_id: "
                       "%(gw_port_id)s"),
                     {'gw_port_id': gw_port_id})
            return None

        router_id = context.get('router_id', None)
        if router_id is None:
            LOG.warn(_("router_id should be specified for gw_port_id: "
                       "%(gw_port_id)s"),
                     {'gw_port_id': gw_port_id})
            return None

        ctx = {}
        ctx['gw_port_id'] = gw_port_id
        ctx['floating_ip_address'] = floating_ip
        ctx['ns_name'] = ns_name
        ctx['router_id'] = router_id
        ctx['floating_port_id'] = floating_port_id

        if policy is not None:
            rate = policy.get(constants.TYPE_QOS_RATELIMIT, None)
            if rate is not None:
                rate = int(rate)
            latency = policy.get(constants.TYPE_QOS_POLICY_TC_LATENCY, None)
            if latency is not None:
                latency = int(latency)
            burst = policy.get(constants.TYPE_QOS_POLICY_TC_BURST, None)
            if burst is not None:
                burst = int(burst)
            else:
                burst = FloatingIpLinuxTcQoSDriver.DEFAULT_BURST
            ctx['inbound_rate'] = rate
            ctx['inbound_latency'] = latency
            ctx['inbound_burst'] = burst
            # TODO(qos): need to be replaced by outbound rate
            ctx['outbound_rate'] = rate
            # TODO(qos): need to be replaced by outbound latency
            ctx['outbound_latency'] = latency
            # TODO(qos): need to be replaced by outbound burst
            ctx['outbound_burst'] = burst
        return ctx

    def delete_qos_for_port(self, port_id, **kwargs):
        '''Delete qos for port.

        :param port_id: port id
        '''
        LOG.debug(_('delete_qos_for_port: port_id: %(port_id)s, '
                    '**kwargs: %(kwargs)s'),
                  {'port_id': port_id, 'kwargs': kwargs})

        # 1. get port context
        context = kwargs.get('context', None)
        if not context:
            return False

        ctx = self.validate_context_details(None, context)
        if ctx is None:
            return False
        gw_port_id = ctx['gw_port_id']
        floating_ip = ctx['floating_ip_address']
        ns_name = ctx['ns_name']
        floating_port_id = ctx['floating_port_id']

        # 2. get tc class id for floating ip
        class_id = self.get_class_id(gw_port_id, floating_ip)
        if not class_id:
            LOG.warn(_("Failed to get tc class id for gw_port_id: "
                       "%(gw_port_id)s, "
                       "floating_ip: %(floating_ip)s"),
                     {'gw_port_id': gw_port_id, 'floating_ip': floating_ip})
            return False

        # 3. reclaim class id
        self.reclaim_class_id(gw_port_id, floating_ip)

        # 4. delete tc class id for floating ip
        ret = self.delete_policy_for_router_gateway(gw_port_id, floating_ip,
                                                    class_id, ns_name)
        self.delete_floating_ip(ns_name, floating_port_id)
        return ret

    def port_qos_updated(self, policy, port_id, **kwargs):
        '''Update qos for port.

        :param policy: qos policy
        :param port_id: port id
        '''
        LOG.debug(_('port_qos_updated: %(port_id)s, policy: %(policy)s, '
                    '**kwargs: %(kwargs)s'),
                  {'port_id': port_id, 'policy': policy, 'kwargs': kwargs})

        # 1. retrieve and validate input data
        context = kwargs.get('context', None)
        if not context:
            return False

        ctx = self.validate_context_details(policy, context)
        if ctx is None:
            return False
        gw_port_id = ctx['gw_port_id']
        floating_ip = ctx['floating_ip_address']
        ns_name = ctx['ns_name']
        floating_port_id = ctx['floating_port_id']

        inbound_policy = {'ratelimit': ctx['inbound_rate'],
                          'burst': ctx['inbound_burst'],
                          'latency': ctx['inbound_latency']}
        outbound_policy = {'ratelimit': ctx['outbound_rate'],
                           'burst': ctx['outbound_burst'],
                           'latency': ctx['outbound_latency']}

        # 2. update tc qdisc for router_gateway
        if not self.has_router_gateway(gw_port_id):
            if not self.update_qdisc_for_router_gateway(gw_port_id, ns_name):
                return False

        # 3. provision class id for floating ip
        class_id = self.provision_class_id(gw_port_id, floating_ip)
        if not class_id:
            LOG.warn(_("Failed to provision tc class id for gw_port_id: "
                       "%(gw_port_id)s, "
                       "floating_ip: %(floating_ip)s"),
                     {'gw_port_id': gw_port_id, 'floating_ip': floating_ip})
            return False

        # 4. update tc class for floating_ip
        if not self._update_policy_for_router_gateway(gw_port_id, floating_ip,
                                                      class_id,
                                                      inbound_policy,
                                                      outbound_policy,
                                                      ns_name=ns_name):
            return False

        # 5. update local database
        self.update_floating_ip(ns_name, floating_port_id, ctx)
        return True
