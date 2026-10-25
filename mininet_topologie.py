#!/usr/bin/env python3

from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import info, setLogLevel
from mininet.net import Mininet
from mininet.node import Host, OVSKernelSwitch, RemoteController
from mininet.topo import Topo
from mininet.util import quietRun


class NatGateway(Host):
    """Linux edge router for the private IPv4 and IPv6 networks."""

    def config(self, **params):
        super().config(**params)

        inside, outside = self.intfList()
        self.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=0")
        self.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=0")
        self.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=0")
        self.cmd(
            "sysctl -w net.ipv6.conf.%s.disable_ipv6=0" % inside.name
        )
        self.cmd(
            "sysctl -w net.ipv6.conf.%s.disable_ipv6=0" % outside.name
        )
        self.setIP("10.0.254.2/30", intf=inside)
        self.setIP("198.51.100.2/28", intf=outside)
        self.cmd(
            "ip -6 addr add 2001:db8:254::2/64 dev %s" % inside.name
        )
        self.cmd(
            "ip -6 addr add 2001:db8:ffff::2/64 dev %s" % outside.name
        )
        self.setDefaultRoute("via 198.51.100.1")
        self.cmd(
            "ip -6 route replace default via 2001:db8:ffff::1 dev %s"
            % outside.name
        )
        self.cmd(
            "ip -6 route replace 2001:db8:100::/64 via 2001:db8:254::1 dev %s"
            % inside.name
        )
        self.cmd(
            "ip -6 route replace 2001:db8:200::/64 via 2001:db8:254::1 dev %s"
            % inside.name
        )
        self.cmd(
            "ip -6 route replace 2001:db8:300::/64 via 2001:db8:254::1 dev %s"
            % inside.name
        )

        self.cmd("sysctl -w net.ipv4.ip_forward=1")
        self.cmd("sysctl -w net.ipv6.conf.all.forwarding=1")
        self.cmd("iptables -F")
        self.cmd("iptables -t nat -F")
        self.cmd("ip6tables -F")
        self.cmd("ip6tables -X")
        self.cmd(
            "iptables -t nat -A POSTROUTING "
            "-s 10.0.0.0/8 -o %s -j SNAT --to-source 198.51.100.2"
            % outside.name
        )
        self.cmd(
            "iptables -A FORWARD -i %s -o %s "
            "-m conntrack --ctstate NEW,ESTABLISHED,RELATED -j ACCEPT"
            % (inside.name, outside.name)
        )
        self.cmd(
            "iptables -A FORWARD -i %s -o %s "
            "-m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT"
            % (outside.name, inside.name)
        )
        self.cmd("iptables -A FORWARD -j DROP")

        # IPv6 has no NAT here: the routed /64 prefixes remain visible end to end.
        self.cmd(
            "ip6tables -A FORWARD -i %s -o %s "
            "-m conntrack --ctstate NEW,ESTABLISHED,RELATED -j ACCEPT"
            % (inside.name, outside.name)
        )
        self.cmd(
            "ip6tables -A FORWARD -i %s -o %s "
            "-m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT"
            % (outside.name, inside.name)
        )
        self.cmd("ip6tables -A FORWARD -m conntrack --ctstate INVALID -j DROP")
        self.cmd("ip6tables -A FORWARD -j DROP")


IPV6_ADDRESSES = {
    "a1_emp": ("2001:db8:100::11/64", "2001:db8:100::1"),
    "a2_emp": ("2001:db8:100::12/64", "2001:db8:100::1"),
    "b1_emp": ("2001:db8:100::21/64", "2001:db8:100::1"),
    "b2_emp": ("2001:db8:100::22/64", "2001:db8:100::1"),
    "b3_emp": ("2001:db8:100::23/64", "2001:db8:100::1"),
    "a1_gst": ("2001:db8:200::11/64", "2001:db8:200::1"),
    "a2_gst": ("2001:db8:200::12/64", "2001:db8:200::1"),
    "b1_gst": ("2001:db8:200::21/64", "2001:db8:200::1"),
    "b2_gst": ("2001:db8:200::22/64", "2001:db8:200::1"),
    "b3_gst": ("2001:db8:200::23/64", "2001:db8:200::1"),
    "a1_mgt": ("2001:db8:300::11/64", "2001:db8:300::1"),
    "a2_mgt": ("2001:db8:300::12/64", "2001:db8:300::1"),
    "b1_mgt": ("2001:db8:300::21/64", "2001:db8:300::1"),
    "b2_mgt": ("2001:db8:300::22/64", "2001:db8:300::1"),
    "b3_mgt": ("2001:db8:300::23/64", "2001:db8:300::1"),
}


def enable_ipv6(node, interface):
    """Enable IPv6 in a Mininet namespace for one interface."""
    node.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=0")
    node.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=0")
    node.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=0")
    node.cmd(
        "sysctl -w net.ipv6.conf.%s.disable_ipv6=0" % interface
    )


class BuildingsTopo(Topo):
    def build(self):
        # Gebouw A
        a_core = self.addSwitch(
            "a_core",
            dpid="0000000000000001",
            protocols="OpenFlow13",
            failMode="secure",
        )
        a_f1 = self.addSwitch(
            "a_f1",
            dpid="0000000000000002",
            protocols="OpenFlow13",
            failMode="secure",
        )
        a_f2 = self.addSwitch(
            "a_f2",
            dpid="0000000000000003",
            protocols="OpenFlow13",
            failMode="secure",
        )

        # Gebouw B
        b_core = self.addSwitch(
            "b_core",
            dpid="0000000000000004",
            protocols="OpenFlow13",
            failMode="secure",
        )
        b_f1 = self.addSwitch(
            "b_f1",
            dpid="0000000000000005",
            protocols="OpenFlow13",
            failMode="secure",
        )
        b_f2 = self.addSwitch(
            "b_f2",
            dpid="0000000000000006",
            protocols="OpenFlow13",
            failMode="secure",
        )
        b_f3 = self.addSwitch(
            "b_f3",
            dpid="0000000000000007",
            protocols="OpenFlow13",
            failMode="secure",
        )

        # ISP-hosts op het ene publieke /28-segment.
        isp_a = self.addHost(
            "isp_a",
            ip="198.51.100.1/28",
        )
        isp_b = self.addHost(
            "isp_b",
            ip="198.51.100.3/28",
        )
        # Keep the Linux interface name below 15 characters (IFNAMSIZ).
        nat_gateway = self.addHost("natgw", cls=NatGateway)
        isp_net = self.addSwitch(
            "isp_net",
            dpid="0000000000000008",
            protocols="OpenFlow13",
            failMode="secure",
        )

        # Employeehosts.
        # VLAN 100 gebruikt /23:
        # 10.0.100.0/23 = 510 bruikbare hostadressen.
        a1_emp = self.addHost(
            "a1_emp",
            ip="10.0.100.11/23",
        )
        a2_emp = self.addHost(
            "a2_emp",
            ip="10.0.100.12/23",
        )
        b1_emp = self.addHost(
            "b1_emp",
            ip="10.0.100.21/23",
        )
        b2_emp = self.addHost(
            "b2_emp",
            ip="10.0.100.22/23",
        )
        b3_emp = self.addHost(
            "b3_emp",
            ip="10.0.100.23/23",
        )

        # Guesthosts.
        a1_gst = self.addHost(
            "a1_gst",
            ip="10.0.200.11/24",
        )
        a2_gst = self.addHost(
            "a2_gst",
            ip="10.0.200.12/24",
        )
        b1_gst = self.addHost(
            "b1_gst",
            ip="10.0.200.21/24",
        )
        b2_gst = self.addHost(
            "b2_gst",
            ip="10.0.200.22/24",
        )
        b3_gst = self.addHost(
            "b3_gst",
            ip="10.0.200.23/24",
        )

        # Managementhosts.
        # Vaste MAC-adressen voor Ethernet port security.
        a1_mgt = self.addHost(
            "a1_mgt",
            mac="02:00:00:00:30:11",
            ip="10.0.30.11/24",
        )
        a2_mgt = self.addHost(
            "a2_mgt",
            mac="02:00:00:00:30:12",
            ip="10.0.30.12/24",
        )
        b1_mgt = self.addHost(
            "b1_mgt",
            mac="02:00:00:00:30:21",
            ip="10.0.30.21/24",
        )
        b2_mgt = self.addHost(
            "b2_mgt",
            mac="02:00:00:00:30:22",
            ip="10.0.30.22/24",
        )
        b3_mgt = self.addHost(
            "b3_mgt",
            mac="02:00:00:00:30:23",
            ip="10.0.30.23/24",
        )

        # Gebouw A: core naar verdiepingsswitches.
        self.addLink(a_core, a_f1, port1=1, port2=1)
        self.addLink(a_core, a_f2, port1=2, port2=1)

        # Gebouw B: core naar verdiepingsswitches.
        self.addLink(b_core, b_f1, port1=1, port2=1)
        self.addLink(b_core, b_f2, port1=2, port2=1)
        self.addLink(b_core, b_f3, port1=3, port2=1)

        # Darkfiber tussen de centrale cores.
        self.addLink(a_core, b_core, port1=3, port2=4)

        # A-core naar de private kant van de NAT-gateway.
        self.addLink(a_core, nat_gateway, port1=4, port2=0)
        # Publiek /28-segment aan de buitenkant van de NAT-gateway.
        self.addLink(nat_gateway, isp_net, port1=1, port2=1)
        self.addLink(isp_net, isp_a, port1=2)
        self.addLink(isp_net, isp_b, port1=3)

        # Employeehosts op poort 2.
        self.addLink(a_f1, a1_emp, port1=2, port2=0)
        self.addLink(a_f2, a2_emp, port1=2, port2=0)
        self.addLink(b_f1, b1_emp, port1=2, port2=0)
        self.addLink(b_f2, b2_emp, port1=2, port2=0)
        self.addLink(b_f3, b3_emp, port1=2, port2=0)

        # Guesthosts op poort 3.
        self.addLink(a_f1, a1_gst, port1=3, port2=0)
        self.addLink(a_f2, a2_gst, port1=3, port2=0)
        self.addLink(b_f1, b1_gst, port1=3, port2=0)
        self.addLink(b_f2, b2_gst, port1=3, port2=0)
        self.addLink(b_f3, b3_gst, port1=3, port2=0)

        # Managementhosts op poort 4.
        self.addLink(a_f1, a1_mgt, port1=4, port2=0)
        self.addLink(a_f2, a2_mgt, port1=4, port2=0)
        self.addLink(b_f1, b1_mgt, port1=4, port2=0)
        self.addLink(b_f2, b2_mgt, port1=4, port2=0)
        self.addLink(b_f3, b3_mgt, port1=4, port2=0)


def run_topology(controller_ip):
    topo = BuildingsTopo()

    net = Mininet(
        topo=topo,
        controller=None,
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=False,
        autoPinCpus=False,
    )

    controller = RemoteController(
        "faucet",
        ip=controller_ip,
        port=6653,
    )

    net.addController(controller)

    info("*** Starting network\n")
    net.start()

    info("*** Waiting for switches to connect to Faucet\n")
    quietRun("sleep 5")

    for host_name, (address, gateway) in IPV6_ADDRESSES.items():
        host = net[host_name]
        interface = "%s-eth0" % host_name
        enable_ipv6(host, interface)
        host.cmd("ip -6 addr replace %s dev %s" % (address, interface))
        host.cmd("ip -6 route replace default via %s" % gateway)

    isp_a = net["isp_a"]
    isp_b = net["isp_b"]
    for isp in (isp_a, isp_b):
        interface = "%s-eth0" % isp.name
        enable_ipv6(isp, interface)
    isp_a.cmd("ip -6 addr replace 2001:db8:ffff::1/64 dev isp_a-eth0")
    isp_b.cmd("ip -6 addr replace 2001:db8:ffff::3/64 dev isp_b-eth0")
    for isp in (isp_a, isp_b):
        isp.cmd(
            "ip -6 route replace 2001:db8:100::/64 via 2001:db8:ffff::2"
        )
        isp.cmd(
            "ip -6 route replace 2001:db8:200::/64 via 2001:db8:ffff::2"
        )
        isp.cmd(
            "ip -6 route replace 2001:db8:300::/64 via 2001:db8:ffff::2"
        )

    info("*** Network nodes and links\n")
    CLI(net)

    info("*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--controller-ip",
        required=True,
        help="IP address of the Faucet VM",
    )
    args = parser.parse_args()

    setLogLevel("info")
    run_topology(args.controller_ip)