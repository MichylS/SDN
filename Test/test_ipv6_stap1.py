#!/usr/bin/env python3
"""Tests voor opdracht 3, stap 1: werkt IPv6 per VLAN (nog zonder IPv6-firewall)?

Start IPV6_Topo_opdracht3.py, voert de tests uit en stopt het netwerk weer.
Draaien op de Mininet-VM, in dezelfde map als IPV6_Topo_opdracht3.py:

    sudo python3 test_ipv6_stap1.py --controller-ip 10.24.20.8

Verwachting in stap 1:
  - elke host heeft zijn vaste IPv6-adres en bereikt zijn IPv6-gateway (::1)
  - IPv6 werkt overal: binnen een VLAN, tussen VLAN's, naar en vanaf de ISP
    (de IPv6-firewall komt pas in stap 2)
  - IPv6 gaat zonder NAT naar buiten: isp_a ziet het echte host-adres
  - IPv4 werkt nog precies als in opdracht 2 (firewall + PAT)
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request

from mininet.link import TCLink
from mininet.log import setLogLevel
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import IPV6_Topo_opdracht3 as topo  # noqa: E402

RESULTS = []
EVIDENCE = {}


def ping(net, src, dst_ip, count=3, family=4):
    out = net[src].cmd("ping -%d -n -c %d -W 1 -i 0.3 %s" % (family, count, dst_ip))
    m = re.search(r"([\d.]+)% packet loss", out)
    loss = round(float(m.group(1))) if m else 100
    return loss, out


def record(group, name, ok_expected, ok_actual, detail=""):
    passed = ok_expected == ok_actual
    RESULTS.append({"group": group, "test": name,
                    "expected": "werkt" if ok_expected else "geblokkeerd",
                    "actual": "werkt" if ok_actual else "geblokkeerd",
                    "pass": passed, "detail": detail})
    print("[%s] %-12s %-58s verwacht=%-11s resultaat=%-11s %s" % (
        "PASS" if passed else "FAIL", group, name,
        "werkt" if ok_expected else "geblokkeerd",
        "werkt" if ok_actual else "geblokkeerd", detail), flush=True)


def ping_test(net, group, src, dst_ip, expect_ok, label, family=6):
    # 5 pings: bij het eerste contact mag een pakket wegvallen terwijl Faucet
    # de buur nog opzoekt (neighbor discovery), net als ARP bij IPv4.
    loss, _ = ping(net, src, dst_ip, count=5, family=family)
    record(group, "%s -> %s (%s)" % (src, label, dst_ip), expect_ok, loss < 100,
           "%d%% loss" % loss)


def ip6_of(name):
    """Vast IPv6-adres van een host of ISP-router."""
    if name.startswith("isp_"):
        return topo.isp_ip(name, 6)
    prefix, kind = name.split("_")
    number = dict((p, n) for p, _sw, n in topo.FLOORS)[prefix]
    return topo.host_ip6(kind, number)


STACK_PORTS = ({("a_core", "1"), ("a_core", "2"), ("a_core", "3"),
                ("b_core", "1"), ("b_core", "2"), ("b_core", "3"), ("b_core", "4")}
               | {(sw, "1") for _p, sw, _n in topo.FLOORS})


def stack_up(controller_ip):
    try:
        text = urllib.request.urlopen("http://%s:9302/" % controller_ip, timeout=3).read().decode()
    except OSError:
        return None
    up = {(m.group(1), m.group(2)) for m in re.finditer(
        r'^port_stack_state\{[^}]*dp_name="([^"]+)",port="(\d+)"[^}]*\} ([\d.\-]+)$', text, re.M)
        if float(m.group(3)) == 3.0}
    return STACK_PORTS <= up


def wait_for_network(net, controller_ip, timeout=90):
    """Wacht tot de stack UP is en de IPv4- en IPv6-gateways antwoorden."""
    start = time.time()
    seen_down = False
    while time.time() - start < timeout:
        state = stack_up(controller_ip)
        if state is None:
            time.sleep(12)
            break
        if not state:
            seen_down = True
        elif seen_down or time.time() - start > 15:
            break
        time.sleep(1)
    EVIDENCE["stack_up_sec"] = round(time.time() - start, 1)
    probes = [("a1_emp", "10.0.100.1", 4), ("b3_emp", "2001:db8:a:100::1", 6),
              ("b2_mgt", "2001:db8:a:300::1", 6), ("a2_gst", "2001:db8:a:200::1", 6),
              ("isp_a", "2001:db8:a:500::2", 6), ("isp_b", "198.51.100.2", 4)]
    while time.time() - start < timeout:
        if all(ping(net, h, ip, count=1, family=f)[0] == 0 for h, ip, f in probes):
            return time.time() - start
        time.sleep(3)
    return None


def run(controller_ip, outfile):
    net = Mininet(topo=topo.BuildingsTopo(), controller=None, switch=OVSKernelSwitch,
                  link=TCLink, autoSetMacs=True, autoStaticArp=False, autoPinCpus=False)
    net.addController(RemoteController("faucet", ip=controller_ip, port=6653))
    net.start()
    try:
        topo.configure_hosts(net)
        topo.configure_isp(net)
        t = wait_for_network(net, controller_ip)
        EVIDENCE["opstarttijd_sec"] = round(t, 1) if t is not None else None
        print("Stack UP na %s s, netwerk klaar na %s s" % (
            EVIDENCE["stack_up_sec"], EVIDENCE["opstarttijd_sec"]), flush=True)

        hosts = ["%s_%s" % (p, k) for p, _sw, _n in topo.FLOORS for k in topo.VLANS]

        # 1. Elke host heeft zijn vaste IPv6-adres en bereikt zijn IPv6-gateway.
        for name in hosts:
            kind = name.split("_")[1]
            addr = net[name].cmd("ip -6 -o addr show scope global")
            record("1-adres", "%s heeft %s" % (name, ip6_of(name)), True,
                   ip6_of(name) + "/64" in addr)
            ping_test(net, "1-gateway6", name, topo.gw6(kind), True, "IPv6-gateway")
        EVIDENCE["ipv6_addr_a1_emp"] = net["a1_emp"].cmd("ip -6 addr show dev a1_emp-eth0").strip()
        EVIDENCE["ipv6_route_a1_emp"] = net["a1_emp"].cmd("ip -6 route").strip()

        # 2. Zelfde VLAN over de stack (ook tussen de gebouwen).
        ping_test(net, "2-zelfde-vlan", "a1_emp", ip6_of("b3_emp"), True, "b3_emp")
        ping_test(net, "2-zelfde-vlan", "a1_mgt", ip6_of("b2_mgt"), True, "b2_mgt")

        # 3. Tussen VLAN's: in stap 1 nog open (firewall volgt in stap 2).
        ping_test(net, "3-tussen-vlan", "a1_emp", ip6_of("a2_mgt"), True, "a2_mgt")
        ping_test(net, "3-tussen-vlan", "b1_gst", ip6_of("a1_emp"), True, "a1_emp")

        # 4. Naar de ISP.
        ping_test(net, "4-naar-isp", "a1_emp", ip6_of("isp_a"), True, "isp_a")
        ping_test(net, "4-naar-isp", "b3_gst", ip6_of("isp_b"), True, "isp_b")
        ping_test(net, "4-naar-isp", "a2_mgt", ip6_of("isp_a"), True, "isp_a")

        # 5. Vanaf de ISP: elk VLAN is routeerbaar (in stap 1 nog niet gefilterd).
        ping_test(net, "5-vanaf-isp", "isp_a", ip6_of("a1_emp"), True, "a1_emp")
        ping_test(net, "5-vanaf-isp", "isp_b", ip6_of("b2_gst"), True, "b2_gst")
        ping_test(net, "5-vanaf-isp", "isp_a", ip6_of("b1_mgt"), True, "b1_mgt")

        # 6. Geen NAT bij IPv6: isp_a ziet het echte adres van a1_emp.
        isp_a = net["isp_a"]
        isp_a.cmd("rm -f /tmp/nat6.txt; tcpdump -n -l -i isp_a-eth0 -c 4 'icmp6 and ip6[40] == 128' "
                  "> /tmp/nat6.txt 2>/dev/null &")
        time.sleep(1.5)
        ping(net, "a1_emp", ip6_of("isp_a"), count=2, family=6)
        time.sleep(1.5)
        isp_a.cmd("pkill -f 'tcpdump -n -l -i isp_a-eth0' ; true")
        capture = isp_a.cmd("cat /tmp/nat6.txt")
        EVIDENCE["tcpdump_ipv6_isp_a"] = capture.strip()
        record("6-geen-nat", "bron op isp_a-eth0 = %s (geen NAT)" % ip6_of("a1_emp"), True,
               "%s > %s" % (ip6_of("a1_emp"), ip6_of("isp_a")) in capture)

        # 7. Volledige IPv6-matrix: alle 17 nodes naar alle andere (stap 1: alles open).
        nodes = hosts + ["isp_a", "isp_b"]
        ok, total, missing = 0, 0, []
        for src in nodes:
            for dst in nodes:
                if src == dst:
                    continue
                total += 1
                loss, _ = ping(net, src, ip6_of(dst), count=2, family=6)
                if loss < 100:
                    ok += 1
                else:
                    missing.append("%s->%s" % (src, dst))
        EVIDENCE["ipv6_matrix_missing"] = missing
        record("7-matrix6", "IPv6 alle-naar-alle (%d paren)" % total, True, ok == total,
               "%d/%d bereikt" % (ok, total))

        # 7b. Na minuten nog steeds bereikbaar: Linux controleert buren met zijn
        #     link-local adres. Zonder fe80::1 als VIP raakt de gateway 'FAILED'.
        for r in ("isp_a", "isp_b"):
            neigh = net[r].cmd("ip -6 neigh show %s" % topo.FAUCET_PUBLIC6).strip()
            EVIDENCE["neigh6_%s" % r] = neigh
            record("7b-nd", "%s kent Faucet ::2 nog (neighbor niet FAILED)" % r, True,
                   bool(neigh) and "FAILED" not in neigh, neigh or "(leeg)")
        ping_test(net, "7b-nd", "a2_emp", ip6_of("isp_b"), True, "isp_b (na de matrix)")
        ping_test(net, "7b-nd", "isp_a", ip6_of("b3_mgt"), True, "b3_mgt (na de matrix)")

        # 8. IPv4 werkt nog zoals in opdracht 2.
        ping_test(net, "8-ipv4", "a1_emp", "198.51.100.1", True, "isp_a", family=4)
        ping_test(net, "8-ipv4", "a1_emp", "10.0.200.11", False, "a1_gst", family=4)
        ping_test(net, "8-ipv4", "a1_gst", "10.0.100.11", False, "a1_emp", family=4)
        ping_test(net, "8-ipv4", "a1_mgt", "10.0.100.12", True, "a2_emp", family=4)

        # Bewijs uit de switch.
        sw = net["a_f1"]
        EVIDENCE["flows_a_f1_ipv6_fib"] = sw.cmd(
            "ovs-ofctl -O OpenFlow13 --names --no-stats dump-flows a_f1 table=4 | head -30").strip()
        EVIDENCE["flows_a_f1_acl_ipv6"] = sw.cmd(
            "ovs-ofctl -O OpenFlow13 --names --no-stats dump-flows a_f1 table=0 | grep ipv6").strip()
        EVIDENCE["routes6_isp_a"] = isp_a.cmd("ip -6 route").strip()
    finally:
        net.stop()

    summary = {"totaal": len(RESULTS),
               "geslaagd": sum(1 for r in RESULTS if r["pass"]),
               "mislukt": sum(1 for r in RESULTS if not r["pass"])}
    with open(outfile, "w") as f:
        json.dump({"summary": summary, "results": RESULTS, "evidence": EVIDENCE}, f, indent=2)
    print("\nSamenvatting: %(geslaagd)d/%(totaal)d geslaagd, %(mislukt)d mislukt" % summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-ip", required=True)
    parser.add_argument("--out", default="/tmp/test_ipv6_stap1.json")
    args = parser.parse_args()
    setLogLevel("warning")
    run(args.controller_ip, args.out)
