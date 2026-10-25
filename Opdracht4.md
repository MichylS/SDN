In de eerste opdrachten heb je gewerkt aan geintegreerde, lokale, netwerken op basis van openflow. In deze opdracht werk je aan een andere methodiek van Software Defined Networking: overlay networking. Daarmee kun je over bestaande, geografische gescheiden, laag3-netwerken een nieuwe laag 3-netwerk heen leggen. Voor de afnemers van zo'n netwerk lijkt alles dus in 1 subnet te liggen.

Underlay netwerk
Je krijgt binnen het thema de beschikking over een proxmox-omgeving, daarbinnen een aantal VM's, je eigen lokale subnet en een extern, publiek adres. Dit vormt jouw underlay network.

Opdrachtomschrijving
Zoek een medestudent, en bouw samen, over jullie beide underlay netwerken een overlay netwerk (mocht je liever alles zelf willen doen: zorg dan zelf voor 2 gescheiden underlay netwerken). Om dit realiseren moet je eerst zorgen dat de beide underlay netwerken elkaar kunnen bereiken. Bepaal zelf wat je daar voor nodig hebt: niets, een VPN (openvpn/wireguard/andere) en of bijv NAT. Bouw hierover heen je gezamenlijke overlay netwerk (1 subnet). Maak dit overlay netwerk binnen proxmox met de VxLAN techniek, en voer passende testen uit voor connectiviteit, latency en voor performance.

Doelstellingen:
Zorg voor laag 3 connectiviteit tussen de beide underlay netwerken (gerouteerde verbinding). Kies wat nodig is om dit te maken: statische routes, VPN, en/of NAT.
Bepaal aan beide zijden welke VM je VTEP wordt
Bepaal welke MTU optimaal is voor je VxLAN verbinding (interfaces).
Gebruik een VNID, een nieuwe private subnet (voorzien van 172.16.x.y adressen).
Maak binnen proxmox de passende VxLAN definities.
Test je verbinding. Kies zelf de tools, waarmee je connectiviteit, latency en bandbreedte in kaart brengt
Minimale eisen:
Gekoppeld underlay netwerk
Ontwerp van je overlay netwerk (1 subnet)
Werkende connectiviteit (aangetoond met juiste screenshots) binnen je overlay netwerk (alle hosts binnen het overlay network kunnen elkaar pingen)
Berekening van je MTU
Heldere uitleg en verantwoording van ontwerpkeuzes
Heldere beschrijving gekozen testtools en de resultaten daarvan
Oplevering:
Werkend gerouteerde verbinding underlay netwerk
Werkend overlay netwerk (1 subnet)
Instellingen van de VxLAN parematers binnen proxmox
Uitlegdocument met:
Netwerktekening
MTU berekening
Screenshots of dumps van relevante testen
Eventuele zelfgeschreven scripts/configuratiehulp