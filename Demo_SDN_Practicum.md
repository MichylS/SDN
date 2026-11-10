# Live demo SDN-practicum

Draaiboek voor de live demo. Per test staat erbij **wat je typt**, **wat je moet zien** en **wat je ermee aantoont**. Alle Mininet-commando's typ je op de prompt `mininet>`.

Adressen om bij de hand te hebben:

| Wat | IPv4 | IPv6 |
|---|---|---|
| Employee (VLAN 100) | 10.0.100.0/23, gw .254, hosts .11 .12 .21 .22 .23 | 2001:db8:100::/64, gw ::1 |
| Guest (VLAN 200) | 10.0.200.0/24, gw .254 | 2001:db8:200::/64, gw ::1 |
| Management (VLAN 300) | 10.0.30.0/24, gw .254 | 2001:db8:300::/64, gw ::1 |
| ISP | isp_a 198.51.100.1, natgw 198.51.100.2, isp_b 198.51.100.3 | 2001:db8:ffff::1 / ::2 / ::3 |

Hostnummers: a1 = .11, a2 = .12, b1 = .21, b2 = .22, b3 = .23 (dus `b3_emp` = 10.0.100.23).

---

## 0. Voorbereiding (vóór de demo)

```bash
# Op de Faucet-VM: controleren dat Faucet draait en de config geldig is
sudo systemctl status faucet
check_faucet_config /etc/faucet/faucet.yaml

# Op de Mininet-VM: oude resten opruimen en topologie starten
sudo mn -c
sudo python3 ~/sdn-opdracht2/topology/buildings_topology.py --controller-ip 10.24.20.8
```

Daarna in Mininet:

```text
mininet> net
mininet> sh ovs-vsctl show
```

**Doel:** laten zien dat alle 7 Faucet-switches (a_core, a_f1, a_f2, b_core, b_f1–b_f3) en isp_net bestaan, en dat de Faucet-switches `is_connected: true` hebben bij hun controller. Zonder controllerverbinding staan de switches in `failMode=secure` en sturen ze niets door.

> Tip: draai voor de demo één keer `pingall` niet. Door de ACL's en de firewall faalt een groot deel bewust, en dat is verwarrend om live te laten zien. Gebruik de gerichte tests hieronder.

---

## 1. Basisconnectiviteit en VLAN's over de darkfiber

```text
mininet> a1_emp ping -c 3 10.0.100.254
mininet> a1_emp ping -c 3 10.0.100.23
mininet> a1_mgt ping -c 3 10.0.30.23
```

| Test | Verwacht | Wat het aantoont |
|---|---|---|
| a1_emp → eigen gateway | 0% loss | Host bereikt natgw via de trunk op a_core poort 4 (router-on-a-stick). |
| a1_emp (gebouw A) → b3_emp (gebouw B) | 0% loss | VLAN 100 loopt getagd over core → darkfiber → b_core → b_f3. Zelfde VLAN = laag 2, dus geen router nodig. |
| a1_mgt → b3_mgt | 0% loss | Ook het management-VLAN is in beide gebouwen beschikbaar. |

---

## 2. Segmentatie: netwerken zijn gescheiden

```text
mininet> a1_emp ping -c 3 -W1 10.0.200.11
mininet> a1_emp ping -c 3 -W1 10.0.30.11
mininet> a1_gst ping -c 3 -W1 10.0.100.11
mininet> a1_gst ping -c 3 -W1 10.0.30.11
mininet> a1_gst ping -c 3 -W1 10.0.200.12
mininet> a1_mgt ping -c 3 10.0.100.11
```

| Test | Verwacht | Waar wordt het tegengehouden / waarom |
|---|---|---|
| employee → guest | 100% loss | `office-acl` op de switchpoort (tabel 0) dropt verkeer naar 10.0.200.0/24. |
| employee → management | 100% loss | Gaat via natgw; de FORWARD-policy DROP staat geen NEW employee → management toe. |
| guest → employee | 100% loss | `guest-acl` dropt naar 10.0.100.0/23. |
| guest → management | 100% loss | `guest-acl` dropt naar 10.0.30.0/24. |
| guest → andere guest | 100% loss | Gastisolatie: gasten mogen elkaar niet zien (ook niet via natgw, hairpin wordt gedropt). |
| management → employee | 0% loss | Bewuste uitzondering: beheer mag naar werkplekken. Het antwoord komt terug door conntrack (ESTABLISHED). |

**Doel:** aantonen dat segmentatie op twee niveaus werkt: op de **switch** (Faucet-ACL's) en op de **gateway** (stateful firewall). De laatste test laat zien dat het geen "alles dicht"-oplossing is maar gericht beleid.

---

## 3. Internet / ISP en NAT (het /28-probleem)

```text
mininet> a1_emp ping -c 3 198.51.100.1
mininet> a1_gst ping -c 3 198.51.100.1
mininet> b3_mgt ping -c 3 198.51.100.1
mininet> a1_emp traceroute -n 198.51.100.1
mininet> natgw iptables -t nat -L POSTROUTING -n -v
```

**Verwacht:** alle drie de VLAN's bereiken de ISP (TTL 63 = één router ertussen). Traceroute: eerste hop 10.0.100.254 (natgw), daarna 198.51.100.1. De SNAT-teller in POSTROUTING loopt op.

**Doel:** aantonen dat alle interne gebruikers via **één publiek adres (198.51.100.2) met PAT** naar buiten gaan. Zo is het /28 (14 bruikbare adressen) genoeg voor 500+ gebruikers en blijven er adressen over voor servers. `b3_mgt` laat zien dat gebouw B via de darkfiber dezelfde uplink gebruikt.

### 3b. PAT zichtbaar maken met tcpdump

```text
mininet> natgw tcpdump -nei natgw-eth0 -c 6 icmp > /tmp/t_vlan.txt 2>&1 &
mininet> natgw tcpdump -ni natgw-eth1 -c 6 icmp > /tmp/t_nat.txt 2>&1 &
mininet> a1_gst ping -c 3 198.51.100.1
mininet> sh cat /tmp/t_vlan.txt
mininet> sh cat /tmp/t_nat.txt
```

**Verwacht:** binnenkant (`natgw-eth0`): frames met `802.1Q vlan 200`, bron 10.0.200.11. Buitenkant (`natgw-eth1`): geen VLAN-tag, bron **198.51.100.2**.

**Doel:** de vertaling live laten zien: het privé-adres verdwijnt aan de buitenkant. Tegelijk bewijst het dat de VLAN-tag over de trunk tot aan natgw meekomt.

---

## 4. Stateful firewall: ISP mag niet naar binnen

```text
mininet> isp_a ip route add 10.0.100.0/23 via 198.51.100.2
mininet> isp_a traceroute -n -w1 10.0.100.11
mininet> isp_a ping6 -c 3 -W1 2001:db8:100::11
mininet> natgw iptables -L FORWARD -n -v
mininet> natgw ip6tables -L FORWARD -n -v
```

**Verwacht:** traceroute toont hop 1 = 198.51.100.2 (natgw), daarna alleen `* * *`. De ping6 geeft 100% loss. In de FORWARD-chains zie je policy DROP en een groeiende ESTABLISHED,RELATED-teller (van de pings uit stap 3).

**Doel:** aantonen dat de firewall **stateful** is: van binnen naar buiten mag (NEW), het antwoord komt terug (ESTABLISHED), maar een nieuwe verbinding van buiten naar binnen wordt gedropt. Bij IPv6 is er geen NAT, dus deze test laat zien dat de firewall (en niet de NAT) de bescherming geeft.

> Uitleg waarom op natgw: OpenFlow 1.3 / Faucet kent geen connection tracking. Een stateless ACL kan niet zien of een pakket een antwoord is.

---

## 5. IPv6

```text
mininet> a1_emp ping6 -c 3 2001:db8:100::1
mininet> a1_emp ping6 -c 3 2001:db8:ffff::1
mininet> a1_gst ping6 -c 3 2001:db8:ffff::1
mininet> a1_mgt ping6 -c 3 2001:db8:100::11
mininet> a1_emp ping6 -c 3 -W1 2001:db8:300::11
mininet> a1_gst ping6 -c 3 -W1 2001:db8:200::12
```

| Test | Verwacht | Aantoont |
|---|---|---|
| employee → eigen IPv6-gateway | 0% loss | Elk VLAN heeft een eigen /64 met natgw op ::1. |
| employee / guest → ISP via IPv6 | 0% loss | IPv6 wordt gerouteerd zonder NAT (dual stack). |
| management → employee (IPv6) | 0% loss | Hetzelfde beleid als bij IPv4. |
| employee → management (IPv6) | 100% loss | ip6tables blokkeert dit net als iptables. |
| guest → guest (IPv6) | 100% loss | De gast-ACL heeft ook IPv6-regels. |

**Doel:** aantonen dat het netwerk volledig dual stack is en dat **elk beleid ook voor IPv6 geldt** (een veelgemaakte fout is alleen IPv4 dichtzetten).

---

## 6. NFV 1: rate limiting gastennetwerk

```text
mininet> iperf a1_gst isp_a
mininet> iperf a1_emp isp_a
mininet> sh ovs-ofctl -O OpenFlow13 dump-meters a_f1
mininet> sh ovs-ofctl -O OpenFlow13 meter-stats a_f1
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 table=0 | grep meter
```

**Verwacht:** gast ≈ 1–1,5 Mbit/s, werknemer vele Gbit/s. `dump-meters` toont `rate=1000 burst_size=100`, `meter-stats` toont gedropte pakketten, en de flows van poort 3 hebben `actions=meter:1,...`.

**Doel:** aantonen dat de OpenFlow-meter **alleen** het gastverkeer beperkt tot 1 Mbit/s, en dat dit in de switch zelf gebeurt (zichtbaar in de flow table), niet op de host. De Gbit/s van de werknemer is een software-snelheid in Mininet en dient alleen als vergelijking.

---

## 7. NFV 2: port security management-VLAN

```text
mininet> a1_mgt ping -c 3 10.0.30.254
mininet> a1_mgt ip link set a1_mgt-eth0 address 02:00:00:00:99:99
mininet> a1_mgt ping -c 3 -W1 10.0.30.254
mininet> sh ovs-ofctl -O OpenFlow13 --names dump-flows a_f1 table=0 | grep a_f1-eth4
mininet> a1_mgt ip link set a1_mgt-eth0 address 02:00:00:00:30:11
mininet> a1_mgt ping -c 3 10.0.30.254
```

**Verwacht:** eerste ping werkt → na MAC-wijziging 100% loss → in de flow dump loopt de `n_packets` van de drop-regel (`priority=20479 ... actions=drop`) op → na terugzetten werkt de ping weer.

> Let op `--names`: zonder die optie toont `ovs-ofctl` poortnummers (`in_port=4`) zodra de uitvoer door `grep` gaat, en dan vindt `grep a_f1-eth4` niets.

**Doel:** aantonen dat op een managementpoort **alleen het geregistreerde MAC-adres** wordt toegelaten. Iemand die een ander apparaat in de managementpoort prikt, komt er niet in. (Kanttekening die je kunt noemen: MAC-adressen zijn te vervalsen; dit is een eerste drempel, geen volledige authenticatie zoals 802.1X.)

---

## 8. Flow entries uitleggen

```text
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 table=0
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 table=1
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 table=2
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 table=3
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows a_core
```

| Tabel | Functie | Waar op letten |
|---|---|---|
| 0 | Poort-ACL | Match op `in_port`, `dl_type`, `nw_dst` / `dl_src` → `drop`, `meter:1` of `goto_table:1` |
| 1 | VLAN-classificatie | `push_vlan:0x8100,set_field:4296->vlan_vid` (4296 = 0x1000 + 200 → VLAN 200; 4196 = VLAN 100, 4396 = VLAN 300) |
| 2 | Bron-MAC leren | Geleerde MAC's per VLAN/poort |
| 3 | Doorsturen op doel-MAC | `output:` naar de juiste poort |
| 4 | Flooding | Broadcast/onbekend verkeer binnen het VLAN |

**Doel:** laten zien dat je de **matching criteria, acties en tabelverdeling** begrijpt (eis uit de opdracht). Wijs bij voorkeur een regel aan waarvan `n_packets` net is opgelopen door een van je eerdere tests.

---

## 9. Schaalbaarheid: 500 gelijktijdige gebruikers (optioneel, ±30 sec)

```text
mininet> a1_emp bash /home/mininet/sdn-opdracht2/tests/scale_test.sh 500 a1_emp-eth0 198.51.100.1 20 > /tmp/scale_summary.txt 2>&1 &
mininet> natgw cat /proc/sys/net/netfilter/nf_conntrack_count
mininet> natgw iptables -t nat -L POSTROUTING -n -v
mininet> sh cat /tmp/scale_summary.txt
```

Vraag de conntrack-teller op terwijl de test loopt (binnen ±20 sec), en wacht ±25 seconden voordat je de samenvatting opvraagt.

> `conntrack -C` werkt niet: het pakket `conntrack` is niet geïnstalleerd op de VM. Het `/proc`-bestand geeft hetzelfde getal.

**Verwacht:** `Gebruikers met 0% verlies: 500 van 500`, conntrack-teller rond de 500, SNAT-teller +500. (Getest: conntrack 4 → 502, SNAT 24 → 524.)

**Doel:** aantonen dat de /23 genoeg adressen heeft en dat NAT + conntrack 500 gelijktijdige verbindingen via één publiek adres aankunnen. Kanttekening: alle adressen zitten op één host met één MAC, dus het test niet het leren van 500 MAC's door Faucet.

---

## 10. Opdracht 4: VxLAN-overlay (Proxmox)

Gegevens: underlay 10.24.11.0/24 (gebouw A) en 10.24.20.0/24 (gebouw B), VTEP's 10.24.11.10 en 10.24.20.10, zone `vxlan1`, VNet `vnet100`, **VNI 10100**, overlay 172.16.100.0/24, MTU 1450. Test-VM's: 172.16.100.10 (A) en 172.16.100.20 (B).

### 10a. Configuratie laten zien (Proxmox-node)

```bash
cat /etc/pve/sdn/zones.cfg
cat /etc/pve/sdn/vnets.cfg
ip -d link show vxlan_vnet100
```

**Doel:** de VxLAN-parameters tonen: peers-lijst (de vmbr0-adressen van beide nodes), VNI 10100, MTU 1450 en UDP-poort 4789. (Kan ook via de GUI: Datacenter → SDN → Zones / VNets.)

### 10b. Underlay (M1)

```bash
ping -c 3 10.24.20.10        # vanaf de node in gebouw A
```

**Verwacht:** 0% loss. **Doel:** de VTEP's bereiken elkaar via gewone L3-routering. Dit is de voorwaarde voor de tunnel; zonder werkende underlay geen overlay. Er is geen VPN nodig, omdat de netwerken al gerouteerd zijn en UDP 4789 open staat.

### 10c. Overlay-connectiviteit (M2)

```bash
ping -c 4 172.16.100.20      # vanaf VM 172.16.100.10
ip neigh show 172.16.100.20
```

**Verwacht:** 0% loss, en in `ip neigh` staat het MAC van de andere VM. **Doel:** de VM's staan in verschillende netwerken/gebouwen maar zitten in **hetzelfde subnet** en zien elkaar op laag 2 (ARP werkt door de tunnel).

### 10d. MTU-test (M3)

```bash
ping -M do -s 1422 -c 4 172.16.100.20   # moet slagen
ping -M do -s 1423 -c 2 172.16.100.20   # moet falen: "message too long"
```

**Rekensom:** 1500 (underlay) − 50 (20 IP + 8 UDP + 8 VxLAN + 14 binnen-Ethernet) = **1450** overlay-MTU. Payload ping = 1450 − 20 (IP) − 8 (ICMP) = **1422**.

**Doel:** `-M do` zet het Don't-Fragment-bit. Slagen bij 1422 en falen bij 1423 bewijst dat de berekende MTU precies klopt: grotere pakketten zouden na inkapseling niet meer in de 1500 van de underlay passen.

### 10e. Latency en bandbreedte

```bash
ping -c 20 -i 0.2 172.16.100.20       # kijk naar de rtt min/avg/max/mdev-regel
iperf3 -s                              # op VM B (172.16.100.20)
iperf3 -c 172.16.100.20 -t 10          # op VM A
```

**Doel:** naast "het werkt" ook de **kwaliteit** meten: de gemiddelde RTT en jitter (mdev) voor latency, en met iperf3 de haalbare bandbreedte door de tunnel. Je kunt vergelijken met een iperf3 over de underlay om de overhead van VxLAN te laten zien.

---

## Volgorde in het kort (spiekbriefje)

1. `net`, `ovs-vsctl show` → switches verbonden
2. a1_emp → b3_emp → VLAN over darkfiber
3. Segmentatie: emp→gst ✗, gst→gst ✗, gst→emp ✗, mgt→emp ✓
4. ISP-ping + traceroute + SNAT-teller + tcpdump → PAT
5. ISP → binnen ✗ → stateful firewall
6. IPv6 dezelfde tests
7. iperf gast vs werknemer + dump-meters → rate limit
8. MAC wijzigen op a1_mgt → port security
9. Flow tables 0–4 uitleggen
10. (optioneel) 500-gebruikerstest
11. VxLAN: config → underlay-ping → overlay-ping → MTU 1422/1423 → iperf3
