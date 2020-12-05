import re
import os
import json
import yaml
import logging
import psutil
import subprocess
import time

from mininet.net import Containernet
from mininet.node import Controller, OVSKernelSwitch
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink, Link
from mininet import clean

import docker


logger = logging.getLogger(__name__)

setLogLevel("info")
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("docker").setLevel(logging.WARNING)

TRIGGER_DELAY = 2


class EnvironmentParser:
    def __init__(self):
        self.topology = None
        self.deploy = {}

    def get(self, what):
        if what == "topology":
            return self.topology
        if what == "deploy":
            return self.deploy
        return None

    def parse_nodes(self):
        self.deploy["nodes"] = {}
        self.deploy["switches"] = []

        nodes = self.topology.get("nodes")
        for _node_id, node in nodes.items():
            node_type = node.get("type")
            node_id = node.get("name")

            if node_type == "container":
                self.deploy["nodes"][node_id] = node

            elif node_type == "switch":
                self.deploy["switches"].append(node_id)

        logger.info("Plugin nodes %s", self.deploy["nodes"].keys())

        logger.info("Plugin switches %s", self.deploy["switches"])

    def parse_links(self):
        self.deploy["links"] = {}

        links = self.topology.get("links")
        for _link_id, link in links.items():
            link_type = link.get("type")

            link_src = link.get("src")
            link_dst = link.get("dst")

            if link_type == "internal" or link_type == "external":
                link_id = link_src + "-" + link_dst

                params_dst = link.get("params_dst")
                params_src = link.get("params_src")

                self.deploy["links"][link_id] = {
                    "type": link_type,
                    "src": link_src,
                    "dst": link_dst,
                    "params_src": params_src,
                    "params_dst": params_dst,
                    "resources": link.get("resources", {}),
                }

            else:
                logger.info("unknown link type %s", link_type)

        logger.info("Plugin links %s", self.deploy["links"].keys())

    def build(self, topology):
        logger.debug("Containernet plugin parsing topology")
        logger.debug(f"{topology}")
        self.topology = topology
        self.parse_nodes()
        self.parse_links()
        return self.deploy


class Environment:
    def __init__(self, topo):
        self.parser = EnvironmentParser()
        self.topo = topo
        self.net = None
        self.nodes = {}
        self.switches = {}
        self.nodes_info = {}
        self._docker_client = None
        self._connected_to_docker = False
        self._docker_network = None
        logger.debug("Environment Instance Created")
        logger.debug(f"{json.dumps(self.topo, indent=4)}")

    def connect_docker(self):
        try:
            self._docker_client = docker.from_env()
        except Exception as e:
            self._docker_client = None
            logger.warn(
                "could not connect to docker socket - check if docker is installed/running %s",
                e,
            )
        else:
            self._connected_to_docker = True

    def create_docker_network(self, network_name="umbra"):
        self.connect_docker()

        if self._connected_to_docker:
            try:
                self._docker_network = self._docker_client.networks.create(
                    network_name, driver="bridge"
                )
            except docker.errors.APIError as e:
                logger.debug(f"Docker network not created - API Error {e}")
                return False
            else:
                logger.debug(f"Docker network - {network_name} - created")
                return True
        else:
            logger.debug(f"Could not create docker network")
            return False

    def remove_docker_network(self, network_name="umbra"):
        self.connect_docker()

        if self._connected_to_docker:

            try:
                if not self._docker_network:
                    self._docker_network = self._docker_client.networks.get(
                        network_name
                    )

                if self._docker_network:
                    self._docker_network.remove()

            except docker.errors.APIError as e:
                logger.debug(f"Docker network not removed - API Error {e}")
                return False
            else:
                logger.debug(f"Docker network - {network_name} - removed")
                return True

        else:
            logger.debug(f"Could not remove docker network")
            return False

    def prune_docker_containers(self):
        self.connect_docker()

        if self._connected_to_docker:
            try:
                pruned = self._docker_client.containers.prune()
                logger.debug(f"Docker containers pruned {pruned}")
            except docker.errors.APIError as e:
                logger.debug(f"Docker containers not pruned - API Error {e}")
                return False
            else:
                return True
        else:
            logger.debug(f"Could not prune docker containers")
            return False

    def prune_docker_volumes(self):
        self.connect_docker()

        if self._connected_to_docker:
            try:
                pruned = self._docker_client.volumes.prune()
                logger.debug(f"Docker volumes pruned {pruned}")
            except docker.errors.APIError as e:
                logger.debug(f"Docker volumes not pruned - API Error {e}")
                return False
            else:
                return True
        else:
            logger.debug(f"Could not prune docker volumes")
            return False

    def remove_docker_container(self, container_name):
        self.connect_docker()

        if self._connected_to_docker:
            try:
                container = self._docker_client.containers.get(container_name)
                container.remove()

            except docker.errors.APIError as e:
                logger.debug(f"Docker container not removed - API Error {e}")
                return False
            else:
                logger.debug(f"Docker container - {container_name} - removed")
                return True

        else:
            logger.debug(f"Could not remove docker container")
            return False

    def remove_docker_container_chaincodes(self):
        self.connect_docker()
        chaincodes_removed = {}

        if self._connected_to_docker:
            try:
                containers = self._docker_client.containers.list()
                for container in containers:
                    container_name = container.name
                    if "dev-peer" in container_name:
                        ack = self.remove_docker_container(container_name)
                        chaincodes_removed[container_name] = ack

            except docker.errors.APIError as e:
                logger.debug(f"Docker container chaincodes not removed - API Error {e}")
                return False
            else:
                logger.debug(
                    f"Docker container chaincodes removed {chaincodes_removed}"
                )

                ack_all = all(list(chaincodes_removed.values()))
                return ack_all

        else:
            logger.debug(f"Could not remove docker container")
            return False

    def _create_network(self):
        self.net = Containernet(controller=Controller, link=TCLink)
        self.net.addController("c0")
        logger.info("Created network: %r" % self.net)

    def _add_container(self, node):
        def calculate_cpu_cfs_values(cpu_resources):
            vcpus = int(cpu_resources.get("cpus", 1))
            cpu_bw = float(cpu_resources.get("cpu_bw", 1.0))

            cpu_bw_p = 100000 * vcpus
            cpu_bw_q = int(cpu_bw_p * cpu_bw)
            return cpu_bw_p, cpu_bw_q

        resources = node.get("resources")
        memory = resources.get("memory", 1024)
        cpu_bw_p, cpu_bw_q = calculate_cpu_cfs_values(resources)

        mng_ip = node.get("mng_intf", None)

        logger.debug("Adding container: %s - %s", node.get("name"), node.get("image"))

        container = self.net.addDocker(
            node.get("name"),
            dcmd=node.get("command", None),
            dimage=node.get("image"),
            ip=mng_ip,
            volumes=node.get("volumes", []),
            cpu_period=cpu_bw_p,
            cpu_quota=cpu_bw_q,
            cpuset_cpus="",
            mem_limit=str(memory) + "m",
            memswap_limit=0,
            environment=node.get("env", None),
            ports=node.get("ports", []),
            port_bindings=node.get("port_bindings", {}),
            working_dir=node.get("working_dir", None),
            extra_hosts=node.get("extra_hosts", {}),
            network_mode=node.get("network_mode", "none"),
        )

        logger.debug("Added container: %s", node.get("name"))
        return container

    def _add_nodes(self):
        nodes = self.topo.get("nodes")

        for node_id, node in nodes.items():
            node_type = node.get("type")

            if node_type == "container":
                added_node = self._add_container(node)
                self.nodes[node_id] = added_node

            else:
                logger.info("Node %s not added, unknown format %s", node_id, format)

    def _add_switches(self):
        switches = self.topo.get("switches")
        logger.info("Adding switches %s", switches)

        for sw_name in switches:
            s = self.net.addSwitch(sw_name, cls=OVSKernelSwitch)
            self.switches[sw_name] = s
            logger.info("Switch added %s", s)

    def _add_links(self):
        links = self.topo.get("links")

        for link_id, link in links.items():
            link_type = link.get("type")

            if link_type == "internal":
                src = link.get("src")
                dst = link.get("dst")

                params_src = {}
                params_dst = {}
                intf_src = None
                intf_dst = None

                params_s = link.get("params_src", {})
                params_d = link.get("params_dst", {})

                link_resources = link.get("resources", {})

                if params_s:
                    intf_src = params_s.get("id", None)
                    ip_src = params_s.get("ip", None)
                    if ip_src:
                        params_src["ip"] = str(ip_src)

                if params_d:
                    intf_dst = params_d.get("id", None)
                    ip_dst = params_d.get("ip", None)
                    if ip_dst:
                        params_dst["ip"] = str(ip_dst)

                src_node = (
                    self.nodes.get(src)
                    if src in self.nodes.keys()
                    else self.switches.get(src)
                )
                dst_node = (
                    self.nodes.get(dst)
                    if dst in self.nodes.keys()
                    else self.switches.get(dst)
                )

                logger.info(
                    "Link adding src %s - intf_src %s, dst %s, intf_dst %s, params_src %s, params_dst %s, resources %s",
                    src,
                    intf_src,
                    dst,
                    intf_dst,
                    params_src,
                    params_dst,
                    link_resources,
                )

                link_stats = self.net.addLink(
                    src_node,
                    dst_node,
                    intfName1=intf_src,
                    intfName2=intf_dst,
                    params1=params_src,
                    params2=params_dst,
                    cls=TCLink,
                    **link_resources,
                )

                logger.info("Link Status %s", link_stats)

            else:
                logger.info("Link %s not added, unknown type %s", link_id, link_type)

    def _add_tun_links(self):
        # https://costiser.ro/2016/07/07/overlay-tunneling-with-openvswitch-gre-vxlan-geneve-greoipsec/
        # https://blog.scottlowe.org/2013/05/15/examining-open-vswitch-traffic-patterns/#scenario-3-the-isolated-bridge
        # https://blog.scottlowe.org/2013/05/07/using-gre-tunnels-with-open-vswitch/

        links = self.topo.get("links")

        for link_id, link in links.items():
            link_type = link.get("type")

            if link_type == "external":
                src = link.get("src")
                dst = link.get("dst")

                logger.info(f"Adding external link: src {src} - dst {dst}")

                src_node = self.switches.get(src)
                dst_node = self.switches.get(dst)

                if src_node:
                    node = src_node
                    params = link.get("params_src", {})
                    logger.info(f"Node link: src {src} - params {params}")

                elif dst_node:
                    node = dst_node
                    params = link.get("params_dst", {})
                    logger.info(f"Node link: dst {dst} - params {params}")

                else:
                    logger.info(f"Node link not found: nor dst {dst} nor src {src}")
                    continue

                intf_tun_name = params.get("tun_id", None)
                tun_remote_ip = params.get("tun_remote_ip", None)

                if intf_tun_name and tun_remote_ip:
                    cmd = f" add-port {node.deployed_name} {intf_tun_name} -- set Interface {intf_tun_name} type=gre options:remote_ip={tun_remote_ip}"

                    logger.info(f"Adding external link: {cmd}")

                    ack = node.vsctl(cmd)

                    logger.info(f"Link external {link_type} {link_id} added")
                    logger.info(f"Link external vsctl out: {ack}")
                else:
                    logger.info(
                        f"Could not add external link: missing intf_tun_name {intf_tun_name} or tun_remote_ip {tun_remote_ip}"
                    )

    def _start_network(self):
        if self.net:
            self.net.start()
            logger.info("Started network: %r" % self.net)

    def get_host_ip(self):
        intf = "docker0"
        intfs = psutil.net_if_addrs()
        intf_info = intfs.get(intf, None)
        if intf_info:
            for address in intf_info:
                if address.family == 2:
                    host_address = address.address
                    return host_address
        return None

    def get_host_ips(self, host):
        intf = "eth0"
        config = host.cmd("ifconfig %s 2>/dev/null" % intf)
        # logger.info("get host %s config ips %s", host, config)
        if not config:
            logger.info("Error: %s does not exist!\n", intf)
        ips = re.findall(r"\d+\.\d+\.\d+\.\d+", config)
        if ips:
            # logger.info("host intf ips %s", ips)
            ips_dict = {"ip": ips[0], "broadcast": ips[1], "mask": ips[2]}
            return ips_dict
        return None

    def parse_info(self, elements, specie):
        full_info = {}
        if specie == "hosts":
            full_info["hosts"] = {}
            for host in elements:
                info = {
                    "name": host.name,
                    "intfs": dict(
                        [(intf.name, port) for (intf, port) in host.ports.items()]
                    ),
                    "host_ip": self.get_host_ips(self.nodes[host.name]).get("ip", None),
                }
                full_info["hosts"][host.name] = info

        if specie == "switches":
            full_info["switches"] = {}
            for sw in elements:
                info = {
                    "name": sw.name,
                    "dpid": sw.dpid,
                    "intfs": dict(
                        [(intf.name, port) for (intf, port) in sw.ports.items()]
                    ),
                }
                full_info["switches"][sw.name] = info

        if specie == "links":
            full_info["links"] = {}
            for link in elements:
                link_name = str(link)
                info = {
                    "name": link_name,
                    "src": link.intf1.node.name,
                    "dst": link.intf2.node.name,
                    "intf_isup": link.intf1.isUp() and link.intf2.isUp(),
                    "src-port": link.intf1.name,
                    "dst-port": link.intf2.name,
                }
                full_info["links"][link_name] = info
        return full_info

    def net_topo_info(self):
        info = {}
        info.update(self.parse_info(self.net.hosts, "hosts"))
        info.update(self.parse_info(self.net.switches, "switches"))
        info.update(self.parse_info(self.net.links, "links"))
        logger.info("Topology info:")
        logger.info("%s", info)
        return info

    def start(self):
        self.topo = self.parser.build(self.topo)
        self.create_docker_network()
        self._create_network()
        self._add_nodes()
        self._add_switches()
        self._add_links()
        self._start_network()
        self._add_tun_links()
        logger.info("Experiment running")

        self.nodes_info = self.parse_info(self.net.hosts, "hosts")
        info = {
            "hosts": self.nodes_info.get("hosts"),
            "topology": self.net_topo_info(),
        }
        return True, info

    def _stop_network(self):
        if self.net:
            self.net.stop()
            logger.info("Stopped network: %r" % self.net)

    def mn_cleanup(self):
        clean.cleanup()
        self.remove_docker_container_chaincodes()
        self.remove_docker_network()
        self.prune_docker_volumes()

    def stop(self):
        self._stop_network()
        self.mn_cleanup()
        self.nodes = {}
        self.switches = {}
        self.nodes_info = {}
        self.net = None
        return True, {}

    def stats(self):
        self.nodes_info = self.parse_info(self.net.hosts, "hosts")
        info = {
            "hosts": self.nodes_info.get("hosts"),
            "topology": self.net_topo_info(),
        }

        return True, info

    def end_container(self, node_name):
        err_msg = None
        ok = True

        if node_name not in self.nodes:
            err_msg = f"Container {node_name} does not exist"
            ok = False
            return ok, err_msg

        try:
            self.nodes[node_name].terminate()
        except:
            ok = False
            err_msg = f"Failed to kill {node_name}"

        return ok, err_msg

    def update_cpu_limit(
        self, node_name, cpu_quota=-1, cpu_period=-1, cpu_shares=-1, cores=None
    ):
        err_msg = None
        ok = True

        if node_name not in self.nodes:
            err_msg = f"Container {node_name} does not exist"
            ok = False
            return ok, err_msg

        try:
            self.nodes[node_name].updateCpuLimit(
                cpu_quota, cpu_period, cpu_shares, cores
            )
        except:
            ok = False
            err_msg = f"Failed to updateCpuLimit {node_name}"

        return ok, err_msg

    def update_memory_limit(self, node_name, mem_limit=-1, memswap_limit=-1):
        err_msg = None
        ok = True

        if node_name not in self.nodes:
            err_msg = f"Container {node_name} does not exist"
            ok = False
            return ok, err_msg

        try:
            self.nodes[node_name].updateMemoryLimit(mem_limit, memswap_limit)
        except:
            ok = False
            err_msg = f"Failed to updateMemoryLimit {node_name}"

        return ok, err_msg

    def start_node(self, node):
        if node not in self.nodes:
            err_msg = f"Container {node} does not exist"
            logger.debug(err_msg)
            return False

        else:
            self.connect_docker()

            if self._connected_to_docker:
                try:
                    docker_container = self._docker_client.containers.get(node)
                    docker_container.unpause()

                except docker.errors.NotFound as e:
                    logger.debug(f"Docker container not found - {e}")
                except docker.errors.APIError as e:
                    logger.debug(f"Docker container not started - API Error {e}")
                    return False
                else:
                    logger.debug(f"Docker container - {node} - started")
                    return True
            else:
                logger.debug(f"Docker container - {node} - not started")

        return False

    def stop_node(self, node):
        if node not in self.nodes:
            err_msg = f"Container {node} does not exist"
            logger.debug(err_msg)
            return False

        else:
            self.connect_docker()

            if self._connected_to_docker:
                try:
                    docker_container = self._docker_client.containers.get(node)
                    docker_container.pause()

                except docker.errors.NotFound as e:
                    logger.debug(f"Docker container not found - {e}")
                except docker.errors.APIError as e:
                    logger.debug(f"Docker container not stopped - API Error {e}")
                    return False
                else:
                    logger.debug(f"Docker container - {node} - stopped")
                    return True
            else:
                logger.debug(f"Docker container - {node} - not stopped")

        return False

    def update_node_resources(self, node, resources):
        self.nodes[node].update_resources(**resources)

    def update_node(self, node, online, resources):
        logger.info(f"Updating node {node}: online {online} - resources {resources}")
        err_msg = None
        ok = True

        if node not in self.nodes:
            err_msg = f"Container {node} does not exist"
            ok = False
            return ok, err_msg

        try:
            is_running = self.nodes[node]._is_container_running()
            if is_running:
                self.update_node_resources(node, resources)

            if online:
                if is_running:
                    pass
                else:
                    self.start_node(node)

            else:
                if is_running:
                    self.stop_node(node)
                else:
                    pass

            is_running = self.nodes[node]._is_container_running()
            if is_running:
                self.update_node_resources(node, resources)

        except Exception as ex:
            ok = False
            err_msg = f"Failed to update {node} - exception {repr(ex)}"

        logger.info(f"Node updated: {ok}")
        return ok, err_msg

    def update_link_resources(self, src, dst, resources):
        src = self.net.get(src)
        dst = self.net.get(dst)
        links = src.connectionsTo(dst)
        srcLink = links[0][0]
        dstLink = links[0][1]
        srcLink.config(**resources)
        dstLink.config(**resources)

    def update_link(self, src, dst, online, resources):
        logger.info(
            f"Updating link {(src, dst)}: online {online} - resources {resources}"
        )
        ack = False
        if online:
            self.net.configLinkStatus(src, dst, "up")
            ack = True

            if resources:
                self.update_link_resources(src, dst, resources)
                ack = True
        else:
            self.net.configLinkStatus(src, dst, "down")
            ack = True

        logger.info(f"Link updated: {ack}")
        return ack

    def update(self, event):
        ack = False
        err_msg = None

        if self.net:
            logger.info("Updating network: %r" % self.net)
            logger.info("Event: %s", event)

            ev_group = event.get("group")
            ev_specs = event.get("specs")

            if ev_group == "links":
                act = ev_specs.get("action")

                if act == "update":
                    online = ev_specs.get("online")
                    resources = ev_specs.get("resources", None)
                    (src, dst) = event.get("target")
                    ack = self.update_link(src, dst, online, resources)

            if ev_group == "nodes":
                act = ev_specs.get("action")
                online = ev_specs.get("online")
                resources = ev_specs.get("resources", None)
                node = event.get("target")

                ack, err_msg = self.update_node(node, online, resources)

        return ack, err_msg