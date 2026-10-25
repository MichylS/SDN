Context – Migratie naar SDN: fase 2
Na het succesvol opleveren van de basis-SDN-topologie is het projectteam gevraagd om het netwerk verder te brengen naar een productiewaardige staat. Dit houdt in dat het netwerk naast IPv4 ook volledig IPv6-compatibel moet zijn, en dat er een geavanceerde firewall moet worden toegepast.

Het CvB verwacht een netwerk waarin stateful firewalling, toegangsisolatie tussen gebruikers, en ISP-integratie via ipv4 IPv6 zijn geïmplementeerd. Je blijft werken in Mininet met de Faucet-controller, maar voert nu geavanceerdere regels en policies in. denk hierbij aan de limitaties van het /28 blok.

Beschikbare infrastructuur gebouw A en B
De SDN-infrastructuur moet worden uitgerold over twee gebouwen: Gebouw A en Gebouw B. Beide gebouwen beschikken over een eigen interne netwerkinfrastructuur geschikt voor (openflow), een paar servers en een externe verbinding met een ISP. De verbinding tussen de gebouwen wordt gerealiseerd via een onderlinge darkfiber.

Gebouw A
Verdiepingen: 2
Switches: Elke verdieping beschikt over een eigen L2/L3-switch die geplaatst is in een lokale patchkast. Deze switches ondersteunen VLAN-configuratie en SDN-protocol (OpenFlow 1.3).
Netwerkbackbone: De switches zijn verbonden met de centrale patchkast waar ook de uplink naar de darkfiber aanwezig is.
Servervoorziening: Een 1U rackserver is aanwezig in de centrale patchkast en is beschikbaar voor het draaien van de Faucet-controller.
Externe connectiviteit: Gebouw A beschikt over een eigen lijn naar een ISP, wat onafhankelijke internettoegang mogelijk maakt.
Iedere patchkast kan binnen het gebouw doorgepatcht worden.
Gebouw B
Verdiepingen: 3
Switches: Ook in Gebouw B beschikt elke verdieping over een eigen L2/L3-switch , centraal geplaatst in een patchkast per etage.
Netwerkbackbone: Alle verdiepingsswitches zijn aangesloten op een centrale patchkast op de begane grond. Deze patchkast is verbonden met de darkfiber naar Gebouw A.
Servervoorziening: Ook Gebouw B beschikt over een eigen 1U-server voor het hosten van een lokale Faucet-controller of redundante controlleromgeving.
Externe connectiviteit: Gebouw B heeft net als Gebouw A een eigen verbinding met een ISP. Deze lijnen kunnen redundantie bieden of gebruikt worden voor load balancing of segmentatie op netwerkniveau.
Iedere patchkast kan binnen het gebouw doorgepatcht worden.
Opdrachtomschrijving – IPv6 en stateful security
Je breidt het bestaande SDN-netwerk uit met:

Volledige IPv6-functionaliteit per VLAN
Een stateful firewall voor zowel IPv4 als IPv6 verkeer
Strikte toegangsbeperkingen tussen gast-clients
Doelstellingen:
Voorzie elk VLAN van een eigen IPv6-subnet met routeerbaarheid vanaf de ISP.
Implementeer een stateful firewall die:
Alleen verbindingen toestaat die van binnenuit het netwerk zijn gestart
Alle andere inkomende verbindingen blokkeert
Voorkom onderlinge communicatie tussen studenten:
apparaten binnen het gastnetwerk mogen enkel communiceren met de isp, niet onderling.
Beschrijf concreet en technisch:
Waarom je een bepaalde firewalloplossing gebruikt
Welke OpenFlow-structuren je inzet
Hoe je de stateful logica hebt opgelost binnen SDN-beperkingen
Minimale eisen:
Werkend ipv4 en IPv6 voor elke VLAN (inclusief ISP-interface)
Filteringregels voor:
Inkomend/outgoing verkeer per VLAN
Richting (initiated inside vs. unsolicited traffic)
Mininet-omgeving met aangepaste topologie en flowregels
Er moeten minimaal 500 concurrent users naar de isp kunnen pingen (NAT)
Heldere uitleg en verantwoording van ontwerpkeuzes
Oplevering:
Werkend prototype in Mininet
YAML-configuraties voor Faucet + eventuele extra componenten (bijv. ACLs of policy rules)
Uitlegdocument met:
Netwerktekening
Per feature de overwegingen en werking
Screenshots of dumps van relevante flow tables
Eventuele zelfgeschreven scripts/configuratiehulp