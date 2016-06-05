# Copyright 2012 VMware, Inc.  All rights reserved.
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

import eventlet
import sys

from oslo_concurrency import lockutils
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging
from oslo_messaging._drivers import common as rpc_common
from oslo_utils import timeutils

from neutron.agent.common import config
from neutron.agent import rpc as agent_rpc
from neutron.common import constants as ha_constants
from neutron.common import config as common_config
from neutron.common import exceptions
from neutron.common import rpc as n_rpc
from neutron.common import topics
from neutron.openstack.common import loopingcall
from neutron.openstack.common import service
from neutron import context
from neutron.plugins.common import constants as plugin_constants
from neutron import manager
from neutron import service as neutron_service


LOG = logging.getLogger(__name__)
agent_resource = {
    ha_constants.AGENT_TYPE_DHCP: "networks",
    ha_constants.AGENT_TYPE_L3: "routers",
    ha_constants.AGENT_TYPE_LOADBALANCER: "instances",
    ha_constants.AGENT_TYPE_OVS: "devices",
    ha_constants.AGENT_TYPE_METADATA: None,
    ha_constants.AGENT_TYPE_LINUXBRIDGE: "devices",
}
L2_Agent_Types = [
    ha_constants.AGENT_TYPE_OVS,
    ha_constants.AGENT_TYPE_LINUXBRIDGE]


class InvalidAgentOperation(exceptions.Invalid):
    message = "Invalid Operation %(operation)s for Agent Type %(agent_type)s"


class InvalidRescheduleMethod(exceptions.Invalid):
    message = "Invalid Method %(method)s to schedule resources to other agents"


class ExceptionRescheduleAgents(exceptions.NeutronException):
    message = "Exception during migrate from %(agent_from)s to %(agent_to)s"


class HAPluginApi(object):
    """Agent side of the ha-agent RPC API.

    API version history:
        1.0 - Initial version.
        1.1 - Floating IP operational status updates

    """

    BASE_RPC_API_VERSION = '1.0'

    def __init__(self, topic):
        target = oslo_messaging.Target(
            topic=topic, version=self.BASE_RPC_API_VERSION)
        self.client = n_rpc.get_client(target)

    def get_agents(self, context):
        """Make a remote process call to get agents information."""

        cctxt = self.client.prepare()
        return cctxt.call(context, 'get_agents')

    def get_agent_resources(self, context, agent):
        agent_id = agent.id
        agent_type = agent.agent_type
        cctxt = self.client.prepare()
        return cctxt.call(
            context,
            'get_agent_resources',
            agent_type=agent_type,
            agent_id=agent_id)

    def get_resource_agents(self, context, resource):
        resource_id = resource.id
        resource_type = resource.type
        cctxt = self.client.prepare()
        return cctxt.call(
            context,
            'get_resource_agents',
            resource_type=resource_type,
            resource_id=resource_id)

    def migrate_agent_resource(
            self, context, agent_type, agent_from, agent_to, resource_id):
        cctxt = self.client.prepare()
        return cctxt.call(
            context,
            'migrate_agent_resource',
            agent_type=agent_type,
            agent_from=agent_from,
            agent_to=agent_to,
            resource_id=resource_id)


class HARpcCallbackMixin(object):

    def get_agents(self, context, **kwargs):
        plugin = manager.NeutronManager.get_plugin()
        return plugin.get_agents(context)

    def get_agent_resources(self, context, **kwargs):
        agent_id = kwargs['agent_id']
        agent_type = kwargs['agent_type']
        if(agent_type == ha_constants.AGENT_TYPE_DHCP):
            plugin = manager.NeutronManager.get_plugin()
            return plugin.list_networks_on_dhcp_agent(context, agent_id)
        elif(agent_type == ha_constants.AGENT_TYPE_L3):
            plugin = manager.NeutronManager.get_service_plugins()[
                plugin_constants.L3_ROUTER_NAT]
            return plugin.list_routers_on_l3_agent(context, agent_id)
        elif(agent_type == ha_constants.AGENT_TYPE_LOADBALANCER):
            plugin = manager.NeutronManager.get_service_plugins()[
                plugin_constants.LOADBALANCER]
            return plugin.list_pools_on_lbaas_agent(context, agent_id)

        return None

    def get_resource_agents(self, context, **kwargs):
        resource_type = kwargs['resource_type']
        resource_id = kwargs['resource_id']
        if(resource_type == 'networks'):
            plugin = manager.NeutronManager.get_plugin()
            return plugin.list_dhcp_agents_hosting_network(
                context, resource_id)
        elif(resource_type == 'routers'):
            plugin = manager.NeutronManager.get_service_plugins()[
                plugin_constants.L3_ROUTER_NAT]
            return plugin.list_l3_agents_hosting_router(context, resource_id)
        elif(resource_type == 'pools'):
            plugin = manager.NeutronManager.get_service_plugins()[
                plugin_constants.LOADBALANCER]
            return plugin.get_lbaas_agent_hosting_pool(context, resource_id)

    def migrate_agent_resource(self, context, **kwargs):
        agent_type = kwargs['agent_type']
        agent_from = kwargs['agent_from']
        agent_to = kwargs['agent_to']
        if 'resource_id' in kwargs.keys():
            resource_id = kwargs['resource_id']
        else:
            resource_id = None

        with context.session.begin(subtransactions=True):
            try:
                if(agent_type == ha_constants.AGENT_TYPE_DHCP):
                    plugin = manager.NeutronManager.get_plugin()
                    if(resource_id is not None):
                        plugin.remove_network_from_dhcp_agent(
                            context, agent_from, resource_id)
                        plugin.add_network_to_dhcp_agent(
                            context, agent_to, resource_id)
                    else:
                        resources = plugin.list_networks_on_dhcp_agent(
                            context, agent_from)['networks']
                        for resource in resources:
                            plugin.remove_network_from_dhcp_agent(
                                context, agent_from, resource['id'])
                            plugin.add_network_to_dhcp_agent(
                                context, agent_to, resource['id'])
                elif(agent_type == ha_constants.AGENT_TYPE_L3):
                    plugin = manager.NeutronManager.get_service_plugins()[
                        plugin_constants.L3_ROUTER_NAT]
                    if(resource_id is not None):
                        plugin.remove_router_from_l3_agent(
                            context, agent_from, resource_id)
                        plugin.add_router_to_l3_agent(
                            context, agent_to, resource_id)
                    else:
                        resources = plugin.list_routers_on_l3_agent(
                            context, agent_from)['routers']
                        for resource in resources:
                            plugin.remove_router_from_l3_agent(
                                context, agent_from, resource['id'])
                            plugin.add_router_to_l3_agent(
                                context, agent_to, resource['id'])
                elif(agent_type == ha_constants.AGENT_TYPE_LOADBALANCER):
                    plugin = manager.NeutronManager.get_service_plugins()[
                        plugin_constants.LOADBALANCER]
                    if(resource_id is not None):
                        plugin.remove_pool_from_lb_agent(
                            context, agent_from, resource_id)
                        plugin.add_pool_to_lb_agent(
                            context, agent_to, resource_id)
                    else:
                        resources = plugin.list_pools_on_lbaas_agent(
                            context, agent_from)['pools']
                        for resource in resources:
                            plugin.remove_pool_from_lb_agent(
                                context, agent_from, resource['id'])
                            plugin.add_pool_to_lb_agent(
                                context, agent_to, resource['id'])
            except Exception:
                LOG.exception(
                    _("Exception occurred during"
                      "migrate resources from %s to %s"),
                    agent_from,
                    agent_to)


class AgentInfo(object):

    def __init__(self, agent):
        self.id = agent['id']
        self.agent_type = agent['agent_type']
        self.agent_state = agent['alive']
        self.agent_host = agent['host']
        self.last_update = agent['heartbeat_timestamp']
        self.resource = {}
        if(agent_resource[self.agent_type] is not None):
            self.resource['name'] = agent_resource[self.agent_type]
            self.resource['count'] = agent[
                'configurations'][self.resource['name']]
        else:
            self.resource['name'] = None
            self.resource['count'] = 0

    @property
    def agent(self):
        return self._agent

    @agent.setter
    def agent(self, value):
        self._agent = value


class ResourceInfo(object):

    def __init__(self, resource_type, resource):
        self.id = resource['id']
        self.type = resource_type

    @property
    def resource(self):
        return self._resource

    @resource.setter
    def resource(self, value):
        self._resource = value


class HAAgent(manager.Manager):
    """Manager for HAAgent
    """
    RPC_API_VERSION = '1.1'

    OPTS = [
        cfg.StrOpt(
            'ha_reschedule_method',
            default='least_resources',
            help=_(
                "Methods to reschedule resources to other agents,"
                "least_resources, or latest_updated are supported."
                "eg, ha_reschedule_method=least_resources"
                "eg, ha_reschedule_method=latest_updated")),
        cfg.IntOpt(
            'ha_check_interval',
            default=20,
            help=_("Check Agents alive status interval, unit is second")),
        cfg.StrOpt(
            'ha_monitor_supported_resource',
            default='Loadbalancer agent',
            help=_(
                "Agent types supported to check agent alive status, "
                "and migrate resources once agent is down."
                "Comma is used as splitor, and no white space before "
                "or after the splitor"
                "ha_monitor_supported_resource=DHCP agent"
                ",L3 agent,Loadbalancer agent")),
    ]
    DEFAULTOPTS = [
        cfg.IntOpt(
            'dhcp_agents_per_network',
            default=1,
            help=_('Number of DHCP agents scheduled to host a network.')),
        cfg.IntOpt(
            'l3_agents_per_router',
            default=1,
            help=_('Number of L3 agents scheduled to host a router.')),
        cfg.IntOpt(
            'agent_down_time',
            default=75,
            help=_(
                "Seconds to regard the agent is down; should be at "
                "least twice report_interval, to be sure the "
                "agent is down for good.")),
    ]
    AGENTREPORTTIME = [

        cfg.FloatOpt('report_interval', default=30,
                     help=_('Seconds between nodes reporting state to server; '
                            'should be less than agent_down_time, best if it '
                            'is half or less than agent_down_time.')),
    ]

    def __init__(self, host, conf=None):
        if conf:
            self.conf = conf
        else:
            self.conf = cfg.CONF

        self.host = host
        self.context = context.get_admin_context()
        self.plugin_rpc = HAPluginApi(topics.PLUGIN)
        self.fullsync = True
        self.agent_infos = set()
        self.active_agents = set()
        self.downed_agents = set()
        self.resource_agent_count = {
            'networks': self.conf.dhcp_agents_per_network,
            'routers': 1,
            'pools': 1
        }
        self.rpc_loop_interval = self.conf.HAAgent.ha_check_interval
        self.support_agents_types = self.conf.\
            HAAgent.ha_monitor_supported_resource.split(',')
        self.schedule_method = self.conf.HAAgent.ha_reschedule_method
        self.sync_progress = False

        self.rpc_loop = loopingcall.FixedIntervalLoopingCall(
            self._rpc_loop)
        self.rpc_loop.start(interval=self.rpc_loop_interval)
        super(HAAgent, self).__init__(host=host)

    def _add_down_agents(self, agent):
        self.downed_agents.add(agent)

    def _add_active_agents(self, agent):
        self.active_agents.add(agent)

    def _get_best_agent_resource_count(self, available_agents):
        min_count = 9999
        ret_agent = None
        for agent in available_agents:
            if agent.resource['count'] < min_count:
                min_count = agent.resource['count']
                ret_agent = agent
        return ret_agent

    def _get_best_agent_last_update_time(self, available_agents, fmt=None):
        atnow = timeutils.utcnow()
        latest = self.conf.Agent.report_interval
        ret_agent = None
        for agent in available_agents:
            agent_time = timeutils.parse_strtime(
                agent.last_update, fmt).replace(
                tzinfo=None)
            deltaSeconds = (atnow - agent_time).total_seconds()
            if deltaSeconds < latest:
                latest = deltaSeconds
                ret_agent = agent

        return ret_agent

    def _get_best_agent(self, available_agents,
                        schedule_method='least_resources'):
        if schedule_method == 'latest_updated':
            return self._get_best_agent_last_update_time(available_agents)
        elif schedule_method == 'least_resources':
            return self._get_best_agent_resource_count(available_agents)

        LOG.exception(
            "Not support the reschedule_method %s", schedule_method)
        raise InvalidRescheduleMethod(method=schedule_method)

    def _get_agent_resources(self, context, down_agent):

        if(down_agent.agent_type == ha_constants.AGENT_TYPE_LOADBALANCER):
            resource_type = 'pools'
        else:
            resource_type = down_agent.resource['name']

        resource_list = self.plugin_rpc.get_agent_resources(
            context, down_agent)
        resources = set()
        for resource in resource_list[resource_type]:
            resource_info = ResourceInfo(resource_type, resource)
            resources.add(resource_info)
        return resources

    def _get_resource_agents(self, context, resource):
        all_agents = self.plugin_rpc.get_resource_agents(context, resource)
        agents = set()
        if 'agent' in all_agents:
            agent_info = AgentInfo(all_agents['agent'])
            agents.add(agent_info)
        elif 'agents' in all_agents:
            for agent in all_agents['agents']:
                agent_info = AgentInfo(agent)
                agents.add(agent_info)
        return agents

    def _get_similar_agents(self, down_agent):
        similar_agents = set()
        for agent in self.active_agents:
            if agent.agent_type == down_agent.agent_type:
                similar_agents.add(agent)

        return similar_agents

    def _migrate_agent_resources(
            self, down_agent, schedule_method='least_resources'):
        resources = self._get_agent_resources(self.context, down_agent)
        if(resources is None):
            LOG.info("No Resources to migrate from Agent ", down_agent['id'])
            return

        for resource in resources:
            except_agents = self._get_resource_agents(self.context, resource)
            needed_migrate = len(except_agents) - \
                1 < self.resource_agent_count[resource.type]
            if(needed_migrate):
                LOG.info(
                    _("Begin to migrate resource %s with ID %s located on %s"),
                    resource.type,
                    resource.id,
                    down_agent.id)
                available_agents = self._get_similar_agents(
                    down_agent) - except_agents
                candidate_agent = self._get_best_agent(
                    available_agents, schedule_method)
                if candidate_agent is not None:
                    try:
                        self.plugin_rpc.migrate_agent_resource(
                            self.context,
                            down_agent.agent_type,
                            down_agent.id,
                            candidate_agent.id,
                            resource.id)
                        LOG.info(
                            _("Migrate resource %s with ID %s to %s"),
                            resource.type,
                            resource.id,
                            candidate_agent.id)
                    except Exception:
                        LOG.exception("Failed migrate %s",
                                      resource.id,
                                      " located on agent %s",
                                      down_agent.agent_type,
                                      " with agent ID: %s",
                                      down_agent.id)

    def _process_agents(self, schedule_method='resource_count'):
        pool = eventlet.GreenPool()
        for agent in self.agent_infos:
            if agent.agent_type in self.support_agents_types:
                if not agent.agent_state:
                    self._add_down_agents(agent)
                else:
                    self._add_active_agents(agent)

        for agent in self.downed_agents:
            LOG.debug(_("Processing dead agents: %s"), agent.id)
            self._migrate_agent_resources(
                agent, schedule_method=schedule_method)
        pool.waitall()

    def _update_agents_info(self, context):
        agents = self.plugin_rpc.get_agents(context)
        for agent in agents:
            if agent['agent_type'] in agent_resource.keys():
                agent_info = AgentInfo(agent)
                self.agent_infos.add(agent_info)

    @lockutils.synchronized('ha-agent', 'neutron-')
    def _rpc_loop(self):
        # _rpc_loop and _sync_agents_task will not be
        # executed in the same time because of lock.
        try:
            LOG.debug(_("Starting RPC loop for %d updated routers"),
                      len(self.downed_agents))

            self.active_agents.clear()
            self.downed_agents.clear()
            self.agent_infos.clear()
            self._update_agents_info(self.context)

            LOG.debug(_('Processing :%r'), self.agent_infos)
            self._process_agents(self.schedule_method)

            LOG.debug(
                _('After processing agents_info, agents count:%d'), len(
                    self.agent_infos))
            LOG.debug(_("RPC loop successfully completed"))

        except Exception:
            LOG.exception(_("Failed handling agents"))
            self.fullsync = True

    @lockutils.synchronized('ha-agent', 'neutron-')
    def sync_agents_task(self):
        LOG.debug(_("Initialize agent_infos Cache."))
        try:
            self.active_agents.clear()
            self.downed_agents.clear()
            self.agent_infos.clear()
            self._update_agents_info(self.context)

        except rpc_common.RPCException:
            LOG.exception(_("Failed synchronizing agents due to RPC error"))
            self.fullsync = True
            return
        except Exception:
            LOG.exception(_("Failed handling agents"))
            self.fullsync = True

    def after_start(self):
        LOG.info(_("HA agent started"))
        self.sync_agents_task()


class HAAgentWithStateReport(HAAgent):

    def __init__(self, host, conf=None):
        super(HAAgentWithStateReport, self).__init__(host=host, conf=conf)
        self.state_rpc = agent_rpc.PluginReportStateAPI(topics.PLUGIN)
        self.agent_state = {
            'binary': 'neutron-ha-agent',
            'host': host,
            'topic': topics.HA_AGENT,
            'configurations': {
                'ha_check_interval': self.conf.HAAgent.ha_check_interval,
                'agent_report_interval': self.conf.Agent.report_interval,
                'agent_down_time':
                self.conf.agent_down_time,
                'ha_monitor_supported_resource':
                self.conf.HAAgent.ha_monitor_supported_resource, },
            'start_flag': True,
            'agent_type': ha_constants.AGENT_TYPE_HA}
        report_interval = cfg.CONF.Agent.report_interval
        self.use_call = True
        if report_interval:
            self.heartbeat = loopingcall.FixedIntervalLoopingCall(
                self._report_state)
            self.heartbeat.start(interval=report_interval)

    def _report_state(self):
        LOG.debug(_("Report state task started"))
        num_total_dhcp_agents = 0
        num_active_dhcp_agents = 0
        num_down_dhcp_agents = 0
        num_to_migrate_networks = 0
        num_total_l3_agents = 0
        num_active_l3_agents = 0
        num_down_l3_agents = 0
        num_to_migrate_routers = 0
        num_total_lbaas_agents = 0
        num_active_lbaas_agents = 0
        num_down_lbaas_agents = 0
        num_to_migrate_loadbalancers = 0
        num_metadata_agents = 0
        num_total_l2_agents = 0
        num_active_l2_agents = 0
        num_down_l2_agents = 0
        num_total_l2_devices = 0
        for agent in self.agent_infos:
            if(agent.agent_type == ha_constants.AGENT_TYPE_DHCP):
                num_total_dhcp_agents += 1
                if(agent.agent_state):
                    num_active_dhcp_agents += 1
                else:
                    num_down_dhcp_agents += 1
                    num_to_migrate_networks += agent.resource['count']
            elif(agent.agent_type == ha_constants.AGENT_TYPE_L3):
                num_total_l3_agents += 1
                if(agent.agent_state):
                    num_active_l3_agents += 1
                else:
                    num_down_l3_agents += 1
                    num_to_migrate_routers += agent.resource['count']
            elif(agent.agent_type == ha_constants.AGENT_TYPE_LOADBALANCER):
                num_total_lbaas_agents += 1
                if(agent.agent_state):
                    num_active_lbaas_agents += 1
                else:
                    num_down_lbaas_agents += 1
                    num_to_migrate_loadbalancers += agent.resource['count']
            elif(agent.agent_type in L2_Agent_Types):
                num_total_l2_agents += 1
                num_total_l2_devices += agent.resource['count']
                if(agent.agent_state):
                    num_active_l2_agents += 1
                else:
                    num_down_l2_agents += 1
            elif(agent.agent_type == ha_constants.AGENT_TYPE_METADATA):
                num_metadata_agents += 1

        configurations = self.agent_state['configurations']
        configurations['dhcp_agents'] = {}
        configurations['dhcp_agents'][
            'total_agents_count'] = num_total_dhcp_agents
        configurations['dhcp_agents'][
            'active_agents_count'] = num_active_dhcp_agents
        configurations['dhcp_agents'][
            'down_agents_count'] = num_down_dhcp_agents
        configurations['dhcp_agents'][
            'to_migrate_resources'] = num_to_migrate_networks
        configurations['l3_agents'] = {}
        configurations['l3_agents']['total_agents_count'] = num_total_l3_agents
        configurations['l3_agents'][
            'active_agents_count'] = num_active_l3_agents
        configurations['l3_agents']['down_agents_count'] = num_down_l3_agents
        configurations['l3_agents'][
            'to_migrate_resources'] = num_to_migrate_routers
        configurations['lbaas_agents'] = {}
        configurations['lbaas_agents'][
            'total_agents_count'] = num_total_lbaas_agents
        configurations['lbaas_agents'][
            'active_agents_count'] = num_active_lbaas_agents
        configurations['lbaas_agents'][
            'down_agents_count'] = num_down_lbaas_agents
        configurations['lbaas_agents'][
            'to_migrate_resources'] = num_to_migrate_loadbalancers
        configurations['metadata_agents'] = num_metadata_agents
        configurations['l2_agents'] = {}
        configurations['l2_agents']['total_agents_count'] = num_total_l2_agents
        configurations['l2_agents'][
            'active_agents_count'] = num_active_l2_agents
        configurations['l2_agents']['down_agents_count'] = num_down_l2_agents
        configurations['l2_agents']['devices_count'] = num_total_l2_devices

        try:
            self.state_rpc.report_state(self.context, self.agent_state,
                                        self.use_call)
            self.agent_state.pop('start_flag', None)
            self.use_call = False
            LOG.debug(_("Report state task successfully completed"))
        except AttributeError:
            # This means the server does not support report_state
            LOG.warn(_("Neutron server does not support state report."
                       " State report for this agent will be disabled."))
            self.heartbeat.stop()
            return
        except Exception:
            LOG.exception(_("Failed reporting state!"))


def register_options(conf):
    conf.register_opts(HAAgent.OPTS, group='HAAgent')
    conf.register_opts(HAAgent.DEFAULTOPTS)
    conf.register_opts(HAAgent.AGENTREPORTTIME, group='Agent')


def main(manager='neutron.agent.ha_agent.HAAgentWithStateReport'):
    eventlet.monkey_patch()
    conf = cfg.CONF
    register_options(conf)
    conf(project='neutron')
    common_config.init(sys.argv[1:])
    config.setup_logging()
    # legacy.modernize_quantum_config(conf)
    server = neutron_service.Service.create(
        binary='neutron-ha-agent',
        topic=topics.HA_AGENT,
        report_interval=cfg.CONF.Agent.report_interval,
        manager=manager)
    service.launch(server).wait()
