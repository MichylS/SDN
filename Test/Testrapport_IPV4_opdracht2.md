# Testrapport: IPv4-topologie opdracht 2 (Faucet + Mininet)

Datum: 9 november 2026 · Getest op de echte VM's: Faucet-VM `10.24.20.8` (Faucet 1.10.12) en Mininet-VM `10.24.20.22` (Mininet 2.3.0, Open vSwitch 2.13.1, kernel 5.4).

## 1. Samenvatting

| | |
|---|---|curl -s localhost:9302 | grep 'table_names{.*dp_name="a_f1"' | sed -E 's/.*next_tables="([^"]*)",table_name="([^"]*)"} ([0-9]+).*/\3  \2  -> \1/' | sort -n
| **Resultaat** | **54 van de 54 tests geslaagd**, in 4 volledige runs na elkaar (run 7 t/m 10) |
| Wijziging | **Firewall én NAT zitten nu in Faucet `ct`**, zoals je docent vroeg ("FW & NAT -> Faucet CT"). `isp_a` en `isp_b` zijn gewone routers zonder NAT. |
| Topologie | [IPV4_Topo_opdracht2.py](IPV4_Topo_opdracht2.py) |
| Faucet-config | [IPV4_Topo_opdracht2.yml](IPV4_Topo_opdracht2.yml), **nu actief** op de Faucet-VM |
| Zonder firewall | [IPV4_Topo_opdracht2_zonder_fw.yml](IPV4_Topo_opdracht2_zonder_fw.yml), dezelfde config zonder verbodsregels. Je wisselt in ~1 s, terwijl het netwerk blijft draaien (zie hoofdstuk 8). |
| Testscript | [test_ipv4_opdracht2.py](test_ipv4_opdracht2.py), start de topologie, voert alle tests uit en stopt weer |
| Ruwe resultaten | [testresultaten_ipv4_opdracht2/](testresultaten_ipv4_opdracht2/):<br>• na de overstap naar gateway `.1`: `run13_gw1_met_fw.*` en `run14_gw1_zonder_fw.*`;<br>• `run7_nat` t/m `run10_nat` (`.json` + `.log`) en `cli_check_nat.log`;<br>• voor hoofdstuk 8: `run11_zonder_fw.*`, `run12_met_fw.*` en `live_wissel.log`;<br>• `run3.*` en `cli_check.log` zijn van de oude versie met NAT op de ISP-routers. |

Wat er werkt, aangetoond met tests:

- Elke host bereikt zijn gateway (`.1`). Die gateway is Faucet zelf.
- Hosts in hetzelfde VLAN bereiken elkaar, ook tussen gebouw A en B (via de darkfiber).
- Routering tussen VLAN's door Faucet, met een **stateful firewall in Faucet** (connection tracking, `ct`).
- Management mag naar employee, maar employee niet naar management. Antwoordverkeer komt wel terug.
- Guests bereiken alleen het internet: niet elkaar, niet employee en niet management.
- Alle VLAN's bereiken de host `internet` (`8.8.8.8`).
- **NAT in Faucet:** de host `internet` ziet alleen `198.51.100.9` als bron, nooit een `10.x`-adres. De vertaling staat in de conntrack-tabel van de switch. Op `isp_a` en `isp_b` staat geen enkele NAT-regel.
- Van buiten kan niemand een nieuwe verbinding naar binnen opzetten, ook niet naar het NAT-adres.
- Port security: een ander MAC-adres op een managementpoort wordt gedropt.
- Guests worden beperkt tot **1,05 Mbit/s**; employees zijn niet beperkt (13 Gbit/s).

## 2. Wat er veranderd is

### 2.1 Faucet-config ([IPV4_Topo_opdracht2.yml](IPV4_Topo_opdracht2.yml))

- **Opzoekregel** (nog niet gevolgd verkeer) op elke host- en ISP-poort: `ct: {zone: 10, table: 0, nat: {}}`. Die lege `nat: {}` past een bestaande vertaling toe, in beide richtingen. Uitgaande pakketten van een bestaande verbinding krijgen zo `198.51.100.9` als bron. Antwoorden die op de ISP-poort binnenkomen krijgen het privé-adres terug als doel.
- **Nieuwe verbinding naar internet**: `ct: {zone: 10, flags: 1, table: 1, nat: {flags: 1, range_ipv4_min: 198.51.100.9, range_ipv4_max: 198.51.100.9}}`. Dit legt de verbinding vast (commit) en zet het bronadres om (SNAT). Dit is precies het patroon uit de Faucet-tutorial *Connection tracking*.
- **Nieuwe verbinding binnen `10.0.0.0/8`**: alleen commit, zonder NAT. Verkeer tussen de VLAN's houdt dus zijn eigen adressen.
- **ISP-poorten**: nieuw van buiten mag alleen een ping vanuit het ISP-segment naar Faucet `.2`; de rest wordt gedropt.
- **Adressen**: het VLAN `isp` is nu `198.51.100.2/29` (was `/28`). De reden staat in 2.3.

### 2.2 Topologie ([IPV4_Topo_opdracht2.py](IPV4_Topo_opdracht2.py))

- `isp_a`/`isp_b`: de `iptables`-SNAT is eruit. Ze routeren alleen: een default route naar `internet`, en `198.51.100.8/29 via 198.51.100.2` (het NAT-blok ligt achter Faucet). Ze kennen geen `10.x` meer, net als een echte provider.
- De klantzijde van de ISP-routers is `/29` geworden (`198.51.100.1/29` en `198.51.100.3/29`).
- De host `internet` heeft een route terug naar het publieke blok van de klant: `198.51.100.0/28` via `isp_a` (metric 10), met `isp_b` als reserve (metric 20).
- De wachttijd na het starten is 12 s geworden (was 6 s), zodat de stack klaar is voordat jij in de CLI gaat pingen (zie 6.4).

### 2.3 Gevonden en opgelost tijdens het testen

1. **Eerste poging: NAT naar `198.51.100.2` (de Faucet-VIP zelf). Resultaat 51/53.**
   - Alle NAT-tests slaagden, maar daarna gaf Faucet geen antwoord meer op een ping naar `198.51.100.2`.
   - **Oorzaak** (gevonden in de flowtabellen en in `faucet/valve_route.py`): Faucet leert elk bron-IP binnen een VIP-subnet als host. Uitgaande pakketten hadden na de NAT `198.51.100.2` als bron, dus Faucet leerde zijn **eigen** VIP als host met zijn eigen MAC (`0e:00:00:00:00:01`). Daarna ging een ping naar dat adres niet meer naar de controller.
   - **Oplossing:** het NAT-adres moet buiten elk VIP-subnet liggen. Het /28 van de klant is daarom in twee helften gesplitst:

     | Deel | Gebruik |
     |---|---|
     | `198.51.100.0/29` | ISP-segment (VLAN 500): `isp_a` .1, Faucet .2, `isp_b` .3 |
     | `198.51.100.8/29` | NAT-blok: Faucet vertaalt naar `.9`; de ISP-routers routeren dit blok naar Faucet `.2` |

2. **Testverwachting fout: `internet → 198.51.100.2`.**
   - Ik had verwacht dat Faucet antwoord zou geven, maar volgens de broncode (`from_connected_to_vip`) beantwoordt Faucet een ping naar zijn VIP alleen als die uit het direct aangesloten subnet komt.
   - De ACL zegt dat nu ook expliciet (`ipv4_src: 198.51.100.0/29`) en de test verwacht "geblokkeerd".
3. **Race in mijn testscript.**
   - In één run faalde `a2_emp → gateway` (3 van 3 pings kwijt).
   - Het Faucet-log liet zien dat de stackpoorten pas ~7 s na het verbinden UP gaan. Bij elke overgang herconfigureert Faucet de VLAN's en vergeet het geleerde hosts. Mijn script begon na 4,4 s al met testen.
   - Het script wacht nu tot Faucet (via Prometheus, poort 9302) alle 12 stackpoort-uiteinden als UP meldt. Daarna 4 runs na elkaar zonder één verloren ping.

### 2.4 Gateway van `.254` naar `.1` (10 november)

De virtuele gateways van Faucet zijn verplaatst van `.254` naar `.1`: `10.0.100.1/23`, `10.0.200.1/24` en `10.0.30.1/24`. Aangepast zijn `faucet_vips` in beide yml-bestanden, de guest-regel "Nieuw naar eigen gateway" (`10.0.200.1/32`), `gw4()` in de topologie en het testscript. Het ISP-segment blijft `198.51.100.2`, want `.1` is daar `isp_a`.

Getest: met firewall **54/54** (run 13), zonder firewall **54/54** (run 14). De versie met firewall staat live.

### 2.5 Controle

- `check_faucet_config` op de nieuwe config: exit 0.
- Reservekopie van de vorige live-config: `/etc/faucet/faucet.yaml.backup-voor-nat-in-faucet-20261109-2121`. De oudste kopie, van vóór opdracht 2, staat er ook nog.
- Na afloop staat er niets meer open op de Mininet-VM: `ovs-vsctl list-br` geeft 0 bridges.
- **Je eigen script los gecontroleerd met de Mininet-CLI** (`cli_check_nat.log`):
  - `a1_emp` en `b2_gst ping 8.8.8.8` werken, met TTL 62: het pakket ging door Faucet en `isp_a`;
  - `isp_a iptables -t nat -S POSTROUTING` is leeg;
  - `a2_gst ping 10.0.100.11` wordt geblokkeerd;
  - de conntrack-tabel toont de vertaling naar `198.51.100.9`.

## 3. Hoe de Faucet-config werkt

### 3.1 VLAN's, gateways en routering

| VLAN | vid | Faucet-gateway (`faucet_vips`) | Poorten |
|---|---|---|---|
| office (employee) | 100 | `10.0.100.1/23` | p2 op elke verdiepingsswitch |
| guest | 200 | `10.0.200.1/24` | p3 op elke verdiepingsswitch |
| management | 300 | `10.0.30.1/24` | p4 op elke verdiepingsswitch |
| isp | 500 | `198.51.100.2/29` | `a_core` p4 (isp_a) en `b_core` p5 (isp_b) |

- `routers: intern` zet routering aan tussen alle vier de VLAN's. Wat er mag, bepalen de firewall-ACL's.
- **Default route** van Faucet: `0.0.0.0/0 via 198.51.100.1` (isp_a), ingesteld onder het VLAN `isp`.
- **Terugweg:** `internet` → `isp_a` → (route `198.51.100.8/29 via 198.51.100.2`) → Faucet. Daar zet de ISP-poort-ACL het doeladres terug van `.9` naar het privé-adres, en Faucet routeert het pakket naar binnen.

### 3.2 Stacking

Alle verbindingen tussen de switches zijn **stack-links**, en `a_core` is de stack-root (`priority: 1`). Faucet kent zo de hele topologie, en dat is nodig om te routeren over meerdere switches (volgens de Faucet-docs: *"inter-VLAN routing can work between hosts on different switches"* bij stacking).

### 3.3 Stateful firewall en NAT met connection tracking

Elke hostpoort heeft een ACL volgens dit patroon:

| Stap | Match | Actie | Betekenis |
|---|---|---|---|
| 1 | ARP | `allow` | adressen opzoeken mag altijd |
| 2 | `ct_state: 0/0x20` (nog niet gevolgd) | `ct: {zone: 10, table: 0, nat: {}}` | door conntrack, bestaande NAT toepassen, opnieuw door de ACL |
| 3 | `ct_state: 0x22/0x22` (+est) | `allow` | pakket van een bestaande verbinding |
| 4 | `ct_state: 0x24/0x24` (+rel) | `allow` | bijbehorende ICMP-fouten |
| 5 | +new en doel verboden | `allow: 0` | nieuwe verbinding die niet mag |
| 6 | +new naar `10.0.0.0/8` | `ct: {zone: 10, flags: 1, table: 1}` | **commit**, zonder NAT (intern verkeer) |
| 7 | +new (overig = internet) | `ct: {…, flags: 1, table: 1, nat: {flags: 1, range_ipv4_min/max: 198.51.100.9}}` | **commit + SNAT** naar `198.51.100.9` |
| 8 | alles anders | `allow: 0` | standaard dicht |

De ISP-poorten hebben stappen 1 t/m 4. Daarna mag alleen een ping vanuit `198.51.100.0/29` naar `198.51.100.2`, en de rest wordt gedropt. Antwoorden op verbindingen van binnen zijn `+est` en mogen door; stap 2 heeft het doeladres dan al teruggezet.

Per soort poort is het beleid zo, en elke cel is met minstens één test aangetoond:

| Bron \ doel | Employee | Guest | Management | Internet |
|---|---|---|---|---|
| **Employee** | ✅ | ❌ | ❌ | ✅ (NAT) |
| **Guest** | ❌ | ❌ (ook onderling) | ❌ | ✅ (NAT, 1 Mbit/s) |
| **Management** | ✅ | ❌ | ✅ | ✅ (NAT) |
| **ISP / buiten** | ❌ | ❌ | ❌ | – |

"❌" geldt voor **nieuwe** verbindingen. Antwoorden op toegestane verbindingen komen altijd terug, dankzij `+est`.

### 3.4 Port security en rate limiting

- **Port security:** de ACL's `mgt-fw-a1` t/m `mgt-fw-b3` matchen in elke regel op het vaste bron-MAC-adres van die poort (`02:00:00:00:30:<nr>`). Een ander MAC-adres valt door naar "droppen".
- **Rate limiting:** de meter `guest-rate-limit` (1000 kbit/s) staat op de `+est`- en `+rel`-regels van de guest-ACL. Daardoor wordt bijna al het verkeer van een guest gemeten. Alleen het allereerste pakket van een verbinding (`+new`) gaat er niet doorheen.

## 4. Testresultaten (run 13, met gateway `.1`; runs 7-10 met `.254` gaven ook 54/54)

| # | Groep | Test | Verwacht | Resultaat | Detail | |
|---|---|---|---|---|---|---|
| 1 | Gateway (Faucet-VIP) | a1_emp → gateway (10.0.100.1) | werkt | werkt | 0% loss | ✅ |
| 2 | Gateway (Faucet-VIP) | a1_gst → gateway (10.0.200.1) | werkt | werkt | 0% loss | ✅ |
| 3 | Gateway (Faucet-VIP) | a1_mgt → gateway (10.0.30.1) | werkt | werkt | 0% loss | ✅ |
| 4 | Gateway (Faucet-VIP) | a2_emp → gateway (10.0.100.1) | werkt | werkt | 0% loss | ✅ |
| 5 | Gateway (Faucet-VIP) | a2_gst → gateway (10.0.200.1) | werkt | werkt | 0% loss | ✅ |
| 6 | Gateway (Faucet-VIP) | a2_mgt → gateway (10.0.30.1) | werkt | werkt | 0% loss | ✅ |
| 7 | Gateway (Faucet-VIP) | b1_emp → gateway (10.0.100.1) | werkt | werkt | 0% loss | ✅ |
| 8 | Gateway (Faucet-VIP) | b1_gst → gateway (10.0.200.1) | werkt | werkt | 0% loss | ✅ |
| 9 | Gateway (Faucet-VIP) | b1_mgt → gateway (10.0.30.1) | werkt | werkt | 0% loss | ✅ |
| 10 | Gateway (Faucet-VIP) | b2_emp → gateway (10.0.100.1) | werkt | werkt | 0% loss | ✅ |
| 11 | Gateway (Faucet-VIP) | b2_gst → gateway (10.0.200.1) | werkt | werkt | 0% loss | ✅ |
| 12 | Gateway (Faucet-VIP) | b2_mgt → gateway (10.0.30.1) | werkt | werkt | 0% loss | ✅ |
| 13 | Gateway (Faucet-VIP) | b3_emp → gateway (10.0.100.1) | werkt | werkt | 0% loss | ✅ |
| 14 | Gateway (Faucet-VIP) | b3_gst → gateway (10.0.200.1) | werkt | werkt | 0% loss | ✅ |
| 15 | Gateway (Faucet-VIP) | b3_mgt → gateway (10.0.30.1) | werkt | werkt | 0% loss | ✅ |
| 16 | Zelfde VLAN | a1_emp → a2_emp (10.0.100.12) | werkt | werkt | 0% loss | ✅ |
| 17 | Zelfde VLAN | a1_emp → b3_emp (10.0.100.23) | werkt | werkt | 0% loss | ✅ |
| 18 | Zelfde VLAN | a1_mgt → b2_mgt (10.0.30.22) | werkt | werkt | 0% loss | ✅ |
| 19 | Tussen VLAN's | a1_mgt → b1_emp (10.0.100.21) | werkt | werkt | 0% loss | ✅ |
| 20 | Tussen VLAN's | b3_mgt → a2_emp (10.0.100.12) | werkt | werkt | 0% loss | ✅ |
| 21 | Tussen VLAN's | a1_emp → a1_mgt (10.0.30.11) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 22 | Tussen VLAN's | b2_emp → a2_mgt (10.0.30.12) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 23 | Tussen VLAN's | a1_emp → b2_gst (10.0.200.22) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 24 | Tussen VLAN's | b1_mgt → a1_gst (10.0.200.11) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 25 | Tussen VLAN's | a2_gst → a1_emp (10.0.100.11) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 26 | Tussen VLAN's | b3_gst → b3_mgt (10.0.30.23) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 27 | Gastisolatie | a1_gst → a2_gst (10.0.200.12) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 28 | Gastisolatie | a1_gst → b1_gst (10.0.200.21) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 29 | Gastisolatie | b2_gst → b3_gst (10.0.200.23) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 30 | Internet | a1_emp → internet (8.8.8.8) | werkt | werkt | 0% loss | ✅ |
| 31 | Internet | b2_emp → internet (8.8.8.8) | werkt | werkt | 0% loss | ✅ |
| 32 | Internet | a2_gst → internet (8.8.8.8) | werkt | werkt | 0% loss | ✅ |
| 33 | Internet | b3_gst → internet (8.8.8.8) | werkt | werkt | 0% loss | ✅ |
| 34 | Internet | a1_mgt → internet (8.8.8.8) | werkt | werkt | 0% loss | ✅ |
| 35 | Internet | b1_mgt → internet (8.8.8.8) | werkt | werkt | 0% loss | ✅ |
| 36 | NAT in Faucet | bron op internet-eth0 = 198.51.100.9 (a1_emp en b3_gst) | werkt | werkt | zie tcpdump in rapport | ✅ |
| 37 | NAT in Faucet | conntrack: 10.0.100.11 → 8.8.8.8, antwoord naar 198.51.100.9 | werkt | werkt | 2 NAT-verbinding(en) | ✅ |
| 38 | NAT in Faucet | isp_a en isp_b hebben geen SNAT/MASQUERADE-regels | werkt | werkt | iptables -t nat leeg | ✅ |
| 39 | Van buiten naar binnen | isp_a → a1_emp (10.0.100.11) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 40 | Van buiten naar binnen | isp_b → b1_mgt (10.0.30.21) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 41 | Van buiten naar binnen | isp_a → a2_gst (10.0.200.12) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 42 | Van buiten naar binnen | isp_a → Faucet-VIP (198.51.100.2) | werkt | werkt | 0% loss | ✅ |
| 43 | Van buiten naar binnen | internet → Faucet-VIP (198.51.100.2) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 44 | Van buiten naar binnen | internet → NAT-adres (198.51.100.9) | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 45 | TCP (stateful) | TCP a1_emp → internet:8000 (8.8.8.8) | werkt | werkt | wget rc=0 | ✅ |
| 46 | TCP (stateful) | TCP b2_gst → internet:8000 (8.8.8.8) | werkt | werkt | wget rc=0 | ✅ |
| 47 | TCP (stateful) | TCP a1_mgt → b1_emp:8000 (10.0.100.21) | werkt | werkt | wget rc=0 | ✅ |
| 48 | TCP (stateful) | TCP b1_emp → a1_mgt:8000 (10.0.30.11) | geblokkeerd | geblokkeerd | wget rc=4 | ✅ |
| 49 | TCP (stateful) | TCP a2_gst → a2_emp:8000 (10.0.100.12) | geblokkeerd | geblokkeerd | wget rc=4 | ✅ |
| 50 | TCP (stateful) | TCP isp_a → a1_emp:8000 (10.0.100.11) | geblokkeerd | geblokkeerd | wget rc=4 | ✅ |
| 51 | Port security | a1_mgt met vals MAC 02:00:00:00:30:99 → gateway | geblokkeerd | geblokkeerd | 100% loss | ✅ |
| 52 | Port security | a1_mgt met juist MAC 02:00:00:00:30:11 → gateway | werkt | werkt | 0% loss | ✅ |
| 53 | Rate limiting | a1_gst → internet <= 1.2 Mbit/s (meter 1 Mbit/s) | werkt | werkt | 1.07 Mbit/s | ✅ |
| 54 | Rate limiting | a1_emp → internet > 5 Mbit/s (geen limiet) | werkt | werkt | 12772.43 Mbit/s | ✅ |

Bij de tests "van buiten naar binnen" (39-41 en 50) zet het script tijdelijk een route naar `10.0.0.0/8` op `isp_a`/`isp_b`. Zo wordt een aanvaller in het ISP-segment nagebootst. Zonder die route komt het verkeer niet eens bij Faucet aan, en dan bewijst de test niets over de firewall. Na test 50 haalt het script de route weer weg.

## 5. Bewijs uit de switches en de hosts

**NAT**: tcpdump op `internet-eth0` terwijl `a1_emp` (`10.0.100.11`) en `b3_gst` (`10.0.200.23`) pingen. Beide komen binnen als `198.51.100.9`:
```
IP 198.51.100.9 > 8.8.8.8: ICMP echo request, id 30890, seq 1, length 64    <- a1_emp
IP 8.8.8.8 > 198.51.100.9: ICMP echo reply, id 30890, seq 1, length 64
IP 198.51.100.9 > 8.8.8.8: ICMP echo request, id 30891, seq 1, length 64    <- b3_gst
IP 8.8.8.8 > 198.51.100.9: ICMP echo reply, id 30891, seq 1, length 64
```

**Conntrack-tabel** (`ovs-appctl dpctl/dump-conntrack zone=10`, selectie). `orig` is het pakket zoals de host het stuurt, `reply` hoe het antwoord terugkomt:
```
icmp,orig=(src=10.0.100.11,dst=8.8.8.8,...),reply=(src=8.8.8.8,dst=198.51.100.9,...),zone=10      <- employee -> internet, NAT
tcp,orig=(src=10.0.200.22,dst=8.8.8.8,...,dport=8000),reply=(src=8.8.8.8,dst=198.51.100.9,...)    <- guest -> internet, NAT
tcp,orig=(src=10.0.30.11,dst=10.0.100.21,...,dport=8000),reply=(src=10.0.100.21,dst=10.0.30.11,...) <- management -> employee, geen NAT
```

**Flows op `a_f1`** (tabel 0, selectie). Poort 2 = employee, 3 = guest, 4 = management:
```
ct_state=-trk,ip,in_port=2                                actions=ct(table=0,zone=10,nat)
ct_state=+new+trk,ip,in_port=2,nw_dst=10.0.200.0/24       actions=drop
ct_state=+new+trk,ip,in_port=2,nw_dst=10.0.30.0/24        actions=drop
ct_state=+new+trk,ip,in_port=2,nw_dst=10.0.0.0/8          actions=ct(commit,table=1,zone=10)
ct_state=+new+trk,ip,in_port=2                            actions=ct(commit,table=1,zone=10,nat(src=198.51.100.9))
ct_state=+new+trk,ip,in_port=3,nw_dst=10.0.0.0/8          actions=drop      (6 pakketten gedropt)
ct_state=+new+trk,ip,in_port=3                            actions=ct(commit,table=1,zone=10,nat(src=198.51.100.9))
ct_state=+est+trk,ip,in_port=3                            actions=meter:1,goto_table:1
```

**ISP-routers doen geen NAT** (`iptables -t nat -S POSTROUTING`) en kennen alleen publieke routes:
```
isp_a: -P POSTROUTING ACCEPT
isp_b: -P POSTROUTING ACCEPT

isp_a# ip route
default via 203.0.113.2 dev isp_a-eth1
198.51.100.0/29 dev isp_a-eth0 proto kernel scope link src 198.51.100.1
198.51.100.8/29 via 198.51.100.2 dev isp_a-eth0
203.0.113.0/30 dev isp_a-eth1 proto kernel scope link src 203.0.113.1
```

**Meter op `a_f1`**: de meter heeft 152 pakketten gedropt om guest-verkeer onder 1 Mbit/s te houden.
```
meter:1 flow_count:2 packet_in_count:974 byte_in_count:1660996
0: packet_count:152 byte_count:295288
```

**Snelheid (iperf3, gemeten aan de ontvangende kant, mét NAT)**:
```
guest    a1_gst -> internet: ontvangen 1.05 Mbit/s (196 retransmits)
employee a1_emp -> internet: ontvangen 13102.60 Mbit/s
```

## 6. Aandachtspunten

1. **Mininet deelt één conntrack-tabel over alle switches.**
   - Alle OVS-bridges op de Mininet-VM gebruiken dezelfde kernel-conntrack. De NAT gebeurt op de verdiepingsswitch (bv. `a_f1`). Het antwoord wordt op `a_core` (de ISP-poort) terugvertaald met de verbinding die `a_f1` vastlegde.
   - Hetzelfde geldt al voor de firewall: een antwoord tussen gebouwen wordt op een andere switch als `+est` herkend.
   - In Mininet werkt dit, maar met losse fysieke switches heeft elke switch zijn eigen tabel. Daar moeten de firewall/NAT-regels op de switch staan waar heen- én terugverkeer langskomt (bv. de core). Goed om te weten als je docent ernaar vraagt.
2. **Het NAT-adres is `198.51.100.9`, niet het Faucet-adres `.2`.** Zie 2.3: NAT naar de VIP zelf brak Faucet. Alle 500 gebruikers delen dat ene adres (PAT: conntrack kiest per verbinding een poort). Meer adressen kan met `range_ipv4_max: 198.51.100.14`.
3. **`isp_b` is reserve, zonder automatische failover.**
   - Faucet heeft één statische default route via `isp_a`, en statische routes in Faucet hebben geen health-check.
   - Overstappen doe je door `ip_gw` te veranderen in `198.51.100.3` en Faucet te herstarten.
   - Omdat de NAT nu in Faucet zit, hoeft er op `isp_b` niets te veranderen: beide ISP-routers routeren `198.51.100.8/29` al naar Faucet.
4. **De stack heeft ~7-8 s nodig na het starten.** Tot alle stackpoorten UP zijn, herconfigureert Faucet de VLAN's en kunnen pings wegvallen. Daarom wacht je topologiescript nu 12 s voordat de CLI verschijnt.
5. **Melding `OFPMMFC_INVALID_METER` in het Faucet-log.**
   - Elke verdiepingsswitch meldt deze fout twee keer bij een cold start. Dat was ook al zo in het log van 27 oktober, met de oude config.
   - De meter werkt daarna wel (`meter:1`, `flow_count:2`, de rate-limit-test slaagt). Het is dus een melding bij het opstarten en geen werkingsprobleem. De precieze oorzaak heb ik niet uitgezocht.
6. **Rate limit alleen in de uploadrichting.** De meter staat op de inkomende guest-poort, dus verkeer **van** de guest wordt beperkt. Verkeer **naar** de guest (download) niet.
7. **IPv6 staat niet in deze config.** Dit is de IPv4-versie. IPv6-pakketten vallen bij de hostpoorten onder "al het andere droppen".
8. **De oude variant (NAT op de ISP-routers) staat niet in git.** De bestanden zijn nooit gecommit. De oude Faucet-config staat wel als reservekopie op de Faucet-VM (zie 7). De oude topologie, met `iptables`-SNAT op de ISP-routers, kan ik desgewenst terugzetten.
9. **Correctie in je eigen notities.** In [Demo_SDN_Practicum.md](Demo_SDN_Practicum.md) (regel 127) staat dat Faucet geen connection tracking kent. Dat klopt niet: deze tests laten firewall én NAT met `ct` zien.

## 7. Zelf opnieuw draaien

Op de Mininet-VM:
```bash
cd ~/sdn-opdracht2/opdracht2-ipv4
sudo mn -c
# alle tests automatisch (duurt ~2 minuten):
sudo python3 test_ipv4_opdracht2.py --controller-ip 10.24.20.8 --out /tmp/resultaat.json
# of interactief met de Mininet-CLI:
sudo python3 IPV4_Topo_opdracht2.py --controller-ip 10.24.20.8
```

Handige commando's in de Mininet-CLI:
```
a1_emp ping -c 3 8.8.8.8                                   # internet via Faucet (NAT) + isp_a
internet tcpdump -n -i internet-eth0 -c 4 icmp &            # dan nog een ping: bron is 198.51.100.9
sh ovs-appctl dpctl/dump-conntrack zone=10 | grep 198.51.100.9   # de NAT-vertalingen
isp_a iptables -t nat -S                                   # leeg: de ISP doet geen NAT
a1_emp ping -c 2 10.0.30.11                                # employee -> management: geblokkeerd
a1_mgt ping -c 2 10.0.100.11                               # management -> employee: werkt
sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 table=0 | grep ct
sh ovs-ofctl -O OpenFlow13 meter-stats a_f1
```

Terug naar een eerdere Faucet-config (op de Faucet-VM):
```bash
# versie met NAT op de ISP-routers (vereist ook de oude topologie, zie 6.8):
cp /etc/faucet/faucet.yaml.backup-voor-nat-in-faucet-20261109-2121 /etc/faucet/faucet.yaml
# of je oorspronkelijke config van vóór opdracht 2:
cp /etc/faucet/faucet.yaml.backup-voor-ipv4-opdracht2-20261109-1853 /etc/faucet/faucet.yaml
systemctl restart faucet
```

## 8. Firewall uit- en aanzetten

### 8.1 Wat de variant zonder firewall anders doet

De ACL's doen firewall én NAT tegelijk. De ACL's helemaal weghalen kan dus niet, want dan werkt internet niet meer. [IPV4_Topo_opdracht2_zonder_fw.yml](IPV4_Topo_opdracht2_zonder_fw.yml) is daarom dezelfde config, met alleen de verbodsregels aangepast:

| ACL | Verschil met de versie mét firewall |
|---|---|
| `office-fw` (employee) | regels "Nieuw naar guest verboden" en "Nieuw naar management verboden" weg |
| `guest-fw` | "Nieuw naar 10.0.0.0/8 verboden" is geworden: vastleggen zonder NAT. Alleen weghalen kan hier niet: dan krijgt guest-verkeer naar binnen het NAT-adres als bron, en dat loopt vast. |
| `mgt-fw-*` (management) | regel "Nieuw naar guest verboden" weg |
| `isp-uplink` | ongewijzigd: van buiten blijft dicht |

Wat blijft werken:
- conntrack en NAT naar `198.51.100.9`;
- routering en stacking;
- port security op management;
- de 1 Mbit/s-limiet voor guests.

De ACL-namen en de `dps`-sectie zijn gelijk gebleven. Wisselen is dus alleen het bestand vervangen.

### 8.2 Wisselen (op de Faucet-VM)

Beide bestanden staan al in `/etc/faucet/`:
```bash
# firewall UIT:
cp /etc/faucet/IPV4_Topo_opdracht2_zonder_fw.yml /etc/faucet/faucet.yaml && systemctl reload faucet
# firewall AAN:
cp /etc/faucet/IPV4_Topo_opdracht2.yml /etc/faucet/faucet.yaml && systemctl reload faucet
```

`reload` laat Faucet de config opnieuw inlezen, zonder herstart. Faucet ziet dat alleen ACL's veranderd zijn en doet een **warme start**. Volgens het log vervangt het alleen de ACL-flows op poort 2, 3 en 4 van elke verdiepingsswitch. De stack, de routes en de geleerde hosts blijven staan, en je Mininet-netwerk hoeft niet opnieuw te starten.

### 8.3 Getest

**Live wissel**, terwijl één Mininet-netwerk bleef draaien (`live_wissel.log`):

| Test | Stap 1: met firewall | Stap 2: na reload zonder firewall | Stap 3: na reload met firewall |
|---|---|---|---|
| employee → management (`a1_emp → 10.0.30.11`) | geblokkeerd | **werkt** | geblokkeerd |
| guest → guest (`a1_gst → 10.0.200.12`) | geblokkeerd | **werkt** | geblokkeerd |
| guest → employee (`a2_gst → 10.0.100.11`) | geblokkeerd | **werkt** | geblokkeerd |
| management → employee (`a1_mgt → 10.0.100.21`) | werkt | werkt | werkt |
| employee → internet, NAT (`a1_emp → 8.8.8.8`) | werkt | werkt | werkt |
| guest → internet, NAT (`b3_gst → 8.8.8.8`) | werkt | werkt | werkt |

Na elke `systemctl reload` was de wijziging binnen **~1 s** actief: de eerste nieuwe ping had het nieuwe resultaat al.

**Volledige testruns:**
- **Run 11, zonder firewall** (`test_ipv4_opdracht2.py --zonder-fw`): **54/54**.
  - De 11 tests die de firewall eerst tegenhield, werken nu allemaal: 6 in groep 3, 3 in groep 4, en TCP employee → management en guest → employee.
  - NAT, port security, de rate limit en "van buiten naar binnen dicht" gaven hetzelfde resultaat als met firewall.
- **Run 12, firewall weer aan** (via `reload`): **54/54**, hetzelfde als run 7-10. Het terugzetten is dus volledig.

Na afloop staat de versie **met** firewall weer live op de Faucet-VM.

### 8.4 Let op bij een demo

- De firewall is **stateful**. Zet je hem weer aan terwijl er al een verbinding loopt, bijvoorbeeld een `ping` zonder `-c` van employee naar management, dan loopt die verbinding gewoon door. Conntrack kent haar al als `+est`.
- Pas een **nieuwe** verbinding wordt geblokkeerd. Stop de lopende ping dus en start een nieuwe: elke `ping`-opdracht is een nieuwe verbinding.
- Een opgebouwde verbinding blijft na het uitzetten van de firewall ook gewoon bestaan, maar daar merk je niets van: alles mag dan.
