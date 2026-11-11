#!/usr/bin/env python3
# Dual-stack topologie (opdracht 3, STAP 2): IPv4 + IPv6 per VLAN, met de
# stateful IPv4/IPv6-firewall en gastisolatie uit IPV6_Topo_opdracht3_fw.yml.
# De topologie zelf is gelijk aan stap 1 (IPV6_Topo_opdracht3.py); de
# firewall zit volledig in de Faucet-config.
#
# Gelijk aan IPV4_Topo_opdracht2.py, met IPv6 erbij:
#   - elk VLAN een eigen /64 uit het klantprefix 2001:db8:a::/48
#     (4e groep = VLAN-nummer, gateway = ::1 = Faucet-VIP)
#   - het ISP-segment (VLAN 500) krijgt 2001:db8:a:500::/64:
#     isp_a ::1, Faucet ::2, isp_b ::3 (zelfde nummering als bij IPv4)
#   - de ISP-routers routeren het hele klantprefix naar Faucet: IPv6 heeft
#     geen NAT nodig, elk VLAN is vanaf de ISP routeerbaar.
# IPv4 blijft precies zoals in opdracht 2 (PAT naar 198.51.100.9).
#
# Hosts krijgen vaste IPv6-adressen. Router advertisements (SLAAC) staan op de
# hosts uit, zodat elk host precies één voorspelbaar adres heeft.
import argparse
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Node, OVSKernelSwitch, RemoteController
from mininet.topo import Topo
from mininet.util import quietRun

VLANS = {
    "emp": {"vid": 100, "net4": "10.0.100", "plen4": 23, "net6": "2001:db8:a:100"},
    "gst": {"vid": 200, "net4": "10.0.200", "plen4": 24, "net6": "2001:db8:a:200"},
    "mgt": {"vid": 300, "net4": "10.0.30", "plen4": 24, "net6": "2001:db8:a:300"},
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

# IPv4: publiek /28-blok, in twee helften (zie opdracht 2):
#   198.51.100.0/29 = ISP-segment: isp_a .1, Faucet .2, isp_b .3
#   198.51.100.8/29 = NAT-blok: Faucet zet privé-adressen om naar .9
FAUCET_PUBLIC = "198.51.100.2"
NAT_POOL = "198.51.100.8/29"
NAT_IP = "198.51.100.9"

# IPv6: het klantprefix dat de ISP naar Faucet routeert.
CUSTOMER_PREFIX6 = "2001:db8:a::/48"
FAUCET_PUBLIC6 = "2001:db8:a:500::2"

# ISP-routers: (naam, core-switch, poort, IPv4-adres, IPv6-adres)
ISP_ROUTERS = [
    ("isp_a", "a_core", 4, "198.51.100.1/29", "2001:db8:a:500::1/64"),
    ("isp_b", "b_core", 5, "198.51.100.3/29", "2001:db8:a:500::3/64"),
]


# Router van de ISP: Linux-node met IP-forwarding voor IPv4 en IPv6.
# Geen NAT en geen firewall; dat doet Faucet.
class LinuxRouter(Node):

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")
        self.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=0")
        self.cmd("sysctl -w net.ipv6.conf.all.forwarding=1")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        self.cmd("sysctl -w net.ipv6.conf.all.forwarding=0")
        super().terminate()


def gw4(kind):
    # IPv4-gateway van elk VLAN = Faucet virtual IP (faucet_vips).
    return "%s.1" % VLANS[kind]["net4"]


def gw6(kind):
    # IPv6-gateway van elk VLAN = Faucet virtual IP (faucet_vips).
    return "%s::1" % VLANS[kind]["net6"]


def host_ip6(kind, number):
    # Zelfde hostnummer als bij IPv4: a1 = ::11, b3 = ::23.
    return "%s::%d" % (VLANS[kind]["net6"], number)


def isp_ip(name, family=4):
    # Adres van een ISP-router zonder prefixlengte, bv. isp_ip("isp_a", 6).
    for router, _core, _port, address4, address6 in ISP_ROUTERS:
        if router == name:
            return (address4 if family == 4 else address6).split("/")[0]
    raise KeyError(name)


def enable_ipv6(node, intf):
    # IPv6 aanzetten op het interface (op de Mininet-VM staat het standaard uit).
    node.cmd("sysctl -qw net.ipv6.conf.all.disable_ipv6=0 "
             "net.ipv6.conf.default.disable_ipv6=0 "
             "net.ipv6.conf.%s.disable_ipv6=0" % intf)


class BuildingsTopo(Topo):
    def build(self):
        for name, dpid in SWITCHES:
            self.addSwitch(
                name,
                dpid="%016x" % dpid,
                protocols="OpenFlow13",
                failMode="secure",
            )

        # Hosts per verdieping (IPv4 hier, IPv6 in configure_hosts).
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
        for name, core, port, address4, _address6 in ISP_ROUTERS:
            self.addNode(name, cls=LinuxRouter, ip=address4)
            self.addLink(core, name, port1=port, port2=0)


def configure_hosts(net):
    for prefix, _switch, number in FLOORS:
        for kind in VLANS:
            host = net["%s_%s" % (prefix, kind)]
            intf = host.defaultIntf().name
            # IPv4: default route naar Faucet.
            host.cmd("ip route replace default via %s" % gw4(kind))
            # IPv6: vast adres + default route naar Faucet. Geen SLAAC.
            enable_ipv6(host, intf)
            host.cmd("sysctl -qw net.ipv6.conf.%s.accept_ra=0 "
                     "net.ipv6.conf.%s.autoconf=0" % (intf, intf))
            host.cmd("ip -6 addr add %s/64 dev %s nodad" % (host_ip6(kind, number), intf))
            host.cmd("ip -6 route replace default via %s dev %s" % (gw6(kind), intf))


def configure_isp(net):
    for name, _core, _port, _address4, address6 in ISP_ROUTERS:
        router = net[name]
        intf = router.defaultIntf().name
        # IPv4: het NAT-blok ligt achter Faucet (.2).
        router.cmd("ip route replace %s via %s" % (NAT_POOL, FAUCET_PUBLIC))
        # IPv6: het hele klantprefix ligt achter Faucet (::2). Geen NAT:
        # elk VLAN-subnet is vanaf de ISP gewoon routeerbaar.
        enable_ipv6(router, intf)
        router.cmd("ip -6 addr add %s dev %s nodad" % (address6, intf))
        router.cmd("ip -6 route replace %s via %s dev %s"
                   % (CUSTOMER_PREFIX6, FAUCET_PUBLIC6, intf))


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

    info("*** Configuring hosts and ISP routers (IPv4 + IPv6)\n")
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
