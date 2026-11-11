#!/usr/bin/env python3
"""Tests voor opdracht 3, stap 2: stateful firewall (IPv4 + IPv6) en gastisolatie.

Start IPV6_Topo_opdracht3_fw.py, voert de tests uit en stopt het netwerk weer.
Draaien op de Mininet-VM, in dezelfde map als IPV6_Topo_opdracht3_fw.py, met
IPV6_Topo_opdracht3_fw.yml actief als /etc/faucet/faucet.yaml:

    sudo python3 test_ipv6_stap2.py --controller-ip 10.24.20.8

Beleid (voor IPv4 en IPv6 hetzelfde):
  employee   -> employee, ISP            (niet guest, niet management)
  guest      -> eigen gateway, ISP        (niets intern, ook geen andere guests)
  management -> employee, management, ISP (niet guest)
  ISP        -> niets nieuw naar binnen   (alleen antwoorden; ping naar Faucet zelf mag)
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
import IPV6_Topo_opdracht3_fw as topo  # noqa: E402

RESULTS = []
EVIDENCE = {}


def ping(net, src, dst_ip, count=5, family=4):
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
    print("[%s] %-14s %-60s verwacht=%-11s resultaat=%-11s %s" % (
        "PASS" if passed else "FAIL", group, name,
        "werkt" if ok_expected else "geblokkeerd",
        "werkt" if ok_actual else "geblokkeerd", detail), flush=True)


def ping_test(net, group, src, dst_ip, expect_ok, label, family=6):
    loss, _ = ping(net, src, dst_ip, family=family)
    record(group, "%s -> %s (%s)" % (src, label, dst_ip), expect_ok, loss < 100,
           "%d%% loss" % loss)


def kind_of(name):
    return "isp" if name.startswith("isp_") else name.split("_")[1]


def addr(name, family):
    """Vast IPv4- of IPv6-adres van een host of ISP-router."""
    if name.startswith("isp_"):
        return topo.isp_ip(name, family)
    prefix, kind = name.split("_")
    number = dict((p, n) for p, _sw, n in topo.FLOORS)[prefix]
    if family == 6:
        return topo.host_ip6(kind, number)
    return "%s.%d" % (topo.VLANS[kind]["net4"], number)


def allowed(src, dst):
    """Mag src een NIEUWE verbinding naar dst starten? (beleid van de firewall)"""
    s, d = kind_of(src), kind_of(dst)
    if s == "isp":
        return False                 # van buiten: niets nieuws naar binnen
    if d == "isp":
        return True                  # iedereen binnen mag naar de ISP
    if s == "emp":
        return d == "emp"
    if s == "gst":
        return False                 # geen intern verkeer, ook niet naar andere guests
    if s == "mgt":
        return d in ("emp", "mgt")
    return False


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


def matrix(net, nodes, family):
    """Alle nodes pingen alle andere (per bron parallel). Geeft {(src, dst): bereikt}."""
    reached = {}
    for src in nodes:
        dsts = [d for d in nodes if d != src]
        cmd = " ".join(
            "(ping -%d -n -c 3 -i 0.3 -W 1 %s >/dev/null 2>&1 && echo OK %s || echo NO %s) &"
            % (family, addr(d, family), d, d) for d in dsts) + " wait"
        out = net[src].cmd(cmd)
        for d in dsts:
            reached[(src, d)] = ("OK %s" % d) in out
    # Mag-wel-paren die faalden nog één keer proberen (eerste contact / neighbor discovery).
    for (src, d), ok in list(reached.items()):
        if not ok and allowed(src, d):
            reached[(src, d)] = ping(net, src, addr(d, family), count=5, family=family)[0] < 100
    return reached


def check_matrix(net, nodes, family):
    reached = matrix(net, nodes, family)
    wrong = ["%s->%s (%s)" % (s, d, "bereikt" if ok else "niet bereikt")
             for (s, d), ok in sorted(reached.items()) if ok != allowed(s, d)]
    n_ok = sum(1 for v in reached.values() if v)
    n_exp = sum(1 for (s, d) in reached if allowed(s, d))
    EVIDENCE["matrix_v%d_afwijkingen" % family] = wrong
    EVIDENCE["matrix_v%d" % family] = {"%s->%s" % k: v for k, v in sorted(reached.items())}
    record("2-matrix-v%d" % family, "IPv%d beleid alle-naar-alle (%d paren)" % (family, len(reached)),
           True, not wrong, "%d bereikt, verwacht %d, %d afwijkingen" % (n_ok, n_exp, len(wrong)))


def http_test(net, group, client, server, server_ip, expect_ok, family=6, port=8000):
    net[server].cmd("python3 -m http.server %d --bind %s >/dev/null 2>&1 &" % (port, server_ip))
    time.sleep(1.0)
    url = "http://[%s]:%d/" % (server_ip, port) if family == 6 else "http://%s:%d/" % (server_ip, port)
    out = net[client].cmd("wget -q -O - -T 3 -t 1 '%s' >/dev/null 2>&1; echo rc=$?" % url)
    net[server].cmd("pkill -f 'http.server %d' ; true" % port)
    rc = re.search(r"rc=(\d+)", out)
    ok = rc is not None and rc.group(1) == "0"
    record(group, "TCP %s -> %s:%d (%s)" % (client, server, port, server_ip), expect_ok, ok,
           "wget rc=%s" % (rc.group(1) if rc else "?"))


def iperf_rate(net, client, server, server_ip, seconds=8):
    net[server].cmd("iperf3 -s -1 -p 5201 >/dev/null 2>&1 &")
    time.sleep(1)
    out = net[client].cmd("iperf3 -6 -c %s -p 5201 -t %d -J 2>&1" % (server_ip, seconds))
    try:
        end = json.loads(out[out.index("{"):])["end"]
        return end["sum_received"]["bits_per_second"] / 1e6
    except (ValueError, KeyError):
        return 0.0


def link_local(net, name):
    out = net[name].cmd("ip -6 -o addr show dev %s-eth0 scope link" % name)
    m = re.search(r"inet6 (fe80::[0-9a-f:]+)/64", out)
    return m.group(1) if m else None


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
        nodes = hosts + ["isp_a", "isp_b"]

        # 1. Elke host bereikt zijn eigen gateway, IPv4 en IPv6.
        for name in hosts:
            kind = name.split("_")[1]
            ping_test(net, "1-gateway", name, topo.gw4(kind), True, "IPv4-gateway", family=4)
            ping_test(net, "1-gateway", name, topo.gw6(kind), True, "IPv6-gateway", family=6)

        # 2. Volledige beleidsmatrix, IPv6 en IPv4.
        check_matrix(net, nodes, 6)
        check_matrix(net, nodes, 4)

        # 3. Gastisolatie: ook niet via link-local, multicast, ARP of ND.
        ll = link_local(net, "a2_gst")
        EVIDENCE["link_local_a2_gst"] = ll
        ping_test(net, "3-gastisolatie", "a1_gst", "%s%%a1_gst-eth0" % ll, False,
                  "a2_gst via link-local")
        out = net["a1_gst"].cmd("ping -6 -n -c 3 -W 1 ff02::1%a1_gst-eth0")
        own = link_local(net, "a1_gst")
        others = sorted(set(re.findall(r"from (fe80::[0-9a-f:]+)", out)) - {own})
        EVIDENCE["guest_multicast_replies"] = others
        record("3-gastisolatie", "a1_gst ping ff02::1: antwoord van andere guests", False,
               bool(others), ", ".join(others) or "geen antwoorden van andere guests")
        net["a1_gst"].cmd("ping -4 -c 2 -W 1 10.0.200.21; ping -6 -c 2 -W 1 2001:db8:a:200::21")
        n4 = net["a1_gst"].cmd("ip neigh show 10.0.200.21").strip()
        n6 = net["a1_gst"].cmd("ip -6 neigh show 2001:db8:a:200::21").strip()
        EVIDENCE["guest_neigh_b1_gst"] = {"ipv4": n4, "ipv6": n6}
        record("3-gastisolatie", "a1_gst leert MAC van b1_gst (ARP/ND)", False,
               "REACHABLE" in n4 or "REACHABLE" in n6 or "STALE" in n4 or "STALE" in n6,
               "ARP: %s | ND: %s" % (n4 or "-", n6 or "-"))

        # 4. Stateful: TCP alleen als de verbinding binnen is gestart.
        http_test(net, "4-tcp", "a1_emp", "isp_a", addr("isp_a", 6), True)
        http_test(net, "4-tcp", "b2_gst", "isp_b", addr("isp_b", 6), True)
        http_test(net, "4-tcp", "a1_mgt", "b1_emp", addr("b1_emp", 6), True)
        http_test(net, "4-tcp", "b1_emp", "a1_mgt", addr("a1_mgt", 6), False)
        http_test(net, "4-tcp", "isp_a", "a1_emp", addr("a1_emp", 6), False)
        http_test(net, "4-tcp", "isp_b", "b3_mgt", addr("b3_mgt", 6), False)
        http_test(net, "4-tcp", "a1_gst", "b2_gst", addr("b2_gst", 6), False)

        # 5. Van buiten: alleen ping naar Faucet zelf.
        ping_test(net, "5-van-buiten", "isp_a", topo.FAUCET_PUBLIC6, True, "Faucet ::2")
        ping_test(net, "5-van-buiten", "isp_b", topo.FAUCET_PUBLIC, True, "Faucet .2", family=4)

        # Bewijs: conntrack-regels voor IPv6 (zone 10).
        net["a1_mgt"].cmd("ping -6 -c 1 -W 1 %s" % addr("b1_emp", 6))
        ct = net["a_f1"].cmd("ovs-appctl dpctl/dump-conntrack zone=10 | grep -i icmpv6 | head -8")
        EVIDENCE["conntrack_v6"] = ct.strip()
        record("5-van-buiten", "conntrack bevat IPv6-verbindingen (zone 10)", True,
               "2001:db8:a:" in ct, "%d regels" % len([l for l in ct.splitlines() if l.strip()]))

        # 6. Port security ook voor IPv6.
        #    'ip link set ... address' wijzigt het MAC zonder de interface uit te
        #    zetten. (Mininets setMAC zet hem down/up; Linux gooit dan het vaste
        #    IPv6-adres en de route weg en de test zou niets bewijzen.)
        mgt = net["a1_mgt"]
        intf = mgt.defaultIntf().name
        mgt.cmd("ip link set dev %s address 02:00:00:00:30:99; ip -6 neigh flush dev %s" % (intf, intf))
        EVIDENCE["a1_mgt_vals_mac_addr6"] = mgt.cmd("ip -6 -o addr show dev %s scope global" % intf).strip()
        loss, _ = ping(net, "a1_mgt", topo.gw6("mgt"), family=6)
        record("6-port-security", "a1_mgt met vals MAC -> IPv6-gateway", False, loss < 100,
               "%d%% loss (IPv6-adres nog aanwezig: %s)" % (
                   loss, "ja" if "2001:db8:a:300::11" in EVIDENCE["a1_mgt_vals_mac_addr6"] else "NEE"))
        mgt.cmd("ip link set dev %s address 02:00:00:00:30:11; ip -6 neigh flush dev %s" % (intf, intf))
        time.sleep(1)
        loss, _ = ping(net, "a1_mgt", topo.gw6("mgt"), family=6)
        record("6-port-security", "a1_mgt met juist MAC -> IPv6-gateway", True, loss < 100,
               "%d%% loss" % loss)

        # 7. Rate limiting ook voor IPv6-guestverkeer.
        gst = iperf_rate(net, "a1_gst", "isp_a", addr("isp_a", 6))
        emp = iperf_rate(net, "a1_emp", "isp_a", addr("isp_a", 6))
        record("7-ratelimit", "a1_gst -> isp_a via IPv6 <= 1.2 Mbit/s", True, 0 < gst <= 1.2,
               "%.2f Mbit/s" % gst)
        record("7-ratelimit", "a1_emp -> isp_a via IPv6 > 5 Mbit/s", True, emp > 5,
               "%.2f Mbit/s" % emp)

        sw = net["a_f1"]
        EVIDENCE["flows_a_f1_table0_ipv6"] = sw.cmd(
            "ovs-ofctl -O OpenFlow13 --names --no-stats dump-flows a_f1 table=0 | grep -E 'ipv6|icmp6'").strip()
        EVIDENCE["meter_stats_a_f1"] = sw.cmd("ovs-ofctl -O OpenFlow13 meter-stats a_f1").strip()
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
    parser.add_argument("--out", default="/tmp/test_ipv6_stap2.json")
    args = parser.parse_args()
    setLogLevel("warning")
    run(args.controller_ip, args.out)
