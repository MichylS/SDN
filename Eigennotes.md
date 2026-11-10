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