Context – Migratie naar SDN: fase 1
Het College van Bestuur (CvB) heeft het intern IT-team opdracht gegeven om de bestaande, verouderde Cisco-netwerkinfrastructuur te vervangen door een SDN-oplossing. De keuze is gemaakt om de migratie volledig in eigen beheer uit te voeren vanwege kostenbesparing.

Als netwerkengineer ben jij verantwoordelijk voor de ontwikkeling van een eerste werkend prototype van het SDN-netwerk, gericht op basisconnectiviteit, segmentatie via VLANs en inzet van NFV-componenten. Dit proof of concept dient als bewijs van technische haalbaarheid én als fundament voor latere uitbreidingen.

Opdrachtomschrijving – Bouw een functioneel basisnetwerk
Je bouwt in Mininet een SDN-netwerk dat functioneel gescheiden is in meerdere VLAN’s, beheerd door de Faucet-controller. Het netwerk simuleert de volledige officestructuur inclusief netwerkbeperkingen, en wordt ontworpen met schaalbaarheid en beheerbaarheid in het achterhoofd.

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
Switches: Ook in Gebouw B beschikt elke verdieping over een eigen L2/L3-switch, centraal geplaatst in een patchkast per etage.
Netwerkbackbone: Alle verdiepingsswitches zijn aangesloten op een centrale patchkast op de begane grond. Deze patchkast is verbonden met de darkfiber naar Gebouw A.
Servervoorziening: Ook Gebouw B beschikt over een eigen 1U-server voor het hosten van een lokale Faucet-controller of redundante controlleromgeving.
Externe connectiviteit: Gebouw B heeft net als Gebouw A een eigen verbinding met een ISP. Deze lijnen kunnen redundantie bieden of gebruikt worden voor load balancing of segmentatie op netwerkniveau.
Iedere patchkast kan binnen het gebouw doorgepatcht worden.
Doelstellingen:
Creëer een werkende netwerkopzet met een employee-, gast- en management-netwerk.
Zorg voor correcte VLAN-segmentatie en toon aan dat netwerken onderling gescheiden zijn.
Simuleer schaalbaarheid: het netwerk moet minimaal 500 simultaan actieve gebruikers kunnen ondersteunen.
Implementeer een oplossing voor de beperking dat er slechts een /28 publiek subnet beschikbaar is.
Implementeer minimaal twee NFV-functionaliteiten:
Rate limiting voor het gastennetwerk
Ethernet port security voor het management VLAN
Toon via Faucet-configuraties en flow entries aan hoe filtering wordt toegepast.
Onderbouw je ontwerpkeuzes met technische argumenten – “omdat het werkt” is niet voldoende.
Minimale eisen:
Gebruik van Mininet met eigen topologie
Faucet-controller met gestructureerde YAML-configuratie
Werkende VLAN-segmentatie
Duidelijke demonstratie van NFV-functionaliteit
Heldere toelichting van de Flow Entries met uitleg over:
Matching criteria
Acties
Verdeling over tabellen
Oplevering:
Werkende Mininet-topologie met Faucet-configuraties
Een portfolio waarin je uitlegt:
Hoe je netwerk is opgebouwd
Welke keuzes je hebt gemaakt en waarom
Hoe je segmentatie en NFV hebt geïmplementeerd
Screenshots of dumps van flow tables (via dpctl dump-flows of vergelijkbaar)
Diagram of schematische netwerktekening