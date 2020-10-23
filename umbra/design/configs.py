import os
import subprocess
import logging
import json
import yaml 
import networkx as nx
import ipaddress
from networkx.readwrite import json_graph
from yaml import load, dump
from collections import defaultdict

logger = logging.getLogger(__name__)


NODES = 10
DEGREE = 5
EDGES_PROB = .5
NEIGHBOUR_EDGES = 5
TOPOLOGIES_FOLDER = "./topos/"
BASE_TOPOLOGIES_FOLDER = "./topos/base/"

# port that umbra-agent binds
AGENT_PORT = 8910

class Graph:
    def __init__(self):
        self.graph = nx.MultiGraph()
        self.nodes = NODES
        self.degree = DEGREE
        self.edge_prob = EDGES_PROB
        self.neighbour_edges = NEIGHBOUR_EDGES
        self.folder = TOPOLOGIES_FOLDER
        self.base_folder = BASE_TOPOLOGIES_FOLDER

    def create_graph(self):
        self.graph = nx.MultiGraph()
    
    def create_random(self, model, kwargs):
        if model == 1:
            degree = kwargs.get("degree", self.degree)
            nodes = kwargs.get("nodes", self.nodes)
            self.graph = nx.random_regular_graph(degree, nodes)
        elif model == 2:
            nodes = kwargs.get("nodes", self.nodes)
            edge_prob = kwargs.get("edge_prob", self.edge_prob)
            self.graph = nx.binomial_graph(nodes, edge_prob)
        elif model == 3:
            nodes = kwargs.get("nodes", self.nodes)
            neighbour_edges = kwargs.get("neighbour_edges", self.neighbour_edges)
            edge_prob = kwargs.get("edge_prob", self.edge_prob)
            self.graph = nx.powerlaw_cluster_graph(nodes, neighbour_edges, edge_prob)
        elif model == 4:
            self.graph = nx.scale_free_graph(self.nodes)
        else:
            nodes = kwargs.get("nodes", self.nodes)
            neighbour_edges = kwargs.get("neighbour_edges", self.neighbour_edges)
            self.graph = nx.barabasi_albert_graph(nodes, neighbour_edges)
        return self.graph

    def parse_filename(self, filename, base=False):
        if base:
            filen = self.base_folder + filename + '.json'
        else:
            filen = self.folder + filename + '.json'
        return filen

    def readfile(self, filename, base):
        filename = self.parse_filename(filename, base=base)
        with open(filename, 'r') as infile:
            data = json.load(infile)
            return data

    def writefile_json(self, data, filename):
        with open(filename, 'w') as outfile:
            json.dump(data, outfile, indent=4, sort_keys=True)
            return True

    def save_graph(self, graph, filename, parse_filename=True, base=False):
        if parse_filename:
            filename = self.parse_filename(filename, base=base)
        data = json_graph.node_link_data(graph)
        if self.writefile_json(data, filename):
            return True
        return False

    def retrieve_graph(self, filename, base=False):
        data = self.readfile(filename, base=base)
        graph = json_graph.node_link_graph(data)
        return graph

    def parse(self, data):
        self.create_graph()
        nodes = data.get("nodes", {})
        links = data.get("links", {})

        for node in nodes:
            node_name = node.get("name")
            if node_name:
                self.graph.add_node(node_name, **node)

        for link in links:
            src, dst = link.get("src", None), link.get("dst", None)
            if src and dst:
                self.graph.add_edge(src, dst, **link)

    def shortest_path(self, src, dst):
        path = nx.shortest_path(self.graph, source=src, target=dst)
        return path


class Profile:
    def __init__(self, profile_name):
        self.name = profile_name
        self.node_ids = 1
        self.link_ids = 5000
        self.nodes = {}
        self.links = {}

    def load(self, data):
        self.nodes = data.get("nodes", {})
        self.links = data.get("links", {})

    def dump(self):
        profile = {
            "nodes": self.nodes,
            "links": self.links,
        }
        return profile

    def build_node_resources(self, cpus, memory, disk):
        resources = {
            "cpus": cpus,
            "memory": memory,
            "disk": disk,
        }
        return resources

    def build_link_resources(self, bw, delay, loss):
        resources = {
            "bw": bw,
            "delay": delay,
            "loss": loss,
        }
        return resources

    def add_node(self, node_resources, node_type, node_name=None):
        node_id = self.node_ids
        self.node_ids += 1
        node = {
            "id": node_id,
            "type": node_type,
            "name": node_name,
            "resources": node_resources,
        }
        self.nodes[node_id] = node
        return node

    def add_link(self, link_resources, link_type):
        link_id = self.link_ids
        self.link_ids += 1
        link = {
            "id": link_id,
            "type": link_type,
            "resources": link_resources,
        }
        self.links[link_id] = link
        return link

    def get_node(self, node):
        node_type = node.get("type")
        resources = self.look_for(node_type, where="nodes")
        profile = {"resources": resources}
        return profile

    def get_link(self, link):
        link_type = link.get("type")
        resources = self.look_for(link_type, where="links")
        profile = {"resources": resources}
        return profile

    def look_for(self, _type, where):
        if where == "nodes":
            itemset = self.nodes.items()
        elif where == "links":
            itemset = self.links.items()
        else:
            logger.debug("Could not look for profile where %s", where)
            return None
        types = [(k,v) for (k,v) in itemset if v["type"] == _type ]
        if types:
            (k,v) = types.pop()
            resources = v["resources"]
            return resources
        else:
            logger.debug("Could not look for profile where %s type %s", where, _type)
            return None


class Lifecycle:
    def __init__(self, name):
        self.name = name
        self.node_ids = 1
        self.link_ids = 5000
        self.nodes = {}
        self.links = {}

    def build_node_workflow(self, name, parameters, method, implementation):
        workflow = {
            "workflow": name,
            "parameters": parameters,
            "method": method,
            "implementation": implementation,
        }
        return workflow

    def add_node(self, workflows, node_name, node_type=None):
        node_id = self.node_ids
        self.node_ids += 1
        node = {
            "id": node_id,
            "type": node_type,
            "name": node_name,
            "workflows": workflows,
        }
        self.nodes[node_id] = node
        return node

    def get_node(self, node):
        node_name = node.get("name")
        workflows = self.look_for(node_name, where="nodes")
        lifecycle = {"lifecycle": workflows}
        return lifecycle

    def look_for(self, name, where):
        if where == "nodes":
            itemset = self.nodes.items()
        else:
            # logger.warning("Could not look for workflows where %s", where)
            return None
        types = [(k,v) for (k,v) in itemset if v["name"] == name ]
        if types:
            (k,v) = types.pop()
            workflows = v["workflows"]
            return workflows
        else:
            # logger.error("Could not look for workflows where %s name %s", where, name)
            return None

    def load(self, data):
        self.nodes = data.get("nodes", {})
        self.links = data.get("links", {})

    def dump(self):
        lifecycle = {
            "nodes": self.nodes,
            "links": self.links,
        }
        return lifecycle


class Topology(Graph):
    def __init__(self, name, profile_name=None):
        Graph.__init__(self)
        self.name = name
        self.topo = None
        self.umbra = {}
        self.profile = None
        self.profile = Profile(profile_name)
        self.lifecycle = Lifecycle(name)

    def get(self):
        return self.topo
        
    def load_base(self, filename):
        self.graph = self.retrieve_graph(filename, base=True)
        if self.graph:
            return True
        return False

    def store(self):
        self.build()
        self.graph.graph["name"] = self.name
        self.graph.graph["umbra"] = self.umbra
        self.graph.graph["profile"] = self.profile.dump()
        self.graph.graph["lifecycle"] = self.lifecycle.dump()
        ack = self.save_graph(self.graph, self.name)
        return ack 

    def parse(self, data):
        super(Topology, self).parse(data)
        if self.graph:
            self.fill(data)
            return True
        return False

    def fill(self, data=None):
        data = data if data else self.graph.graph
        self.name = data.get("name", None)
        self.umbra = data.get("umbra", {})
        profile = data.get("profile", {})
        self.profile = Profile(self.name)
        self.profile.load(profile)
        lifecycle = data.get("lifecycle", {})
        self.lifecycle = Lifecycle(self.name)
        self.lifecycle.load(lifecycle)

    def load(self, filename):
        self.graph = self.retrieve_graph(filename)
        if self.graph:
            self.fill()
            return True
        return False
        
    def add_node(self, node_name, node_type, **kwargs):
        node_attribs = {
            "name": node_name,
            "type": node_type,
        }
        node_attribs.update(kwargs)
        self.graph.add_node(node_name, **node_attribs)

    def add_link_nodes(self, src, dst, link_type, params_src=None, params_dst=None):
        link_attribs = {
            "src": src,
            "dst": dst,
            "type": link_type,
            "params_src": params_src,
            "params_dst": params_dst,
        }
        self.graph.add_edge(src, dst, **link_attribs)

    def create_profile(self, profile_name):
        self.profile = Profile(profile_name)

    def create_node_profile(self, cpus, memory, disk):
        node_resources = self.profile.build_node_resources(cpus, memory, disk)
        return node_resources

    def create_link_profile(self, bw, delay, loss):
        link_resources = self.profile.build_link_resources(bw, delay, loss)
        return link_resources

    def create_node_lifecycle(self, workflow, parameters, method, implementation):
        workflow = self.lifecycle.build_node_workflow(workflow, parameters, method, implementation)
        return workflow

    def add_node_lifecycle(self, workflows, node_name):
        if node_name in self.graph.nodes:
            self.lifecycle.add_node(workflows, node_name)
        else:
            logger.error("Lifecycle not added: node_name %s does not exist in topology", node_name)

    def add_node_profile(self, resources, node_type=None, node_name=None):
        if node_type or node_name:
            self.profile.add_node(resources, node_type, node_name=node_name)
        else:
            logger.error("Node profile not added. Please, provide node type or name")       

    def add_link_profile(self, resources, link_type):
        if link_type:
            self.profile.add_link(resources, link_type)
        else:
            logger.error("Link profile not added. Please, provide link type")       

    def set_lifecycle(self, lifecycle):
        self.lifecycle = lifecycle

    def set_profile(self, profile):
        self.profile = profile

    def get_profile(self):
        return self.profile

    def show(self):
        logger.info("*** Dumping network graph ***")
        logger.info("nodes:")
        for n, data in self.graph.nodes(data=True):
            logger.info(f"  node = {n}, data = {data}")

        logger.info("links:")
        for src, dst, data in self.graph.edges(data=True):
            logger.info(f"  src = {src}, dst = {dst}, data = {data}", data)

    def to_dot(self):
        """
        Parse networkx graph into Graphiz Dot format

        Return a string in Graphviz Dot format showing the
        connections between all the nodes in the Topology
        """
        dot_fmt = "strict graph  {"

        # Populate list of nodes
        for n in self.graph.nodes():
            dot_fmt += f"\"{n}\";"

        # Populate the connection between nodes
        for src, dst, data in self.graph.edges(data=True):
            if data.get("deploy", {}).get("intf_isup", True):
                dot_fmt += f"\"{src}\" -- \"{dst}\";"

        dot_fmt += "}"

        return dot_fmt

    def build(self):
        nodes = []
        links = []
        for n, data in self.graph.nodes(data=True):
            node = data
            resources = self.profile.get_node(node)
            lifecycle = self.lifecycle.get_node(node)
            node.update(resources)
            node.update(lifecycle)
            nodes.append(node)

        for src, dst, data in self.graph.edges(data=True):
            link = data
            # link["connection-points"] = [ src, dst ]
            resources = self.profile.get_link(link)
            if resources:
                link.update(resources)
            links.append(link)

        self.topo = {
            "nodes": nodes,
            "links": links,
        }
        return self.topo

    def has(self, cat, name):
        if cat == "node":
            ack = name in self.graph.nodes()
        elif cat == "link":
            ack = name in self.graph.edges()
        else:
            ack = False
        return ack

    def get_data(self, cat, name):
        info = None
        if self.has(cat, name):               
            if cat == "node":
                info = self.graph.nodes[name]
            if cat == "link":
                info = self.graph.edges[name]
        return info

    def fill_hosts_config(self, hosts_info):
        for n, data in self.graph.nodes(data=True):
            if n in hosts_info.keys():
                data["deploy"] = hosts_info.get(n)
        
    def fill_config(self, deploy_config):
        hosts = deploy_config.get("hosts")
        switches = deploy_config.get("switches")
        links = deploy_config.get("links")
        
        for n, data in self.graph.nodes(data=True):
            if n in hosts.keys():
                data["deploy"] = hosts.get(n)
            elif n in switches.keys():
                data["deploy"] = switches.get(n)
            else:
                logger.debug("unknown node %s", n)

        for link in links.values():
            src, dst = link.get("src"), link.get("dst")
            if (src, dst) in self.graph.edges():
                data = self.graph.get_edge_data(src, dst, 0)
                data["deploy"] = link

    def get_link_deploy_data_as(self, src, dst):
        if (src, dst) in self.graph.edges():
            data = self.graph.get_edge_data(src, dst, 0)
            data_src, data_dst = data.get("deploy").get("src"), data.get("deploy").get("dst")

            if data_src == src:
                return data
            else:
                src_port = data.get("deploy").get("src-port")
                dst_port = data.get("deploy").get("dst-port")
                inv_data = {'deploy': 
                    {'src': dst, 'dst': src, 'name': 'eth1<->s2-eth1', 'src-port': dst_port, 'dst-port': src_port}
                }
                return inv_data

    def get_host_intf_addr(self, path):
        host_dst = path[-1] 

        end_src, end_dst = path[-2], path[-1] 
        end_data = self.get_link_deploy_data_as(end_src, end_dst)
        dst_host_intf = end_data.get("deploy").get("dst-port")

        host_dst_data = self.graph.nodes[host_dst]
        intf_control_info = host_dst_data.get("deploy").get("control").get(dst_host_intf)
        nw_dst_ip = intf_control_info.get("ip") #, intf_control_info.get("mask")
        return nw_dst_ip

    def get_deploy_map(self, path):
        host_src, host_dst = path[0], path[-1] 

        deploy_map = {}

        nw_dst_ip = self.get_host_intf_addr(path)

        for i in range(1, len(path[:-1])):

            prev_src, prev_dst = path[i-1], path[i]
            curr_src, curr_dst = path[i], path[i+1]

            if (prev_src, prev_dst) in self.graph.edges() and (curr_src, curr_dst) in self.graph.edges():
                prev_data = self.get_link_deploy_data_as(prev_src, prev_dst)
                curr_data = self.get_link_deploy_data_as(curr_src, curr_dst)

                prev_deploy = prev_data["deploy"]
                src_port = prev_deploy.get("dst-port")

                curr_deploy = curr_data["deploy"]
                dst_port = curr_deploy.get("src-port")

                sw_data = self.graph.nodes[curr_src]
                
                deploy_src_port = sw_data.get("deploy").get("intfs").get(src_port)
                deploy_dst_port = sw_data.get("deploy").get("intfs").get(dst_port)
                
                sw_dpid = sw_data.get("deploy").get("dpid")

                deploy_map[i] = {"dpid": sw_dpid, "in_port": deploy_src_port, "out_port": deploy_dst_port, "nw_dst_ip": nw_dst_ip}
       
        return deploy_map        

    def read_file(self, filepath):
        data = {}
        try:
            with open(filepath, 'r') as f:
                data = load(f, Loader=yaml.SafeLoader)
        except Exception as e:
            logger.debug('exception: could not read file %s - %s', filepath, e)
        finally:
            return data

    def write_file(self, data, filepath):
        noalias_dumper = yaml.dumper.SafeDumper
        noalias_dumper.ignore_aliases = lambda self, data: True
        try:
            with open(filepath, 'w') as f:
                dump(data, f, indent=4, default_flow_style=False, explicit_start=True, Dumper=noalias_dumper)
                # dump(data, f, default_flow_style=False)
        except Exception as e:
            logger.debug('exception: could not write file %s - %s', filepath, e)
        else:
            logger.debug('write file ok %s - \n%s', filepath, data)


    def _join_full_path(self, temp_dir, filename):
        return os.path.normpath(
            os.path.join(
                os.path.dirname(__file__), temp_dir, filename))

    def _full_path(self, temp_dir):
        return os.path.normpath(
            os.path.join(
                os.path.dirname(__file__), temp_dir))
    

class FabricTopology(Topology):
    def __init__(self, name, cfgs_dir, chaincode_dir, clear_dir=True):
        Topology.__init__(self, name)
        self._tmp_dir = cfgs_dir
        self.project_network = "umbra" #HARDCODED
        self.network_mode = "umbra"
        self.orgs = {}
        self.orderers = {}
        self.agent = {}
        self._config_tx = {}
        self._configtx_fill = {}
        self._networks = {}
        self._ca_ports = 7054
        self._peer_ports = 7000
        self._peer_subports = 51
        self._iperf_port = 5201
        self._ip_network = ipaddress.IPv4Network("172.31.0.0/16")
        self._ip_network_assigned = []
        self._filepath_fabricbase = None
        self._configtx_path = None
        self._configsdk_path = None
        self._chaincode_path = chaincode_dir
        self._cfgs()
        self.clear_cfgs(clear_dir)

    def _cfgs(self):
        filename = "fabric.yaml"
        dirname = "./fabric/base"
        self._filepath_fabricbase = self._join_full_path(dirname, filename)

    def defaults(self):
        self.project_network = "umbra"
        self.network_mode = "umbra"
        self._ca_ports = 7054
        self._peer_ports = 7000
        self._peer_subports = 51
        self.orgs = {}
        self.orderers = {}
        self._config_tx = {}
        self._configtx_fill = {}
        self._networks = {}
        self.clear_cfgs()
        self._ip_network = ipaddress.IPv4Network("172.31.0.0/16")
        self._ip_network_assigned = []

    def clear_cfgs(self, clear_dir=True):
        if clear_dir:
            cfgs_folder = self._full_path(self._tmp_dir)       
            for root, dirs, files in os.walk(cfgs_folder, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))

    def configtx(self, conf):
        self._config_tx = conf

    def add_org_network_link(self, org, network, link_type):
        if network in self._networks:
            net = self._networks[network]
            net["links"][org] = {
                "link": link_type,
            }

    def add_network(self, net):
        if net not in self._networks:
            self._networks[net] = {
                "links": {},
            }

    def add_org(self, name, domain, EnableNodeOUs=True, policies=None):
        org = {
            "name": name,
            "domain": domain,
            "org_fqdn": name + "." + domain,
            "EnableNodeOUs": EnableNodeOUs,
            "msp_id": name + "MSP",
            "peers": {},
            "CAs": {},
            "policies": policies if policies else {},
            "anchor": None,
        }
        if name not in self.orgs:
            self.orgs[name] = org
            logger.info("Org registered %s", name)
        else:
            logger.info("Org already exists %s", name)
               
    def add_orderer(self, name, domain, mode="solo", specs=None, org=None, policies=None, image_tag="1.4.0"):
        orderer = {
            "name": name,
            "domain": domain,
            "mode": mode,
            "specs": specs,
            "orderer_fqdn": name + "." + domain,
            "port": 7050, #TODO Hardcoded! get to know how to change it!
            "ports": [7050],
            "org": org,
            "policies": policies if policies else {},
            "msp_id": name + "MSP",
            "image_tag": image_tag,
            "intf": 1,
            "ips": {},
        }
        if name not in self.orderers:
            orderer["orderer_path"] = self.get_node_dir(orderer, orderer=True)
            orderer["root_config"] = self._full_path(self._tmp_dir)
            
            self.orderers[name] = orderer
            logger.info("Orderer registered %s - %s", name, domain)
        else:
            logger.info("Orderer already exists %s", name)

    def add_agent(self, name, domain, image="umbra-agent", **kwargs):
        """
        Add umbraagent to the topology

        NOTE:2020-08-14: only single agent is tested thus far. So, calling
        this API multiple times to add multiple agents likely won't work
        """
        agent = {
            "name": name,
            "domain": domain,
            "agent_fqdn": name + "." + domain,
            "ports":[AGENT_PORT],
            "org": None,
            "image": image,
            "image_tag": "1.0",
            "intf": 1,
            # AGENT_ADDR is set to the container $HOSTNAME. This will resolve to eth0
            # which is the intf that bridges to the docker0 intf from host machine
            "env": [f"AGENT_ADDR={name}", f"AGENT_PORT={AGENT_PORT}"],
            "ips": {},
        }
        agent.update(kwargs)

        if name not in self.agent:
            self.agent[name] = agent
            logger.info("umbra-agent registered %s - %s", name, agent['agent_fqdn'])
        else:
            logger.info("umbra-agent already exist, name =", name)


    def add_ca(self, name, org_name, domain, ca_admin, ca_admin_pw, image_tag="1.4.0"):
        CA = {
            "name": name,
            "org": org_name,
            "name_org": name + "-" + org_name,
            "domain": domain,
            "port": self._ca_ports,
            "ports": [self._ca_ports],
            "ca_fqdn": ".".join([name, org_name, domain]),
            "image_tag": image_tag,
            "ca_keyfile": None, 
            "ca_admin": ca_admin,
            "ca_admin_pw": ca_admin_pw,
            "intf": 1,
            "ips": {},
        }
        if org_name in self.orgs:
            org = self.orgs[org_name]
            org_CAs = org.get("CAs")
            org_fqdn = ".".join([org_name, domain])
            CA["org_fqdn"] = org_fqdn
            
            if name not in org_CAs:
                org_CAs[name] = CA
                logger.info("CA registered %s - %s", name, org_fqdn)
                self._ca_ports += 1

            else:
                logger.info("CA already exists %s", name)
        else:
            logger.info("Org %s for CA %s not registered", org_name, name)

    def add_peer(self, name, org_name, anchor=False, image_tag="1.4.0"):
        peer = {
            "name": name,
            "org": org_name,
            "anchor": anchor,
            "port": self._peer_ports + self._peer_subports,
            "ports": [self._peer_ports + self._peer_subports, self._iperf_port],
            "chaincode_port": self._peer_ports + self._peer_subports + 1,
            "image_tag": image_tag,
            "project_network": self.project_network,
            "peer_anchor_fqdn": None, #TODO add anchor fqdn when build_configs
            "peer_anchor_port": None,
            "intf": 1,
            "ips": {},
        }

        if org_name in self.orgs:
            org = self.orgs[org_name]
            org_peers = org.get("peers")

            org_fqdn, peer_fqdn = self._format_fqdn(name, org_name)

            if anchor:
                org["anchor"] = name

            peer["peer_msp_id"] = org.get("msp_id")
            peer["org_fqdn"] = org_fqdn
            peer["peer_fqdn"] = peer_fqdn
            peer["peer_path"] = self.get_node_dir(peer)
            peer["root_config"] = self._full_path(self._tmp_dir)
           
            if name not in org_peers:
                self._peer_ports += 1000 #Updates port for next peer
                org_peers[name] = peer
                logger.info("Peer registered %s", peer_fqdn)

            else:
                logger.info("Peer already exists %s", name)
        else:
            logger.info("Org %s for peer %s not registered", org_name, name)

    def _format_fqdn(self, peer_name, org_name):
        org = self.orgs.get(org_name)
        domain = org.get("domain")
        org_fqdn = org_name + "." + domain
        peer_fqdn = peer_name + "." + org_fqdn
        return org_fqdn, peer_fqdn
        
    def _load_base_profile(self, profile_type):       
        datafile = self.read_file(self._filepath_fabricbase)
        if datafile:
            if profile_type in datafile:
                profile_template = datafile.get(profile_type)
                return profile_template
        return None

    def _format_port_bindings(self, port_bindings):
        port_bindings_dict = dict([ tuple(bind.split(":")) for bind in port_bindings ])
        port_bindings_dict = { int(k) : int(v) for k, v in port_bindings_dict.items() }
        return port_bindings_dict

    def _parse_orderer_template(self, orderer):
        orderer_kwargs = {}
        orderer_template = self._load_base_profile("orderer-base")

        image = orderer_template.get("image").format(**{"image_tag": orderer.get("image_tag")})
        environment = orderer_template.get("environment")
        env_vars = self._peer_format_fields_list(orderer, orderer_template.get("environment_format"))
        environment.extend(env_vars)
        volumes = self._peer_format_fields_list(orderer, orderer_template.get("volumes"))
        port_bindings = self._peer_format_fields_list(orderer, orderer_template.get("ports"))

        orderer_kwargs = {
            "image": image,
            "env": environment,
            "volumes": volumes,
            "port_bindings": self._format_port_bindings(port_bindings),
            "ports": orderer.get("ports"),
            "working_dir": orderer_template.get("working_dir"),
            "network_mode": self.network_mode,
            "command": orderer_template.get("command"),            
        }
        return orderer_kwargs

    def _build_orderers(self):
        for orderer in self.orderers.values():
            orderer_kwargs = self._parse_orderer_template(orderer)
            self.add_node(orderer.get("orderer_fqdn"), "container", **orderer_kwargs)

    def _build_agent(self):
        for agent in self.agent.values():
            agent_kwargs = {
                "image": agent.get("image") + ":" + agent.get("image_tag"),
                "env": agent.get("env"),
                "volumes": [],
                "port_bindings": {},
                "ports": agent.get("ports"),
                "working_dir": "",
                "network_mode": self.network_mode,
                "command": "",
            }
            self.add_node(agent.get("agent_fqdn"), "container", **agent_kwargs)

    def _peer_format_fields_list(self, info, fields):
        fields_frmt = []
        for field in fields:
            field_filled = field.format(**info)
            fields_frmt.append(field_filled)
        return fields_frmt

    def _parse_node_template(self, node, template):
        node_kwargs = {}
        node_template = self._load_base_profile(template)

        image = node_template.get("image").format(**{"image_tag": node.get("image_tag")})
        environment = node_template.get("environment")
        env_vars = self._peer_format_fields_list(node, node_template.get("environment_format"))
        environment.extend(env_vars)
        volumes = self._peer_format_fields_list(node, node_template.get("volumes"))
        port_bindings = self._peer_format_fields_list(node, node_template.get("ports"))
        command = node_template.get("command")

        if template == "ca-base":
            command = command.format(**node)

        node_kwargs = {
            "image": image,
            "env": environment,
            "volumes": volumes,
            "port_bindings": self._format_port_bindings(port_bindings),
            "ports": node.get("ports"),
            "working_dir": node_template.get("working_dir"),
            "network_mode": self.network_mode,
            "command": command,            
        }
        return node_kwargs
        
    def _build_peers(self):
        for org in self.orgs.values():
            orgs_peers = org.get("peers")
            for peer in orgs_peers.values():
                peer_kwargs = self._parse_node_template(peer, "peer-base")
                self.add_node(peer.get("peer_fqdn"), "container", **peer_kwargs)

    def _build_CAs(self):
        for org in self.orgs.values():
            orgs_CAs = org.get("CAs")
            for CA in orgs_CAs.values():
                CA_kwargs = self._parse_node_template(CA, "ca-base")
                self.add_node(CA.get("ca_fqdn"), "container", **CA_kwargs)

    def get_network_ip(self):
        available_ips = list(self._ip_network.hosts())
        available_index = len(self._ip_network_assigned)
        ip = str(available_ips[available_index]) + "/" + str(self._ip_network.prefixlen)
        self._ip_network_assigned.append(available_ips[available_index])
        return ip

    def _fill_org_anchors(self):
        for org in self.orgs.values():
            org_peers = org.get("peers")
            peer_anchor_name = org.get("anchor")

            peer_anchor = org_peers.get(peer_anchor_name)
            if not peer_anchor:
                peer_anchor = org_peers.values()[0]
                
            peer_anchor_fqdn = peer_anchor.get("peer_fqdn") 
            peer_anchor_port = peer_anchor.get("port")

            for peer in org_peers.values():
                peer["peer_anchor_fqdn"] = peer_anchor_fqdn
                peer["peer_anchor_port"] = peer_anchor_port

    def _build_network(self): 
        #TODO: check links and set switches stp if needed (remember wait time - convergence)
        # e.g., https://gist.github.com/lantz/7853026

        for net_name,net in self._networks.items():
            self.add_node(net_name, "switch")
            links = net.get("links")

            for org_name in links:
                link_type = links[org_name].get("link")                
                if org_name in self.orgs:
                    org = self.orgs[org_name]
                    org_CAs = org.get("CAs")
                    org_peers = org.get("peers")
                    
                    # logger.debug("Add links for net - org - peers - CAs", net_name, org_name, org_peers.keys(), org_CAs.keys())
                    
                    for peer in org_peers.values():
                        peer_fqdn = peer.get("peer_fqdn")
                        intf = peer.get("intf")
                        intf_name = "eth"+str(intf)
                        intf_ip = self.get_network_ip()
                        self.add_link_nodes(peer_fqdn, net_name, link_type,
                                            params_src={"id": intf_name,
                                                        "interface": "ipv4",
                                                        "ip": intf_ip }) #TODO verify params_src (intf and ipv4)
                        peer["intf"] += 1
                        peer["ips"][intf_name] = intf_ip.split('/')[0]
                        
                    for CA in org_CAs.values():
                        ca_fqdn = CA.get("ca_fqdn")
                        intf = CA.get("intf")
                        intf_name = "eth"+str(intf)
                        intf_ip = self.get_network_ip()
                        self.add_link_nodes(ca_fqdn, net_name, link_type,
                                            params_src={"id": intf_name,
                                                        "interface": "ipv4",
                                                        "ip": intf_ip }) #TODO verify params_src (intf and ipv4)
                        CA["intf"] += 1
                        CA["ips"][intf_name] = intf_ip.split('/')[0]

                
                if org_name in self.orderers:
                    orderer = self.orderers[org_name]
                    orderer_fqdn = orderer.get("orderer_fqdn")
                    intf = orderer.get("intf")
                    intf_name = "eth"+str(intf)
                    intf_ip = self.get_network_ip()
                    self.add_link_nodes(orderer_fqdn, net_name, link_type,
                                        params_src={"id": intf_name,
                                                    "interface": "ipv4",
                                                    "ip": intf_ip }) #TODO verify params_src (intf and ipv4)
                    
                    orderer["intf"] += 1
                    orderer["ips"][intf_name] = intf_ip.split('/')[0]

                if org_name in self.agent:
                    agent = self.agent[org_name]
                    agent_fqdn = agent.get("agent_fqdn")
                    intf = agent.get("intf")
                    intf_name = "eth"+str(intf)
                    intf_ip = self.get_network_ip()
                    self.add_link_nodes(agent_fqdn, net_name, link_type,
                                        params_src={"id": intf_name,
                                                    "interface": "ipv4",
                                                    "ip": intf_ip}
                                        )
                    agent["intf"] += 1
                    ip_addr = intf_ip.split('/')[0]
                    agent["ips"][intf_name] = ip_addr

    def _build_network_dns(self):
        dns_names = {}
        dns_nodes = []

        for net_name,net in self._networks.items():
            links = net.get("links")
            for org_name in links:
                if org_name in self.orgs:
                    org = self.orgs[org_name]
                    org_CAs = org.get("CAs")
                    org_peers = org.get("peers")
                                
                    for peer in org_peers.values():
                        peer_fqdn = peer.get("peer_fqdn")
                        peer_ips = peer.get("ips")

                        dns_nodes.append(peer_fqdn)
                        for ip in peer_ips.values():
                            dns_names[peer_fqdn] = ip

                    for CA in org_CAs.values():
                        ca_fqdn = CA.get("ca_fqdn")
                        ca_ips = CA.get("ips")

                        dns_nodes.append(ca_fqdn)
                        for ip in ca_ips.values():
                            dns_names[ca_fqdn] = ip
                        
                if org_name in self.orderers:
                    orderer = self.orderers[org_name]
                    orderer_fqdn = orderer.get("orderer_fqdn")
                    orderer_ips = orderer.get("ips")
                
                    dns_nodes.append(orderer_fqdn)
                    for ip in orderer_ips.values():
                        dns_names[orderer_fqdn] = ip

                if org_name in self.agent:
                    agent = self.agent[org_name]
                    agent_fqdn = agent.get("agent_fqdn")
                    agent_ips = agent.get("ips")
                    dns_nodes.append(agent_fqdn)

                    for ip in agent_ips.values():
                        dns_names[agent_fqdn] = ip


        for n, data in self.graph.nodes(data=True):
            if n in dns_nodes:
                data['extra_hosts'] = dns_names

    def dump(self, topo):
        fabric_cfgs = {
            'orgs': self.orgs,
            'orderers': self.orderers,
            'agents': self.agent
        }

        info = {
            'plugin': 'fabric',
            'configtx': self._configtx_path,
            'configsdk': self._configsdk_path,
            'chaincode': self._chaincode_path,
            'topology': fabric_cfgs,
        }
        topo["umbra"] = info

    def build(self):
        self._build_peers()
        self._build_CAs()
        self._build_orderers()
        self._build_agent()
        self._build_network()
        self._build_network_dns()
        topo_built = Topology.build(self)
        self.dump(topo_built)
        return topo_built

    def loading(self, root, file, full_path):
        files = []
        p = os.path.join(root, file)
        if full_path:
            file_path = os.path.abspath(p)
            files.append(file_path)
        else:
            files.append(file)
        return files

    def get_filepath(self, folder, endswith=None, full_path=False):
        for root, dirs, files in os.walk(folder):
            for file in files:
                # if file.startswith(file_begin_with):
                if endswith:
                    if file.endswith(endswith):
                        file_path = self.loading(root, file, full_path)
                        return file_path        
                else:
                    file_path = self.loading(root, file, full_path)
                    return file_path        
        return None

    def _fill_node_configs(self):
        for org in self.orgs.values():
            org_CAs = org.get("CAs")
            if org_CAs:
                root_path = self._full_path(self._tmp_dir)
                org_fqdn = org.get("org_fqdn")
                org_ca_dir = os.path.join(
                        root_path, "peerOrganizations", org_fqdn, "ca")
                ca_keyfile = self.get_filepath(org_ca_dir, endswith="_sk", full_path=False)
                for org_CA in org_CAs.values():
                    org_CA["ca_keyfile"] = ca_keyfile.pop()
                    # print("ca_keyfile", org_CA["ca_keyfile"] )
                org_path = self.get_org_dir(org)
                org_CA["org_path"] = org_path
        
    def build_configs(self):
        self._fill_org_anchors()
        self._build_crypto_config()
        self._build_configtx()
        self._build_config_sdk()
        self._fill_node_configs()

    def get_peers(self, org):
        org_peers = org.get("peers") 
        num_peers = len(org_peers.values())
        return num_peers
       
    def _call(self, args):
        return_code = 0
        out, err = '', None
        try:
            p = subprocess.Popen(args,
                stdin = subprocess.PIPE,
                stdout = subprocess.PIPE,
                stderr = subprocess.PIPE,
                )
            self.process = p
            logger.debug('process started %s', p.pid)
            out, err = p.communicate()
            return_code = p.returncode
        except OSError:
            return_code = -1
            err = 'ERROR: exception OSError'
        finally:
            if return_code != 0:
                answer = err
            else:
                answer = out
            self.process = None
            logger.debug("Return code %s - output %s", return_code, answer)
            return return_code, answer

    def _build_crypto_config(self):
        crypto_config = {
            "OrdererOrgs": [],
            "PeerOrgs": []
        }

        for org in self.orgs.values():
            num_org_peers = self.get_peers(org)
            
            org_frmt = {
                "Name": org.get("name"),
                "Domain": org.get("name") + "." + org.get("domain"),
                "EnableNodeOUs": org.get("EnableNodeOUs"),
                "Template": {
                    "Count": num_org_peers, # TODO: assign peer names accordingly
                },
                "Users": {
                    "Count": 1,
                }
            }

            crypto_config["PeerOrgs"].append(org_frmt)


        for orderer in self.orderers.values():
            ord_frmt = {
                "Name": orderer.get("name"),
                "Domain": orderer.get("domain"),
                "Specs": orderer.get("specs") if orderer.get("specs") else [],
            }
            crypto_config["OrdererOrgs"].append(ord_frmt)

        filename = "crypto-config.yaml"
        filepath = self._join_full_path(self._tmp_dir, filename)
        output_path = self._full_path(self._tmp_dir)

        logger.info("Saving Fabric crypto config file %s", filepath) 
        self.write_file(crypto_config, filepath)

        cmd = [self._join_full_path("./fabric/bin/", "cryptogen")]
        args = ["generate", "--config", filepath, "--output", output_path]
        cmd.extend(args)
        logger.info("Generating  crypto-config.yaml folder structure - calling cryptogen")
        logger.debug("Calling %s", cmd)
        self._call(cmd)

    def get_node_dir(self, node, orderer=False):
        root_path = self._full_path(self._tmp_dir)
        
        if orderer:
            org_type = "ordererOrganizations"
            org_fqdn = node.get("domain")
            peer_fqdn = node.get("name") + "." + org_fqdn
            node_dir = os.path.join(
                    root_path, org_type, org_fqdn, "orderers", peer_fqdn)
        else:
            org_name = node.get("org")
            org_type = "peerOrganizations"
            org_fqdn, peer_fqdn = self._format_fqdn(node.get("name"), org_name)            
            node_dir = os.path.join(
                    root_path, org_type, org_fqdn, "peers", peer_fqdn)
        return node_dir

    def get_msp_dir(self, org, orderer=False):
        root_path = self._full_path(self._tmp_dir)
        if orderer:
            org_type = "ordererOrganizations"  
            org_fqdn = org.get("domain")
        else:
            org_type = "peerOrganizations"
            org_fqdn = org.get("name") + "." + org.get("domain")
        org_msp_dir = os.path.join(
                root_path, org_type, org_fqdn, "msp")
        return org_msp_dir

    def get_org_dir(self, org, orderer=False):
        root_path = self._full_path(self._tmp_dir)
        if orderer:
            org_type = "ordererOrganizations"
            org_fqdn = org.get("domain")
            org_dir = os.path.join(
                    root_path, org_type, org_fqdn)
        else:
            org_type = "peerOrganizations"
            org_fqdn = org.get("name") + "." + org.get("domain")
            org_dir = os.path.join(
                    root_path, org_type, org_fqdn)
        return org_dir

    def get_path(self, data, path):
        fields = path.split(".")
        fields.reverse()
        datapath = data
        while fields:
            f = fields.pop()
            datapath = datapath.get(f)
        return datapath

    def _frmt_configtx_profiles(self, orgs):
        profiles = self._config_tx.get("Profiles")
        for path,value in self._configtx_fill.items():
            datapath = self.get_path(profiles, path)
            org_names = value.get("fields")
            for org_name in org_names:
                org = orgs.get(org_name)
                datapath.remove(org_name)
                datapath.append(org)
                    
    def set_configtx_profile(self, path, fields):
        self._configtx_fill[path] = {
            "fields": fields,
        }

    def _build_configtx(self):
        orgs_frmt = {}

        for org in self.orgs.values():
            anchors = []
            anchor = org.get("anchor")
            if anchor:
                org_peers = org.get("peers")
                peer = org_peers.get(anchor)
                _, peer_fqdn = self._format_fqdn(anchor, org.get("name"))
                anchor_info = {
                    "Host": peer_fqdn, 
                    "Port": peer.get("port")
                }
                anchors = [anchor_info]

            org_frmt = {
                "Name": org.get("name") + "MSP",
                "ID": org.get("name") + "MSP",
                "MSPDir": self.get_msp_dir(org),
                "Policies": org.get("policies"),
                "AnchorPeers": anchors,
            }    
            orgs_frmt[org.get("name")] = org_frmt
            self._config_tx["Organizations"].append(org_frmt)

        for order in self.orderers.values():
            org_frmt = {
                "Name": order.get("name") + "Org",
                "ID": order.get("name") + "MSP",
                "MSPDir": self.get_msp_dir(order, orderer=True),
                "Policies": order.get("policies"),
            }    
            orgs_frmt[order.get("name")] = org_frmt
            self._config_tx["Organizations"].append(org_frmt)

        self._frmt_configtx_profiles(orgs_frmt)

        filename = "configtx.yaml"
        filepath = self._join_full_path(self._tmp_dir, filename)
        output_path = self._full_path(self._tmp_dir)

        logger.info("Saving Fabric configtx file %s", filepath) 
        self.write_file(self._config_tx, filepath)
        self._configtx_path = output_path

        cmd = self._join_full_path("./fabric/bin/", "configtxgen")
        logger.info("Generating  configtx.yaml files - calling configtxgen")

        #TODO generate genesis args according to orderer choosen
        genesis_args = [
            "-configPath", output_path,
            "-profile", "TwoOrgsOrdererGenesis",
            "-channelID", "examplechannel",
            "-outputBlock", output_path+"/genesis.block"
        ]

        channel_args = [
            "-configPath", output_path,
            "-profile", "TwoOrgsChannel",
            "-channelID", "testchannel",
            "-outputCreateChannelTx", output_path+"/channel.tx"
        ]
        
        #TODO generate anchor args according to anchor peers in orgs
        anchor_args1 = [
            "-configPath", output_path,
            "-profile", "TwoOrgsChannel",
            "-channelID", "testchannel",
            "-outputAnchorPeersUpdate", output_path+"/Org2MSPanchors.tx",
            "-asOrg", "org2MSP",
        ]

        anchor_args2 = [
            "-configPath", output_path,
            "-profile", "TwoOrgsChannel",
            "-channelID", "testchannel",
            "-outputAnchorPeersUpdate", output_path+"/Org1MSPanchors.tx",
            "-asOrg", "org1MSP",
        ]

        self._build_configtx_call(cmd, genesis_args)
        self._build_configtx_call(cmd, channel_args)
        self._build_configtx_call(cmd, anchor_args1)
        self._build_configtx_call(cmd, anchor_args2)

    def _build_configtx_call(self, cmd, args):
        cmd_list = []
        cmd_list.append(cmd)
        cmd_list.extend(args)
        logger.debug("Calling %s", cmd_list)
        self._call(cmd_list)

    def _get_org_users(self, org, is_orderer=False):
        org_dir = self.get_org_dir(org, orderer=is_orderer)
        
        org_users_dir = os.path.join(
            org_dir, "users")
        
        users_info = {}

        for root, dirs, files in os.walk(org_users_dir):
            for user_dir in dirs:
                org_user = user_dir.split("@")[0]
                org_user_cert_name = user_dir + "-cert.pem"
                
                org_user_keystore_path = os.path.join(
                    org_users_dir, user_dir, "msp", "keystore")
                org_user_keystore = self.get_filepath(org_user_keystore_path, endswith="_sk", full_path=True)
                
                users_info[org_user] = {
                    "cert": os.path.join(
                        org_users_dir, user_dir, "msp/signcerts/", org_user_cert_name),
                    "private_key": org_user_keystore.pop(),
                }
            break

        return users_info
        
    def _build_config_sdk(self):
        config = {
            "name": "sample-network",
            "description": "Sample network contains 4 peers (2 orgs), 1 orderer and 2 cas for Python SDK testing",
            "version": "0.1",
            "client": {
                "organization": "org1",
                "credentialStore": {
                "path": "/tmp/hfc-kvs",
                "cryptoStore": {
                    "path": "/tmp/hfc-cvs"
                },
                "wallet": "wallet-name"
                }
            },
        }

        organizations = {}
        for org in self.orgs.values():
            org_peers = org.get("peers")
            org_CAs = org.get("CAs")

            peers_fqdn = [ peer.get("peer_fqdn") for peer in org_peers.values() ] 
            ca_names = [ CA.get("name_org") for CA in org_CAs.values() ]
            org_users = self._get_org_users(org) 

            org_frmt = {
                org.get("org_fqdn"): {
                    "mspid": org.get("msp_id"),
                    "peers": peers_fqdn,
                    "certificateAuthorities": ca_names, 
                    "users": org_users,
                }
            }
            organizations.update(org_frmt)

        orderers = {}

        for orderer in self.orderers.values():
            
            orderers_fqdn = [orderer.get("orderer_fqdn")]
            org_users = self._get_org_users(orderer, is_orderer=True) 

            org_frmt = {
                orderer.get("orderer_fqdn"): {
                    "mspid": orderer.get("msp_id"),
                    "orderers": orderers_fqdn,
                    "certificateAuthorities": [], 
                    "users": org_users,
                }
            }
            organizations.update(org_frmt)

            orderer_dir = self.get_org_dir(orderer, orderer=True)
        
            orderer_tls_dir = os.path.join(
                orderer_dir, "tlsca/")

            orderer_tls_file = self.get_filepath(orderer_tls_dir, endswith=".pem", full_path=True)

            orderer_frmt = {
                orderer.get("orderer_fqdn"): {
                    "url": "localhost:" + str(orderer.get("port")),
                    "grpcOptions": {
                        "grpc.ssl_target_name_override": orderer.get("orderer_fqdn"),
                        "grpc-max-send-message-length": 15,
                    },
                    "tlsCACerts": {
                        "path": orderer_tls_file.pop(),
                    }
                }
            }

            orderers.update(orderer_frmt)

        config["organizations"] = organizations
        config["orderers"] = orderers

        peers = {}
        CAs = {}
        for org in self.orgs.values():
            org_peers = org.get("peers")
            org_CAs = org.get("CAs")

            for peer in org_peers.values():
                peer_dir = self.get_node_dir(peer)
                peer_tls_dir = os.path.join(
                    peer_dir, "msp/tlscacerts/")   
                peer_tls_file = self.get_filepath(peer_tls_dir, endswith=".pem", full_path=True)
                
                peer_frmt = {
                    peer.get("peer_fqdn"): {
                        "url": "localhost:" + str(peer.get("port")),
                        "eventUrl": "localhost:9053", #TODO find peer eventurl (set this ENV in fabric.yaml peer-base)
                        "grpcOptions": {
                            "grpc.ssl_target_name_override": peer.get("peer_fqdn"),
                            "grpc.http2.keepalive_time": 15
                        },
                        "tlsCACerts": {
                            "path": peer_tls_file.pop(),
                        }
                    }
                }
                peers.update(peer_frmt)

            for CA in org_CAs.values():
                org_dir = self.get_org_dir(org)
                org_ca_tls_dir = os.path.join(
                    org_dir, "ca")   
                org_ca_tls_file = self.get_filepath(org_ca_tls_dir, endswith=".pem", full_path=True)

                CA_frmt = {
                    CA.get("name_org"): {
                        "url": "localhost:" + str(CA.get("port")),
                        "grpcOptions": {
                            "verify": True,
                        },
                        "tlsCACerts": {
                            "path": org_ca_tls_file.pop(),
                        },
                        "registrar": [
                            {
                              "enrollId": CA.get("ca_admin"),
                              "enrollSecret": CA.get("ca_admin_pw"),
                            },
                        ]
                    }
                }
                CAs.update(CA_frmt)
                  
        config["certificateAuthorities"] = CAs
        config["peers"] = peers
    
        filename = "fabric_sdk_config.json"
        filepath = self._join_full_path(self._tmp_dir, filename)
        logger.info("Saving Fabric SDK config file %s", filepath) 
        self.writefile_json(config, filepath)
        self._configsdk_path = filepath


class IrohaTopology(Topology):
    def __init__(self, name, cfgs_dir, clear_dir=True):
        Topology.__init__(self, name)
        self._tmp_dir = cfgs_dir
        self.project_network = "umbra" #HARDCODED
        self.network_mode = "umbra"


class EventsFabric:
    def __init__(self):
        self._ids = 1
        self._events = {}

    def add(self, when, category, params):
        ev_id = self._ids
        event = {
            "ev": ev_id,
            "when": when,
            "category": category,
            "params": params,
        }            
        self._events[ev_id] = event
        self._ids += 1

    def build(self):
        return self._events
        
    def parse(self, data):
        self._events = data

class EventsOthers:
    """
    Use this Event class for event category of: monitor, agent, and environment
    """
    def __init__(self):
        self._ev_id = 1;
        self._events = defaultdict(lambda: [])

    def add(self, when, category, ev_args, **kwargs):
        """
        Input for kwargs:

        'until': time (in sec) limit to complete this event
        'duration': expected time to complete an iteration, if 'repeat'
            is set to run more than once
        'interval': delay for the next iteration if 'repeat' is set
        'repeat': repeat the cmd by 'x' iteration. Set to 0 to run
            command only once

        """
        sched = {
            "from": when,
            "until": 0,
            "duration": 0,
            "interval": 0,
            "repeat": 0
        }
        sched.update(kwargs)
        ev_args["schedule"] = sched
        ev_args["id"] = self._ev_id
        self._events[category].append(ev_args)
        self._ev_id += 1

    def build(self):
        return self._events

    def parse(self, data):
        self._events = data

class Scenario:
    def __init__(self, id, entrypoint, folder):
        self.id = id
        self.entrypoint = entrypoint
        self.folder = folder
        self.topology = None
        # ideally, we should have a generic Event class for all kinds of
        # event type: Fabric, Iroha, environment, agent, monitor, etc.
        # To achieve that, all events should use the umbra/common/scheduler.py
        # Currently, FabricEvents (broker/plugin/fabric.py) has custom scheduler
        self.events_fabric = EventsFabric()
        self.events_others = EventsOthers()

    def parse(self, data):
        topo = Topology(None)
        ack = topo.parse(data.get("topology", {}))
        if ack:
            self.topology = topo
            self.events_fabric.parse(data.get("events_fabric", {}))
            self.events_others.parse(data.get("events_others", {}))
            self.name = data.get("id", None)
            self.entrypoint = data.get("entrypoint", None)
            return True
        return False

    def add_event_fabric(self, when, category, params):
        self.events_fabric.add(when, category, params)

    def add_event_others(self, when, category, ev_args):
        """
        Arguments:
            when: run the event at ith-second
            category: environment | agent | monitor
        """
        self.events_others.add(when, category, ev_args)

    def set_topology(self, topology):
        self.topology = topology

    def get_topology(self):
        return self.topology

    def dump(self):
        topo_built = self.topology.build()
        events_fabric_built = self.events_fabric.build()
        events_others_built = self.events_others.build()
        scenario = {
            "id": self.id,
            "entrypoint": self.entrypoint,
            "topology": topo_built,
            "events_fabric": events_fabric_built,
            "events_others": events_others_built
        }
        return scenario

    def save(self):
        data = self.dump()
        filename =  self.id + ".json"

        filepath = os.path.normpath(
            os.path.join(
                self.folder, filename))

        with open(filepath, 'w') as outfile:
            logger.info("Saving config file %s", filepath)
            json.dump(data, outfile, indent=4, sort_keys=True)
            return True

    def load(self, cfg_name):
        filename =  cfg_name + ".json"

        filepath = os.path.normpath(
            os.path.join(
                self.folder, filename))

        with open(filepath, 'r') as infile:
            data = json.load(infile)
            self.parse(data)
