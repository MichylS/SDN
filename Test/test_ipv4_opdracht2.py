#!/usr/bin/env python3
"""Automatische tests voor IPV4_Topo_opdracht2.py + IPV4_Topo_opdracht2.yml.

Start de topologie, voert alle tests uit en schrijft de resultaten naar
stdout en naar een JSON-bestand. Draaien op de Mininet-VM:

    sudo python3 test_ipv4_opdracht2.py --controller-ip 10.24.20.8

Met --zonder-fw verwacht het script de variant zonder firewall
(IPV4_Topo_opdracht2_zonder_fw.yml): verkeer tussen de interne VLAN's werkt
dan overal; NAT, port security, rate limit en "van buiten dicht" blijven gelijk.

Er is geen host "internet": de ISP-routers isp_a (198.51.100.1) en isp_b
(198.51.100.3) zijn het eindpunt buiten Faucet.
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
import IPV4_Topo_opdracht2 as topo  # noqa: E402

RESULTS = []
EVIDENCE = {}

ISP_A = topo.isp_ip("isp_a")   # 198.51.100.1
ISP_B = topo.isp_ip("isp_b")   # 198.51.100.3


def ip_of(net, name):
    return net[name].IP()


def ping(net, src, dst_ip, count=3):
    out = net[src].cmd("ping -n -c %d -W 1 -i 0.3 %s" % (count, dst_ip))
    m = re.search(r"([\d.]+)% packet loss", out)
    loss = round(float(m.group(1))) if m else 100
    return loss, out


def record(group, name, ok_expected, ok_actual, detail=""):
    passed = ok_expected == ok_actual
    RESULTS.append({
        "group": group, "test": name,
        "expected": "werkt" if ok_expected else "geblokkeerd",
        "actual": "werkt" if ok_actual else "geblokkeerd",
        "pass": passed, "detail": detail,
    })
    print("[%s] %-14s %-55s verwacht=%-11s resultaat=%-11s %s" % (
        "PASS" if passed else "FAIL", group, name,
        "werkt" if ok_expected else "geblokkeerd",
        "werkt" if ok_actual else "geblokkeerd", detail), flush=True)


def ping_test(net, group, src, dst, expect_ok, dst_label=None):
    dst_ip = dst if re.match(r"^\d+\.\d+\.\d+\.\d+$", dst) else ip_of(net, dst)
    loss, _ = ping(net, src, dst_ip)
    ok = loss < 100
    record(group, "%s -> %s (%s)" % (src, dst_label or dst, dst_ip), expect_ok, ok,
           "%d%% loss" % loss)


# Alle uiteinden van de stack-links: (switch, poort).
STACK_PORTS = ({("a_core", "1"), ("a_core", "2"), ("a_core", "3"),
                ("b_core", "1"), ("b_core", "2"), ("b_core", "3"), ("b_core", "4")}
               | {(sw, "1") for _prefix, sw, _nr in topo.FLOORS})


def stack_up(controller_ip):
    """True als Faucet (Prometheus, poort 9302) alle stackpoorten als UP (3) meldt."""
    try:
        text = urllib.request.urlopen("http://%s:9302/" % controller_ip, timeout=3).read().decode()
    except OSError:
        return None
    up = {(m.group(1), m.group(2)) for m in re.finditer(
        r'^port_stack_state\{[^}]*dp_name="([^"]+)",port="(\d+)"[^}]*\} ([\d.\-]+)$', text, re.M)
        if float(m.group(3)) == 3.0}
    return STACK_PORTS <= up


def wait_for_network(net, controller_ip, timeout=90):
    """Wacht tot alle stackpoorten UP zijn en daarna tot de gateways antwoorden.

    Zolang de stack nog opkomt, herconfigureert Faucet bij elke poortovergang
    de VLAN's en vergeet het geleerde hosts; tests in die periode zijn onbetrouwbaar.
    """
    start = time.time()
    seen_down = False   # metrics kunnen nog de UP-status van een vorige run tonen
    while time.time() - start < timeout:
        state = stack_up(controller_ip)
        if state is None:          # metrics niet bereikbaar: ruime vaste wachttijd
            time.sleep(12)
            break
        if not state:
            seen_down = True
        elif seen_down or time.time() - start > 15:
            break
        time.sleep(1)
    EVIDENCE["stack_up_sec"] = round(time.time() - start, 1)
    probes = [("a1_emp", "10.0.100.1"), ("b3_emp", "10.0.100.1"),
              ("b2_mgt", "10.0.30.1"), ("a2_gst", "10.0.200.1"),
              ("isp_a", "198.51.100.2"), ("isp_b", "198.51.100.2")]
    while time.time() - start < timeout:
        ok = all(ping(net, h, ip, count=1)[0] == 0 for h, ip in probes)
        if ok:
            return time.time() - start
        time.sleep(3)
    return None


def http_test(net, group, client, server, server_ip, expect_ok, port=8000):
    net[server].cmd("python3 -m http.server %d --bind %s >/dev/null 2>&1 &" % (port, server_ip))
    time.sleep(1.0)
    out = net[client].cmd("wget -q -O - -T 3 -t 1 http://%s:%d/ >/dev/null 2>&1; echo rc=$?"
                          % (server_ip, port))
    net[server].cmd("pkill -f 'http.server %d' ; true" % port)
    rc = re.search(r"rc=(\d+)", out)
    ok = rc is not None and rc.group(1) == "0"
    record(group, "TCP %s -> %s:%d (%s)" % (client, server, port, server_ip), expect_ok, ok,
           "wget rc=%s" % (rc.group(1) if rc else "?"))


def iperf_rate(net, client, server, server_ip, seconds=10):
    """Meet met iperf3 de snelheid aan de ontvangende kant (sum_received)."""
    net[server].cmd("iperf3 -s -1 -p 5201 >/dev/null 2>&1 &")
    time.sleep(1)
    out = net[client].cmd("iperf3 -c %s -p 5201 -t %d -J 2>&1" % (server_ip, seconds))
    try:
        end = json.loads(out[out.index("{"):])["end"]
        rate = end["sum_received"]["bits_per_second"] / 1e6
        sent = end["sum_sent"]["bits_per_second"] / 1e6
        summary = "ontvangen %.2f Mbit/s, verzonden %.2f Mbit/s, retransmits %s" % (
            rate, sent, end["sum_sent"].get("retransmits", "?"))
    except (ValueError, KeyError):
        rate, summary = 0.0, out[-800:]
    return rate, summary


def run(controller_ip, outfile, zonder_fw=False):
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

        # 1. Elke host bereikt zijn eigen gateway (Faucet-VIP).
        for prefix, _sw, _nr in topo.FLOORS:
            for kind in topo.VLANS:
                ping_test(net, "1-gateway", "%s_%s" % (prefix, kind), topo.gw4(kind), True,
                          "gateway")

        # 2. Zelfde VLAN, ook tussen gebouwen (laag 2 via de stack).
        ping_test(net, "2-zelfde-vlan", "a1_emp", "a2_emp", True)
        ping_test(net, "2-zelfde-vlan", "a1_emp", "b3_emp", True)
        ping_test(net, "2-zelfde-vlan", "a1_mgt", "b2_mgt", True)

        # Tests die alleen door de firewall geblokkeerd worden: zonder firewall werken ze.
        fw_blokkeert = zonder_fw
        EVIDENCE["variant"] = "zonder firewall" if zonder_fw else "met firewall"

        # 3. Tussen VLAN's (firewallbeleid).
        ping_test(net, "3-tussen-vlan", "a1_mgt", "b1_emp", True)
        ping_test(net, "3-tussen-vlan", "b3_mgt", "a2_emp", True)
        ping_test(net, "3-tussen-vlan", "a1_emp", "a1_mgt", fw_blokkeert)
        ping_test(net, "3-tussen-vlan", "b2_emp", "a2_mgt", fw_blokkeert)
        ping_test(net, "3-tussen-vlan", "a1_emp", "b2_gst", fw_blokkeert)
        ping_test(net, "3-tussen-vlan", "b1_mgt", "a1_gst", fw_blokkeert)
        ping_test(net, "3-tussen-vlan", "a2_gst", "a1_emp", fw_blokkeert)
        ping_test(net, "3-tussen-vlan", "b3_gst", "b3_mgt", fw_blokkeert)

        # 4. Gastisolatie: guests zien elkaar niet.
        ping_test(net, "4-gastisolatie", "a1_gst", "a2_gst", fw_blokkeert)
        ping_test(net, "4-gastisolatie", "a1_gst", "b1_gst", fw_blokkeert)
        ping_test(net, "4-gastisolatie", "b2_gst", "b3_gst", fw_blokkeert)

        # 5. ISP-routers bereikbaar (via Faucet-routering en NAT in Faucet).
        for host, isp in (("a1_emp", "isp_a"), ("b2_emp", "isp_b"), ("a2_gst", "isp_a"),
                          ("b3_gst", "isp_b"), ("a1_mgt", "isp_a"), ("b1_mgt", "isp_b")):
            ping_test(net, "5-isp", host, topo.isp_ip(isp), True, isp)

        # 6. NAT in Faucet: isp_a ziet alleen het NAT-adres, nooit 10.x.
        isp_a = net["isp_a"]
        isp_a.cmd("rm -f /tmp/nat.txt; tcpdump -n -l -i isp_a-eth0 -c 8 icmp "
                  "> /tmp/nat.txt 2>/dev/null &")
        time.sleep(1.5)
        ping(net, "a1_emp", ISP_A, count=2)
        ping(net, "b3_gst", ISP_A, count=2)
        time.sleep(1.5)
        isp_a.cmd("pkill -f 'tcpdump -n -l -i isp_a-eth0' ; true")
        capture = isp_a.cmd("cat /tmp/nat.txt")
        EVIDENCE["nat_tcpdump_isp_a_eth0"] = capture.strip()
        nat_ok = (capture.count("%s > %s" % (topo.NAT_IP, ISP_A)) >= 2
                  and not re.search(r"\b10\.\d+\.\d+\.\d+", capture))
        record("6-nat", "bron op isp_a-eth0 = %s (a1_emp en b3_gst)" % topo.NAT_IP, True,
               nat_ok, "zie tcpdump in rapport")

        # De vertaling staat in de conntrack-tabel van Faucet (zone 10).
        ct = net["a_f1"].cmd("ovs-appctl dpctl/dump-conntrack zone=10")
        ct_nat = [l for l in ct.splitlines()
                  if "src=10.0.100.11,dst=%s," % ISP_A in l and "dst=%s," % topo.NAT_IP in l]
        EVIDENCE["conntrack_nat_a1_emp"] = "\n".join(ct_nat[:3])
        record("6-nat", "conntrack: 10.0.100.11 -> %s, antwoord naar %s" % (ISP_A, topo.NAT_IP),
               True, bool(ct_nat), "%d NAT-verbinding(en)" % len(ct_nat))

        # De ISP-routers doen zelf geen NAT meer.
        isp_nat = {r: net[r].cmd("iptables -t nat -S POSTROUTING") for r in ("isp_a", "isp_b")}
        EVIDENCE["iptables_nat_isp"] = "\n".join(
            "%s: %s" % (r, v.strip() or "(leeg)") for r, v in isp_nat.items())
        record("6-nat", "isp_a en isp_b hebben geen SNAT/MASQUERADE-regels", True,
               not any(re.search(r"SNAT|MASQUERADE", v) for v in isp_nat.values()),
               "iptables -t nat leeg")

        # 7. Stateful: van buiten mag niets nieuws naar binnen. Een ISP routeert
        #    normaal geen 10.x; voor deze test zetten we die route tijdelijk op
        #    isp_a/isp_b (aanvaller in het ISP-segment), zodat de firewall het
        #    verkeer moet tegenhouden en niet de ontbrekende route.
        for r in ("isp_a", "isp_b"):
            net[r].cmd("ip route replace 10.0.0.0/8 via %s" % topo.FAUCET_PUBLIC)
        ping_test(net, "7-van-buiten", "isp_a", "a1_emp", False)
        ping_test(net, "7-van-buiten", "isp_b", "b1_mgt", False)
        ping_test(net, "7-van-buiten", "isp_a", "a2_gst", False)
        ping_test(net, "7-van-buiten", "isp_a", "198.51.100.2", True, "Faucet-VIP")
        ping_test(net, "7-van-buiten", "isp_a", topo.NAT_IP, False, "NAT-adres")
        ping_test(net, "7-van-buiten", "isp_b", topo.NAT_IP, False, "NAT-adres")

        # 8. TCP (stateful, met handshake).
        http_test(net, "8-tcp", "a1_emp", "isp_a", ISP_A, True)
        http_test(net, "8-tcp", "b2_gst", "isp_b", ISP_B, True)
        http_test(net, "8-tcp", "a1_mgt", "b1_emp", ip_of(net, "b1_emp"), True)
        http_test(net, "8-tcp", "b1_emp", "a1_mgt", ip_of(net, "a1_mgt"), fw_blokkeert)
        http_test(net, "8-tcp", "a2_gst", "a2_emp", ip_of(net, "a2_emp"), fw_blokkeert)
        http_test(net, "8-tcp", "isp_a", "a1_emp", ip_of(net, "a1_emp"), False)
        for r in ("isp_a", "isp_b"):
            net[r].cmd("ip route del 10.0.0.0/8 ; true")

        # 9. Port security: ander MAC-adres op een managementpoort wordt gedropt.
        mgt = net["a1_mgt"]
        intf = mgt.defaultIntf()
        mgt.setMAC("02:00:00:00:30:99", intf)
        loss, _ = ping(net, "a1_mgt", "10.0.30.1")
        record("9-port-security", "a1_mgt met vals MAC 02:00:00:00:30:99 -> gateway", False,
               loss < 100, "%d%% loss" % loss)
        mgt.setMAC("02:00:00:00:30:11", intf)
        time.sleep(1)
        loss, _ = ping(net, "a1_mgt", "10.0.30.1")
        record("9-port-security", "a1_mgt met juist MAC 02:00:00:00:30:11 -> gateway", True,
               loss < 100, "%d%% loss" % loss)

        # 10. Rate limiting: guest max ~1 Mbit/s, employee niet beperkt.
        gst_rate, gst_out = iperf_rate(net, "a1_gst", "isp_a", ISP_A)
        emp_rate, emp_out = iperf_rate(net, "a1_emp", "isp_a", ISP_A)
        EVIDENCE["iperf_guest"] = gst_out.strip()
        EVIDENCE["iperf_employee"] = emp_out.strip()
        record("10-ratelimit", "a1_gst -> isp_a <= 1.2 Mbit/s (meter 1 Mbit/s)", True,
               0 < gst_rate <= 1.2, "%.2f Mbit/s" % gst_rate)
        record("10-ratelimit", "a1_emp -> isp_a > 5 Mbit/s (geen limiet)", True,
               emp_rate > 5, "%.2f Mbit/s" % emp_rate)

        # Bewijs uit de switches en conntrack.
        sw = net["a_f1"]
        EVIDENCE["flows_a_f1_ct"] = sw.cmd(
            "ovs-ofctl -O OpenFlow13 dump-flows a_f1 table=0 | grep -E 'ct_state|ct\\(' "
            "| sed -E 's/ *duration=[^,]*,//; s/ *idle_age=[^,]*,//'").strip()
        EVIDENCE["meter_stats_a_f1"] = sw.cmd("ovs-ofctl -O OpenFlow13 meter-stats a_f1").strip()
        EVIDENCE["conntrack_zone10"] = sw.cmd(
            "ovs-appctl dpctl/dump-conntrack zone=10 | head -25").strip()
        EVIDENCE["routes_isp_a"] = net["isp_a"].cmd("ip route").strip()
        EVIDENCE["routes_isp_b"] = net["isp_b"].cmd("ip route").strip()
    finally:
        net.stop()

    summary = {
        "totaal": len(RESULTS),
        "geslaagd": sum(1 for r in RESULTS if r["pass"]),
        "mislukt": sum(1 for r in RESULTS if not r["pass"]),
    }
    with open(outfile, "w") as f:
        json.dump({"summary": summary, "results": RESULTS, "evidence": EVIDENCE}, f, indent=2)
    print("\nSamenvatting: %(geslaagd)d/%(totaal)d geslaagd, %(mislukt)d mislukt" % summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--controller-ip", required=True)
    parser.add_argument("--out", default="/tmp/test_ipv4_opdracht2.json")
    parser.add_argument("--zonder-fw", action="store_true",
                        help="verwachtingen voor IPV4_Topo_opdracht2_zonder_fw.yml")
    args = parser.parse_args()
    setLogLevel("warning")
    run(args.controller_ip, args.out, args.zonder_fw)
