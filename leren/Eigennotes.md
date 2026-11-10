# eersste deel ipv4

Loops in topolgie zijn om de juiste ip en dip nummer te geven aan de switches


Per onderdeel
Imports (r. 3-10): dit zijn de bouwstenen van Mininet: hosts, switches, links, de CLI en de remote controller.

Constanten (r. 12-45): hier staat het ontwerp als data.

NATGW_MAC: het vaste MAC-adres van de gateway. De guest-ACL in Faucet matcht hierop: guests mogen alleen naar dit MAC.
VLANS: per netwerk de VLAN-ID, het subnet en de prefixlengte. Employee heeft /23, de andere twee /24.
FLOORS, PORTS, SWITCHES: welke switch op welke verdieping staat, welke poort bij welk VLAN hoort en welk DPID elke switch heeft. Die DPID's moeten overeenkomen met de dp_id in Faucet.
gw4() (r. 48): maakt het gateway-adres van een VLAN, bijvoorbeeld 10.0.100.254.

BuildingsTopo (r. 52-101): de bekabeling.

failMode="secure": zonder controller sturen de switches niets door. Ze vallen dus niet terug op een "domme" switch.
isp_net is een gewone OVSBridge zonder Faucet. Dit stelt het internet voor.
De dubbele lus maakt alle 15 hosts aan met het juiste IP-adres en koppelt ze aan de juiste poort.
Management-hosts krijgen een vast MAC-adres (02:00:00:00:30:11 enz.). Dat is nodig voor de port-security-ACL's in Faucet.
Daarna komen de links: core naar verdieping (poort 1), de darkfiber tussen de cores en natgw op a_core poort 4.
configure_natgw() (r. 104-163): hier wordt natgw een router. Dit is het belangrijkste deel.

modprobe 8021q laadt VLAN-ondersteuning in de Linux-kernel. ip_forward=1 laat de machine pakketten doorsturen, en dat maakt hem een router. send_redirects=0 voorkomt ICMP-redirects.
Router-on-a-stick: op één kabel komen drie subinterfaces (natgw-eth0.100, .200 en .300). Elke subinterface krijgt het .254-adres van zijn VLAN.
Publieke kant: 198.51.100.2/28, met de default route naar de ISP (.1).
Stateful firewall (iptables):
Standaard staat alles op DROP, zowel INPUT (naar de router zelf) als FORWARD (door de router heen).
Toegestaan: loopback, antwoorden op bestaande verbindingen (ESTABLISHED,RELATED) en verkeer van binnen naar de router zelf.
Nieuwe verbindingen mogen van elk VLAN naar de ISP, en van management naar employee.
Al het andere wordt gedropt: employee naar guest of management, guest naar intern, en internet naar binnen.
"Stateful" betekent dat de firewall verbindingen onthoudt. Een antwoord op een ping die van binnen kwam mag dus terug naar binnen, maar een nieuwe verbinding van buiten niet.
NAT/PAT: alle 10.x-adressen worden bij het verlaten van de router vervangen door 198.51.100.2. Met poortnummers houdt de router bij welk antwoord bij welke host hoort.
configure_hosts() (r. 166-170): elke host krijgt als default route de gateway van zijn eigen VLAN.

run_topology() (r. 173-199): start en stopt het netwerk.

Mininet(...) maakt het netwerk. TCLink maakt bandbreedte- en delay-instellingen mogelijk. autoStaticArp=False zorgt dat ARP echt plaatsvindt, zoals in een echt netwerk.
RemoteController(..., port=6653) wijst naar Faucet. 6653 is de standaard OpenFlow-poort.
sleep 6 geeft de switches tijd om verbinding te maken met Faucet.
CLI(net) geeft je de mininet>-prompt, waar je bijvoorbeeld a1_emp ping 10.0.200.11 of pingall kunt typen.
net.stop() ruimt alles op als je exit typt.
__main__ (r. 202-208): leest het IP-adres van de Faucet-VM uit de opdrachtregel. Starten doe je zo:


sudo python3 IPV4_Topo_opdracht2.py --controller-ip <IP-van-Faucet-VM>

3. Waar leidt de default gateway heen?
Elke host heeft default via <net>.254, bijvoorbeeld 10.0.100.254. Dat adres is geen apparaat maar een virtueel IP van Faucet (faucet_vips):

ARP: de host vraagt "wie heeft 10.0.100.254?". De switch stuurt dat naar Faucet, en Faucet antwoordt met zijn virtuele MAC 0e:00:00:00:00:01.
Routeren: pakketten naar dat MAC worden in de switch zelf gerouteerd. Faucet heeft daar flows voor geïnstalleerd die het VLAN, het MAC en de TTL aanpassen. De controller zit dus niet in het datapad; hij bedenkt alleen de regels.
Naar internet: daarvoor heeft Faucet een eigen default route: 0.0.0.0/0 via 198.51.100.1, dus isp_a. Onderweg gebeurt de NAT naar 198.51.100.9, en isp_a stuurt het door naar de host internet.

4. Waarom zijn sommige MAC-adressen automatisch en andere vast?
Automatisch (employee en guest): het script start Mininet met autoSetMacs=True. Mininet nummert de MAC's dan op volgorde: 00:00:00:00:00:01, :02, enzovoort. Niemand controleert die MAC's, dus het exacte adres maakt niet uit.
Vast (management, 02:00:00:00:30:<nr>): dit is nodig voor port security. De ACL mgt-fw-a1 laat alleen verkeer door met eth_src: 02:00:00:00:30:11, en elk ander MAC wordt gedropt (test 51 bewijst dat). Daarvoor moet je vooraf weten welk MAC er hoort. Een automatisch MAC kan veranderen als je hosts toevoegt of de volgorde wijzigt, en dan zou de beheerder zichzelf buitensluiten.
De 02 aan het begin betekent "lokaal toegekend". Zo'n adres botst nooit met een echt fabrikantenadres.
De 30 en het hostnummer (11, 12, 21, …) maken het leesbaar: VLAN 30(0) en host .11.


# intervlan 

1. A wil naar 10.0.200.10.
2. A merkt dat dit buiten zijn eigen subnet valt.
3. A zoekt het MAC-adres van zijn gateway 10.0.100.1 via ARP.
4. Faucet antwoordt met het MAC-adres dat bij de gateway hoort.
5. A stuurt het Ethernet-frame naar dat MAC-adres.
6. De switch routeert het IP-pakket naar VLAN 200.
7. B ontvangt het pakket.
4. Hoe kun je dit onthouden?
- Host: heeft een default gateway ingesteld.
- Faucet YAML: bepaalt welk gateway-IP bij welk VLAN hoort.
- Switch: voert de routering uit met de OpenFlow-regels van Faucet


#documetie tekstjes

Ik heb eerst een IP-plan gemaakt: elk netwerk heeft een eigen subnet, employee een /23, guest en management een /24. Daarna heb ik elk netwerk in een eigen VLAN gezet: 100, 200 en 300. Op elke verdiepingsswitch heeft elke groep een eigen accesspoort. Zo zijn de netwerken op layer 2 gescheiden: broadcasts en frames blijven in hun eigen VLAN. De switches zijn met een Faucet-stack verbonden, zodat Faucet de hele topologie kent. Daardoor lopen de VLAN's over beide gebouwen en kan elke switch routeren via de gateway .1. Omdat Faucet tussen de VLAN's routeert, bepalen de ACL's met connection tracking welke verbindingen mogen. Guest mag alleen naar internet, employee niet naar guest of management, en management wel naar employee."

Je hebt gelijk: wat Faucet doet is PAT. Alle gebruikers delen één IP-adres (198.51.100.9), en verbindingen worden uit elkaar gehouden op poortnummer. Dat deel klopt dus.

Ik bouw het nu stap voor stap op: eerst wie welk adres heeft, dan één pakket heen en terug. Bij elke stap staat wat het apparaat ziet en beslist.

Stap 1: de apparaten en hun interfaces
Ik neem alleen het deel dat nodig is: één gebruiker, Faucet, isp_a en internet.


 a1_emp                Faucet (de switches)            isp_a                         internet
┌───────────────┐     ┌──────────────────────┐     ┌──────────────────────┐     ┌────────────────────┐
│ eth0          │     │ VLAN 100: 10.0.100.1 │     │ eth0  198.51.100.1   │     │ eth0  203.0.113.2  │
│ 10.0.100.11   │────►│ VLAN 500: 198.51.100.2│◄──►│                      │     │                    │
│               │     │                      │     │ eth1  203.0.113.1    │◄───►│ lo    8.8.8.8      │
└───────────────┘     └──────────────────────┘     └──────────────────────┘     └────────────────────┘
     intern                 router + PAT                 ISP-router                    "internet"
Er zijn drie kabels, en elke kabel is een eigen klein netwerk:

Kabel	Netwerk	Wie zit erop
a1_emp ↔ Faucet	10.0.100.0/23	a1_emp .11, Faucet .1
Faucet ↔ isp_a	198.51.100.0/29	Faucet .2, isp_a .1 (en isp_b .3)
isp_a ↔ internet	203.0.113.0/30	isp_a .1, internet .2
198.51.100.9 staat op geen enkele interface. Er is geen kabel en geen apparaat met dat adres. Het bestaat alleen in de conntrack-tabel van Faucet, als het adres dat Faucet in plaats van de echte bron invult.

Stap 2: het pakket gaat naar buiten
a1_emp opent een website: 10.0.100.11:40000 → 8.8.8.8:80.

① a1_emp

Ziet: "8.8.8.8 zit niet in mijn netwerk."
Doet: stuurt het pakket naar de gateway 10.0.100.1 (Faucet).

src 10.0.100.11 : 40000   →   dst 8.8.8.8 : 80
② Faucet, tabel 0 (de ACL)

Ziet: een nieuwe verbinding naar buiten.
Doet: PAT. Het bronadres wordt 198.51.100.9 en Faucet schrijft in de conntrack-tabel:

src 198.51.100.9 : 40000   →   dst 8.8.8.8 : 80

conntrack onthoudt:  198.51.100.9:40000  ⇄  10.0.100.11:40000
③ Faucet, tabel 3 (routering)

Ziet: 8.8.8.8 valt onder de default route via 198.51.100.1.
Doet: stuurt het pakket via VLAN 500 naar isp_a.
④ isp_a

Ziet: 8.8.8.8 valt onder zijn eigen default route via 203.0.113.2.
Doet: stuurt het pakket via eth1 naar internet.
⑤ internet

Ziet: een pakket van 198.51.100.9.
Doet: weet niets van 10.0.100.11 en antwoordt naar .9.
Stap 3: het antwoord komt terug
Bij deze stap gaat het om de splitsing.


src 8.8.8.8 : 80   →   dst 198.51.100.9 : 40000
⑥ internet

Ziet: zijn route 198.51.100.0/28 via 203.0.113.1.
Doet: stuurt het antwoord naar isp_a.
⑦ isp_a: "waar is 198.51.100.9?"

isp_a kijkt in zijn routingtabel. Die ziet er zo uit:


198.51.100.0/29  dev eth0               ← adressen .0 t/m .7: zitten DIRECT op mijn kabel
198.51.100.8/29  via 198.51.100.2       ← adressen .8 t/m .15: stuur naar Faucet
203.0.113.0/30   dev eth1
default          via 203.0.113.2
.9 valt in 198.51.100.8/29, dus isp_a stuurt het antwoord naar 198.51.100.2.
isp_a vraagt via ARP "wie heeft .2?", Faucet antwoordt "ik", en het pakket gaat naar Faucet.
⑧ Faucet, tabel 0 (isp-uplink)

Ziet in conntrack: .9:40000 hoort bij 10.0.100.11:40000.
Doet: zet het doeladres terug.

src 8.8.8.8 : 80   →   dst 10.0.100.11 : 40000
⑨ Faucet routeert het pakket naar VLAN 100, en a1_emp krijgt zijn antwoord.

Stap 4: waarom die splitsing nodig is
Stap ⑦ werkt alleen door de splitsing. Een router behandelt elk doeladres op een van twee manieren:

Ligt het adres…	Wat de router doet
in het netwerk van zijn eigen kabel	denkt "dat apparaat zit direct op mijn kabel" en vraagt via ARP "wie heeft dit adres?"
ergens anders	zoekt een route en stuurt het naar de router die in die route staat
Zonder splitsing: de kabel naar Faucet zou dan de hele 198.51.100.0/28 zijn, en daar valt .9 ook in.


isp_a: ".9 zit op mijn kabel" → ARP: "wie heeft 198.51.100.9?"
       → geen antwoord, want er bestaat geen apparaat met .9
       → antwoord weggegooid ✗
Met splitsing: de kabel is 198.51.100.0/29 (.0 tot en met .7), en .9 valt daarbuiten.


isp_a: ".9 zit niet op mijn kabel, maar ik heb een route: 198.51.100.8/29 via .2"
       → ARP: "wie heeft .2?" → Faucet: "ik!"
       → naar Faucet ✓
De splitsing zorgt er dus voor dat isp_a .9 niet zelf zoekt, maar het pakket aan Faucet geeft. Faucet kent .9 wel, via de conntrack-tabel.

Stap 5: PAT met twee gebruikers tegelijk
Stel dat b1_emp tegelijk ook naar 8.8.8.8 gaat, toevallig met dezelfde bronpoort:

Gebruiker	Origineel	Na PAT
a1_emp	10.0.100.11 : 40000	198.51.100.9 : 40000
b1_emp	10.0.100.21 : 40000	198.51.100.9 : 40001
Bij b1_emp ziet conntrack dat .9:40000 al bezet is en kiest een andere poort. Zo kan conntrack elk antwoord aan de juiste gebruiker teruggeven:

komt er een antwoord naar .9:40000, dan gaat het naar a1_emp;
komt er een antwoord naar .9:40001, dan gaat het naar b1_emp.
Dit stuk heb ik niet live laten zien. Wil je het zelf zien, doe dan test 3 (500 gebruikers) en kijk naar de conntrack-tabel: daar staan dan 500 regels met .9 als adres.

In drie zinnen
PAT: Faucet vervangt het privéadres door 198.51.100.9 en onthoudt in conntrack welke poort bij welke gebruiker hoort.
.9 staat nergens op een interface: het is een adres dat alleen in de conntrack-tabel van Faucet bestaat.
De /28 is gesplitst, zodat .9 buiten de kabel naar de ISP valt. Daardoor stuurt isp_a antwoorden naar .9 via een route naar Faucet (.2), in plaats van zelf te zoeken naar een apparaat dat niet bestaat.


Wat is NFV?
NFV staat voor Network Function Virtualization. Vroeger kocht je voor elke netwerkfunctie een apart apparaat: een firewall, een bandbreedtebegrenzer, een switch met port security. Met NFV doe je die functies in software.

NFV 1: rate limiting voor guests
Stap 1: de meter definiëren
CONF/IPV4_Topo_opdracht2.yml:32-41:


meters:
    guest-rate-limit:
        meter_id: 1
        entry:
            flags: [KBPS, BURST, STATS]
            bands:
                - type: DROP
                  rate: 1000          # 1000 kbit/s = 1 Mbit/s
                  burst_size: 100     # 100 kbit mag even "te veel"
Onderdeel	Betekenis
meter_id: 1	het nummer van de meter op de switch
KBPS	de snelheid wordt in kilobits per seconde gemeten
BURST	een korte piek boven de limiet mag
STATS	de switch houdt tellers bij, zodat je het kunt bewijzen
type: DROP	alles boven 1 Mbit/s wordt gedropt
burst_size: 100	een buffer van 100 kbit voor korte pieken
Een meter werkt als een emmer met een gat erin: er stroomt 1 Mbit/s uit. Komt er meer in dan eruit kan, dan loopt de emmer over en wordt het teveel weggegooid. TCP merkt die verloren pakketten en gaat vanzelf langzamer zenden, tot ongeveer 1 Mbit/s.

Stap 2: de meter gebruiken in de guest-ACL
De meter doet niets totdat een regel ernaar verwijst. In guest-fw:


- rule:
      description: "Bestaande verbinding, met 1 Mbit/s-limiet"
      ct_state: 0x22/0x22
      actions: {allow: 1, meter: guest-rate-limit}
Stap 3: in de flows

table=0, ct_state=+est+trk, ip, in_port="a_f1-eth3"  actions=meter:1, goto_table:1
Elk pakket van een bestaande verbinding dat binnenkomt op de guest-poort (eth3), gaat eerst door meter 1 en daarna pas de rest van de pipeline in.

Stap 4: het pad van een guest-pakket

a1_gst stuurt data ──► a_f1 poort 3 ──► tabel 0: guest-fw
                                           ├─ +est → meter:1 ──► onder 1 Mbit/s? → door
                                           │                 └─► erboven?       → DROP
                                           └─ … rest van de pipeline (VLAN, NAT, routeren)
Waarom zo gedaan
De meter staat op de switch zelf, in hardware of de datapath. De controller hoeft niets per pakket te doen, dus dit schaalt ook bij veel verkeer.
Hij staat op de accesspoort van de guest. Het verkeer wordt begrensd waar het binnenkomt. Het teveel belast de stack en de darkfiber dus niet eens.
Alleen de guest-poorten krijgen de meter. Employee en management houden hun volle snelheid.
Twee beperkingen om te kennen
1. Alleen upload wordt begrensd, waarschijnlijk. De meter zit in acls_in van de guest-poort, dus alleen op verkeer van de guest. Wat de guest downloadt, komt binnen via isp-uplink op a_core, en daar zit geen meter. Ik verwacht dat iperf3 -R (download) dus niet begrensd is; dat laat test 5 zien.

Download ook begrenzen kan, maar dan moet er een meter op de terugweg komen, bijvoorbeeld in isp-uplink voor verkeer naar 10.0.200.0/24. Die meter zou dan op a_core staan en door alle guests samen gedeeld worden.

2. "Per poort" klopt hier toevallig. Een meter hoort bij een switch, niet bij een poort. Op elke verdiepingsswitch zit nu maar één guest-poort, dus 1 Mbit/s per switch is hier gelijk aan 1 Mbit/s per guest. Hang je twee guests aan dezelfde switch, dan delen ze die 1 Mbit/s. Wil je echt per gebruiker begrenzen, dan geef je elke poort een eigen meter.

NFV 2: port security voor management
Wat is het probleem?
Iemand trekt de kabel uit de management-pc en prikt zijn eigen laptop in poort 4. Zonder port security zit die laptop dan in het management-VLAN en mag hij overal bij waar management bij mag.

De oplossing: alleen één vast MAC-adres toestaan
De management-hosts hebben een vast MAC-adres. Dat wordt in de .py ingesteld (IPV4_Topo_opdracht2.py:101-104):


if kind == "mgt":
    mac = "02:00:00:00:30:%d" % number      # a1_mgt → 02:00:00:00:30:11
In de .yml begint elke regel van de management-ACL met dat MAC-adres:


mgt-fw-a1:
    - rule: {eth_src: "02:00:00:00:30:11", eth_type: 0x0806, actions: {allow: 1}}     # ARP
    - rule: {eth_src: "02:00:00:00:30:11", eth_type: 0x0800, ct_state: 0/0x20, ...}   # conntrack
    - …                                                                              # firewallregels
    - rule: {description: "Ander MAC-adres of ander verkeer: droppen", actions: {allow: 0}}
In de flows

table=0, priority=20480, arp, in_port="a_f1-eth4", dl_src=02:00:00:00:30:11  actions=goto_table:1
table=0, priority=20479, ct_state=-trk, ip, in_port="a_f1-eth4", dl_src=02:00:00:00:30:11  actions=ct(...)
…
table=0, priority=0  actions=drop
Elke regel voor poort 4 eist dl_src=02:00:00:00:30:11. Er is geen enkele regel die een ander MAC-adres toestaat.

Stap voor stap: een vreemde laptop op poort 4

laptop (MAC aa:bb:cc:..) prikt in a_f1 poort 4
  → stuurt een ARP: "wie heeft 10.0.30.1?"
  → tabel 0: is er een regel met in_port=eth4 en dl_src=aa:bb:cc:..? → NEE
  → valt door naar de laatste regel → DROP
  → de laptop krijgt niet eens antwoord op ARP en kan dus niets ✗
En met het goede apparaat:


a1_mgt (MAC 02:00:00:00:30:11)
  → ARP → regel "arp, dl_src=…30:11" → door ✓
  → IP  → regel met dl_src=…30:11 → firewall → door ✓
Waarom een aparte ACL per verdieping?
Elke managementpoort heeft een ander toegestaan MAC-adres. a_f1 accepteert …:30:11 en b_f3 …:30:23. Daarom zijn er vijf ACL's: mgt-fw-a1 tot en met mgt-fw-b3. Zet je a1_mgt op poort 4 van b_f3, dan werkt hij daar dus ook niet. Elk apparaat zit vast aan zijn eigen poort.

Waarom zo gedaan
De controle zit op de eerste switch. Een vreemd apparaat komt niet verder dan poort 4. Het bereikt de stack, andere switches of de gateway nooit.
Er wordt gedropt, niet alleen gelogd. Ook ARP wordt geblokkeerd, dus het apparaat kan het netwerk niet eens verkennen.
Het zit in dezelfde ACL als de firewall. Port security en de stateful firewall staan in één regelset. Daardoor kan het MAC-adres nooit om de firewall heen.
Beperking om te kennen
Een MAC-adres is niet geheim. Iemand die het MAC-adres van de management-pc weet, kan zijn eigen laptop dat adres geven (MAC-spoofing) en komt dan wel binnen. Port security op MAC-adres is dus een basismaatregel. In een echt bedrijfsnetwerk zou je daarnaast 802.1X gebruiken: inloggen met certificaat of wachtwoord voordat de poort opengaat.

