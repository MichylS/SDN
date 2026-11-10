#!/usr/bin/env python3
# IPv4-only topologie (opdracht 2), zonder natgw.
# Routering, firewall en NAT worden door Faucet gedaan (faucet_vips + ct-ACL's
# met ct nat). Faucet zet de privé-adressen om naar zijn publieke adres
# 198.51.100.9. Elk gebouw heeft een eigen ISP-router (isp_a, isp_b): dat is
# apparatuur van de provider, niet door Faucet beheerd. Wat achter de ISP ligt
# (het internet) bouwen we niet na: de ISP-routers zelf zijn het eindpunt.
import argparse
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Node, OVSKernelSwitch, RemoteController
from mininet.topo import Topo
from mininet.util import quietRun

VLANS = {
    "emp": {"vid": 100, "net4": "10.0.100", "plen4": 23},
    "gst": {"vid": 200, "net4": "10.0.200", "plen4": 24},
    "mgt": {"vid": 300, "net4": "10.0.30", "plen4": 24},
}

# (prefix, verdiepingsswitch, hostnummer)
FLOORS = [
    ("a1", "a_f1", 11),
    ("a2", "a_f2", 12),
    ("b1", "b_f1", 21),
    ("b2", "b_f2", 22),
    ("b3", "b_f3", 23),
]

# Poortindeling op elke verdiepingsswitch.
PORTS = {"emp": 2, "gst": 3, "mgt": 4}

# (naam, dpid)
SWITCHES = [
    ("a_core", 1),
    ("a_f1", 2),
    ("a_f2", 3),
    ("b_core", 4),
    ("b_f1", 5),
    ("b_f2", 6),
    ("b_f3", 7),
]

# Publiek /28-blok van de klant, in twee helften:
#   198.51.100.0/29 = ISP-segment: isp_a .1, Faucet .2 (faucet_vip), isp_b .3
#   198.51.100.8/29 = NAT-blok: Faucet zet privé-adressen om naar .9
# Het NAT-adres ligt buiten het VIP-subnet, anders leert Faucet het als host.
PUBLIC_NET = "198.51.100.0/28"
FAUCET_PUBLIC = "198.51.100.2"
NAT_POOL = "198.51.100.8/29"
NAT_IP = "198.51.100.9"

# ISP-routers: (naam, core-switch, poort, adres in het ISP-segment)
ISP_ROUTERS = [
    ("isp_a", "a_core", 4, "198.51.100.1/29"),
    ("isp_b", "b_core", 5, "198.51.100.3/29"),
]

# Router van de ISP: Linux-node met IP-forwarding (zoals mininet/examples/linuxrouter.py).
# Geen NAT en geen firewall; dat doet Faucet.
class LinuxRouter(Node):
    
    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        super().terminate()


def gw4(kind):
    # Gateway van elk VLAN = Faucet virtual IP (faucet_vips in de Faucet-config).
    return "%s.1" % VLANS[kind]["net4"]


class BuildingsTopo(Topo):
    def build(self):
        for name, dpid in SWITCHES:
            self.addSwitch(
                name,
                dpid="%016x" % dpid,
                protocols="OpenFlow13",
                failMode="secure",
            )

        # Hosts per verdieping.
        for prefix, switch, number in FLOORS:
            for kind, vlan in VLANS.items():
                name = "%s_%s" % (prefix, kind)
                params = {"ip": "%s.%d/%d" % (vlan["net4"], number, vlan["plen4"])}
                link_opts = {"port1": PORTS[kind], "port2": 0}
                if kind == "mgt":
                    mac = "02:00:00:00:30:%d" % number
                    params["mac"] = mac
                    link_opts["addr2"] = mac
                self.addHost(name, **params)
                self.addLink(switch, name, **link_opts)

        # Gebouw A: core naar verdiepingen.
        self.addLink("a_core", "a_f1", port1=1, port2=1)
        self.addLink("a_core", "a_f2", port1=2, port2=1)

        # Gebouw B: core naar verdiepingen.
        self.addLink("b_core", "b_f1", port1=1, port2=1)
        self.addLink("b_core", "b_f2", port1=2, port2=1)
        self.addLink("b_core", "b_f3", port1=3, port2=1)

        # Darkfiber tussen de cores.
        self.addLink("a_core", "b_core", port1=3, port2=4)

        # ISP-routers: eth0 naar de core-switch, in het ISP-segment.
        for name, core, port, address in ISP_ROUTERS:
            self.addNode(name, cls=LinuxRouter, ip=address)
            self.addLink(core, name, port1=port, port2=0)


def configure_hosts(net):
    for prefix, _switch, _number in FLOORS:
        for kind in VLANS:
            name = "%s_%s" % (prefix, kind)
            net[name].cmd("ip route replace default via %s" % gw4(kind))


def isp_ip(name):
    # IP-adres van een ISP-router zonder prefixlengte, bv. isp_ip("isp_a") = 198.51.100.1.
    for router, _core, _port, address in ISP_ROUTERS:
        if router == name:
            return address.split("/")[0]
    raise KeyError(name)


def configure_isp(net):
    for name, _core, _port, _address in ISP_ROUTERS:
        # Het NAT-blok van de klant ligt achter Faucet (.2): zonder deze route
        # komen antwoorden aan 198.51.100.9 niet terug. Gewone routering, geen NAT.
        net[name].cmd("ip route replace %s via %s" % (NAT_POOL, FAUCET_PUBLIC))


def run_topology(controller_ip):
    net = Mininet(
        topo=BuildingsTopo(),
        controller=None,
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=False,
        autoPinCpus=False,
    )
    net.addController(RemoteController("faucet", ip=controller_ip, port=6653))

    info("*** Starting network\n")
    net.start()

    # De stackpoorten worden ca. 8 s na het verbinden UP; tot dan
    # herconfigureert Faucet de VLAN's en kunnen pings wegvallen.
    info("*** Waiting for switches to connect to Faucet and the stack to come up\n")
    quietRun("sleep 12")

    info("*** Configuring hosts, ISP routers\n")
    configure_hosts(net)
    configure_isp(net)

    info("*** Network ready\n")
    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-ip", required=True, help="IP address of the Faucet VM")
    args = parser.parse_args()

    setLogLevel("info")
    run_topology(args.controller_ip)
