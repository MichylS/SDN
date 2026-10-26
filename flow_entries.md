Wat je wilt zien	Commando
Alle flows van één switch	sh ovs-ofctl -O OpenFlow13 dump-flows a_f1
Eén tabel	sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 table=0
Alle switches in één keer	dpctl dump-flows -O OpenFlow13
Alleen regels van één poort	sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 table=0 | grep 'a_f1-eth3'
Alleen regels met een meter	sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 | grep meter
Alleen drops	sh ovs-ofctl -O OpenFlow13 dump-flows a_f1 | grep drop
De meter zelf	sh ovs-ofctl -O OpenFlow13 dump-meters a_f1
Meterstatistieken	sh ovs-ofctl -O OpenFlow13 meter-stats a_f1
Poortnummers en namen	sh ovs-ofctl -O OpenFlow13 show a_f1