1. Netwerkinterfaces en IP-adressen
Commando	Wat doet het?
isp_a ip addr	Toont alle netwerkinterfaces en IP-adressen van isp_a.
isp_a ip addr show	Hetzelfde, maar explicieter uitgeschreven.
isp_a ip link	Toont alle netwerkinterfaces en hun status (UP/DOWN).
isp_a ip link show	Toont uitgebreide informatie over netwerkinterfaces.
isp_a ip -br addr	Toont interfaces en IP-adressen in een compact overzicht.
isp_a ip -br link	Toont interfaces en hun status in een compact overzicht.

2. Routing en gateways
Commando	Wat doet het?
isp_a ip route	Toont de routingtabel van isp_a.
isp_a ip route show	Toont alle bekende routes.
isp_a ip route get 8.8.8.8	Laat zien welke route wordt gebruikt om 8.8.8.8 te bereiken.
isp_a ip route add default via 192.168.2.254	Voegt een standaardgateway toe.
isp_a ip route del default	Verwijdert de standaardgateway.
isp_a ip neigh	Toont bekende IP- en MAC-adreskoppelingen (ARP/neighbour table).

3. Verbinding testen
Commando	Wat doet het?
isp_a ping 192.168.2.1	Test of isp_a een ander apparaat kan bereiken.
isp_a ping -c 4 192.168.2.1	Stuurt 4 ping-pakketten en stopt daarna.
isp_a traceroute 8.8.8.8	Toont via welke routers het verkeer loopt.
isp_a tracepath 8.8.8.8	Alternatief voor traceroute.
isp_a ip neigh show	Controleert welke apparaten via ARP bekend zijn.

4. Netwerkconfiguratie aanpassen
Commando	Wat doet het?
isp_a ip addr add 192.168.2.10/24 dev eth0	Stelt een extra IP-adres in op eth0.
isp_a ip addr del 192.168.2.10/24 dev eth0	Verwijdert een IP-adres van eth0.
isp_a ip link set eth0 up	Zet netwerkinterface eth0 aan.
isp_a ip link set eth0 down	Zet netwerkinterface eth0 uit.
isp_a ip route flush cache	Leegt de routingcache.

5. Mininet-specifieke commando's
Deze voer je rechtstreeks uit bij de mininet> prompt.
Commando	Wat doet het?
nodes	Toont alle hosts, switches en controllers.
net	Toont hoe alle apparaten met elkaar verbonden zijn.
dump	Toont uitgebreide informatie over alle Mininet-nodes.
links	Toont alle verbindingen tussen apparaten.
hosts	Toont alle hosts.
switches	Toont alle switches.
controllers	Toont alle controllers.
pingall	Test de verbinding tussen alle hosts.
h1 ping h2	Test de verbinding tussen h1 en h2.
iperf h1 h2	Meet de netwerkdoorvoer tussen h1 en h2.
exit	Sluit de Mininet CLI af.

