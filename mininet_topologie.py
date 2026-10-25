#!/usr/bin/env python3
import argparse
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import OVSBridge, OVSKernelSwitch, RemoteController
from mininet.topo import Topo
from mininet.util import quietRun

# MAC van de binnenkant van natgw. Faucet-ACL's matchen hierop.
NATGW_MAC = "02:00:00:00:fe:01"
INSIDE = "natgw-eth0"
OUTSIDE = "natgw-eth1"

VLANS = {
    "emp": {"vid": 100, "net4": "10.0.100", "plen4": 23, "net6": "2001:db8:100"},
    "gst": {"vid": 200, "net4": "10.0.200", "plen4": 24, "net6": "2001:db8:200"},
    "mgt": {"vid": 300, "net4": "10.0.30", "plen4": 24, "net6": "2001:db8:300"},
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


def gw4(kind):
    return "%s.254" % VLANS[kind]["net4"]


def gw6(kind):
    return "%s::1" % VLANS[kind]["net6"]


class BuildingsTopo(Topo):
    def build(self):
        for name, dpid in SWITCHES:
            self.addSwitch(
                name,
                dpid="%016x" % dpid,
                protocols="OpenFlow13",
                failMode="secure",
            )

        # ISP-kant: gewone bridge, geen Faucet.
        self.addSwitch("isp_net", cls=OVSBridge, dpid="%016x" % 8)

        # Gateway en ISP-hosts. natgw krijgt zijn adressen later.
        self.addHost("natgw", ip=None, mac=NATGW_MAC)
        self.addHost("isp_a", ip="198.51.100.1/28")
        self.addHost("isp_b", ip="198.51.100.3/28")

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

        # Gateway op a_core poort 4 (trunk met alle VLAN's).
        self.addLink("a_core", "natgw", port1=4, port2=0, addr2=NATGW_MAC)

        # Publiek /28-segment.
        self.addLink("natgw", "isp_net", port1=1)
        self.addLink("isp_net", "isp_a")
        self.addLink("isp_net", "isp_b")


def enable_ipv6(node, interface):
    node.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=0")
    node.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=0")
    node.cmd("sysctl -w net.ipv6.conf.%s.disable_ipv6=0" % interface)


def configure_natgw(net):
    gw = net["natgw"]
    quietRun("modprobe 8021q")

    for command in (
        "sysctl -w net.ipv4.ip_forward=1",
        "sysctl -w net.ipv6.conf.all.disable_ipv6=0",
        "sysctl -w net.ipv6.conf.default.disable_ipv6=0",
        "sysctl -w net.ipv6.conf.all.forwarding=1",
        "sysctl -w net.ipv4.conf.all.send_redirects=0",
        "sysctl -w net.ipv6.conf.%s.disable_ipv6=0" % INSIDE,
        "sysctl -w net.ipv6.conf.%s.disable_ipv6=0" % OUTSIDE,
        "ip addr flush dev %s" % INSIDE,
        "ip link set %s up" % INSIDE,
        "ip link set %s up" % OUTSIDE,
    ):
        gw.cmd(command)

    # Een subinterface per VLAN, met het gateway-adres van dat VLAN.
    for kind, vlan in VLANS.items():
        sub = "%s.%d" % (INSIDE, vlan["vid"])
        gw.cmd("ip link add link %s name %s type vlan id %d" % (INSIDE, sub, vlan["vid"]))
        gw.cmd("ip link set %s up" % sub)
        gw.cmd("ip addr add %s/%d dev %s" % (gw4(kind), vlan["plen4"], sub))
        gw.cmd("ip -6 addr add %s/64 dev %s nodad" % (gw6(kind), sub))

    # Publieke kant.
    gw.cmd("ip addr add 198.51.100.2/28 dev %s" % OUTSIDE)
    gw.cmd("ip -6 addr add 2001:db8:ffff::2/64 dev %s nodad" % OUTSIDE)
    gw.cmd("ip route replace default via 198.51.100.1")
    gw.cmd("ip -6 route replace default via 2001:db8:ffff::1 dev %s" % OUTSIDE)

    emp = "%s.%d" % (INSIDE, VLANS["emp"]["vid"])
    gst = "%s.%d" % (INSIDE, VLANS["gst"]["vid"])
    mgt = "%s.%d" % (INSIDE, VLANS["mgt"]["vid"])

    for tool in ("iptables", "ip6tables"):
        gw.cmd("%s -F" % tool)
        gw.cmd("%s -X" % tool)
        gw.cmd("%s -P INPUT DROP" % tool)
        gw.cmd("%s -P FORWARD DROP" % tool)
        gw.cmd("%s -P OUTPUT ACCEPT" % tool)
        gw.cmd("%s -A INPUT -i lo -j ACCEPT" % tool)
        gw.cmd("%s -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT" % tool)
        gw.cmd("%s -A INPUT -i %s.+ -j ACCEPT" % (tool, INSIDE))
        gw.cmd("%s -A FORWARD -m conntrack --ctstate INVALID -j DROP" % tool)
        gw.cmd("%s -A FORWARD -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT" % tool)
        # Nieuwe verbindingen van binnen naar de ISP.
        for sub in (emp, gst, mgt):
            gw.cmd(
                "%s -A FORWARD -i %s -o %s -m conntrack --ctstate NEW -j ACCEPT"
                % (tool, sub, OUTSIDE)
            )
        # Management mag verbindingen starten naar employee en guest.
        for target in (emp,):
            gw.cmd(
                "%s -A FORWARD -i %s -o %s -m conntrack --ctstate NEW -j ACCEPT"
                % (tool, mgt, target)
            )
        # Alles anders valt onder de FORWARD DROP-policy:
        # employee -> guest/management, guest -> guest (hairpin),
        # guest -> intern en alle nieuwe verbindingen vanaf de ISP.

    # IPv6 neighbour discovery op de publieke kant.
    for icmp_type in ("neighbour-solicitation", "neighbour-advertisement"):
        gw.cmd(
            "ip6tables -A INPUT -i %s -p ipv6-icmp --icmpv6-type %s -j ACCEPT"
            % (OUTSIDE, icmp_type)
        )

    # IPv4 PAT: alle interne adressen delen 198.51.100.2.
    gw.cmd("iptables -t nat -F")
    gw.cmd(
        "iptables -t nat -A POSTROUTING -s 10.0.0.0/8 -o %s "
        "-j SNAT --to-source 198.51.100.2" % OUTSIDE
    )


def configure_hosts(net):
    for prefix, _switch, number in FLOORS:
        for kind, vlan in VLANS.items():
            name = "%s_%s" % (prefix, kind)
            host = net[name]
            interface = "%s-eth0" % name
            enable_ipv6(host, interface)
            host.cmd("ip route replace default via %s" % gw4(kind))
            host.cmd(
                "ip -6 addr replace %s::%d/64 dev %s nodad"
                % (vlan["net6"], number, interface)
            )
            host.cmd("ip -6 route replace default via %s dev %s" % (gw6(kind), interface))


def configure_isp(net):
    for name, suffix in (("isp_a", "1"), ("isp_b", "3")):
        isp = net[name]
        interface = "%s-eth0" % name
        enable_ipv6(isp, interface)
        isp.cmd("ip -6 addr replace 2001:db8:ffff::%s/64 dev %s nodad" % (suffix, interface))
        # Terugroutes naar de interne IPv6-prefixen (geen NAT bij IPv6).
        for vlan in VLANS.values():
            isp.cmd(
                "ip -6 route replace %s::/64 via 2001:db8:ffff::2 dev %s"
                % (vlan["net6"], interface)
            )


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

    info("*** Waiting for switches to connect to Faucet\n")
    quietRun("sleep 6")

    info("*** Configuring natgw, hosts and ISP\n")
    configure_natgw(net)
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
mininet@mininet-vm:~/sdn-opdracht2/topology$ 