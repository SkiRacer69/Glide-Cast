"""
FIS Alpine World Cup Venue Altitude Data
All values sourced directly from FIS race result pages (fis-ski.com).
elev_ft = highest start altitude across all disciplines (converted from meters × 3.28084, rounded)
finish_ft = finish altitude in feet
starts_ft = per-discipline start altitudes in feet

Sources cited as: raceid=XXXXXX, Homologation Number: XXXXX/XX/XX
NOT_FOUND = no FIS WC race record with altitude data found after searching 2009–2025 calendars
"""

import math

def m_to_ft(m):
    return round(m * 3.28084)

FIS_VENUE_ALTITUDES = {

    # 1. Soldeu (AND) — GS, SL (Men's and Women's)
    # W GS: raceid=118480, Homol 12395/08/17; W SL: raceid=118481, Homol 12396/08/17
    # M GS: raceid=114130, Homol 12395/08/17; M SL: raceid=114132, Homol 12396/08/17
    # M DH (Finals): raceid=114125, Homol 12968/11/18; M SG: raceid=114127, Homol 12969/11/18
    "soldeu": {
        "elev_ft": m_to_ft(2435),   # M DH Finals start
        "finish_ft": m_to_ft(1725), # DH/SG finish (Finals 2023)
        "starts_ft": {
            "DH_M": m_to_ft(2435),  # raceid=114125
            "SG_M": m_to_ft(2325),  # raceid=114127
            "GS_M": m_to_ft(2265),  # raceid=114130
            "SL_M": m_to_ft(2037),  # raceid=114132
            "GS_W": m_to_ft(2187),  # raceid=118480
            "SL_W": m_to_ft(2047),  # raceid=118481
        },
    },

    # 2. Altenmarkt-Zauchensee (AUT) — DH, SuperG (Women's)
    # DH: raceid=118465, Homol 13591/05/20; SG: raceid=118349, Homol 13592/05/20
    "altenmarkt_zauchensee": {
        "elev_ft": m_to_ft(2176),   # DH start
        "finish_ft": m_to_ft(1380),
        "starts_ft": {
            "DH": m_to_ft(2176),    # raceid=118465
            "SG": m_to_ft(1875),    # raceid=118349
        },
    },

    # 3. Flachau (AUT) — SL (Women's)
    # SL: raceid=122810, Homol 13835/11/20
    "flachau": {
        "elev_ft": m_to_ft(1169),
        "finish_ft": m_to_ft(960),
        "starts_ft": {
            "SL": m_to_ft(1169),    # raceid=122810
        },
    },

    # 4. Hinterstoder (AUT) — GS (Men's); SL: NOT_FOUND in WC (venue only held SG/GS events)
    # GS: raceid=100113, Homol 11981/01/16; SG: raceid=100158, Homol 12253/12/16
    "hinterstoder": {
        "elev_ft": m_to_ft(1292),   # SG start
        "finish_ft": m_to_ft(646),
        "starts_ft": {
            "SG": m_to_ft(1292),    # raceid=100158 (2020 event)
            "GS": m_to_ft(1072),    # raceid=100113
            "SL": "NOT_FOUND",      # No WC SL ever held at Hinterstoder (2009–2025)
        },
    },

    # 5. Kitzbühel (AUT) — DH, SuperG, SL (Men's)
    # DH: raceid=122820, Homol 14579/09/22; SG: raceid=122819, Homol 14580/09/22
    # SL: raceid=122821, Homol 12647/12/17
    "kitzbuehel": {
        "elev_ft": m_to_ft(1665),
        "finish_ft": m_to_ft(805),
        "starts_ft": {
            "DH": m_to_ft(1665),    # raceid=122820
            "SG": m_to_ft(1345),    # raceid=122819
            "SL": m_to_ft(1004),    # raceid=122821
        },
    },

    # 6. Mayrhofen (AUT) — SL (Men's): NOT_FOUND in WC calendars 2009–2025
    "mayrhofen": {
        "elev_ft": "NOT_FOUND",
        "finish_ft": "NOT_FOUND",
        "starts_ft": {
            "SL": "NOT_FOUND",      # No WC race record found for Mayrhofen
        },
    },

    # 7. Pitztal (AUT) — SL, GS (glacier opener): NOT_FOUND in WC calendars 2009–2025
    "pitztal": {
        "elev_ft": "NOT_FOUND",
        "finish_ft": "NOT_FOUND",
        "starts_ft": {
            "GS": "NOT_FOUND",
            "SL": "NOT_FOUND",
        },
    },

    # 8. Saalbach (AUT) — DH, SuperG, GS, SL (2024/2025 Worlds)
    # M DH: raceid=118505, Homol 15272/01/24; W DH: raceid=118504
    # M SG: raceid=118503, Homol 15273/01/24; W SG: raceid=118502
    # M GS: raceid=118495, Homol 14862/01/23; W GS: raceid=118496
    # M SL: raceid=118497, Homol 15305/01/24; W SL: raceid=118494
    "saalbach": {
        "elev_ft": m_to_ft(1830),
        "finish_ft": m_to_ft(1070),
        "starts_ft": {
            "DH_M": m_to_ft(1830),  # raceid=118505
            "DH_W": m_to_ft(1830),  # raceid=118504
            "SG_M": m_to_ft(1627),  # raceid=118503
            "SG_W": m_to_ft(1627),  # raceid=118502
            "GS_M": m_to_ft(1510),  # raceid=118495
            "GS_W": m_to_ft(1458),  # raceid=118496
            "SL_M": m_to_ft(1279),  # raceid=118497
            "SL_W": m_to_ft(1279),  # raceid=118494
        },
    },

    # 9. Schladming (AUT) — SL, GS (Men's)
    # SL: raceid=122826, Homol 13699/10/20; GS: raceid=122827, Homol 13633/09/20
    "schladming": {
        "elev_ft": m_to_ft(1050),
        "finish_ft": m_to_ft(744),
        "starts_ft": {
            "SL": m_to_ft(1050),    # raceid=122826
            "GS": m_to_ft(958),     # raceid=122827
        },
    },

    # 10. Semmering (AUT) — GS, SL (Women's)
    # GS: raceid=123079, Homol 15622/12/24; SL: raceid=123080, Homol 15623/12/24
    "semmering": {
        "elev_ft": m_to_ft(1335),
        "finish_ft": m_to_ft(1020),
        "starts_ft": {
            "GS": m_to_ft(1335),    # raceid=123079
            "SL": m_to_ft(1230),    # raceid=123080
        },
    },

    # 11. Sölden (AUT) — GS (season opener, M and W)
    # GS W: raceid=122760, GS M: raceid=122761, Homol 14044/07/21
    "soelden": {
        "elev_ft": m_to_ft(3040),
        "finish_ft": m_to_ft(2670),
        "starts_ft": {
            "GS_W": m_to_ft(3040),  # raceid=122760
            "GS_M": m_to_ft(3040),  # raceid=122761
        },
    },

    # 12. Bansko (BUL) — DH, SuperG (Women's), GS, SL (Men's)
    # W DH: raceid=100043, Homol 13498/01/20; W SG: raceid=100064, Homol 12084/10/16
    # M GS: raceid=118558, Homol 12429/10/17; M SL: raceid=118559, Homol 15013/09/23
    "bansko": {
        "elev_ft": m_to_ft(2415),   # W DH start
        "finish_ft": m_to_ft(1610), # W DH/SG finish
        "starts_ft": {
            "DH_W": m_to_ft(2415),  # raceid=100043
            "SG_W": m_to_ft(2215),  # raceid=100064
            "GS_M": m_to_ft(2060),  # raceid=118558
            "SL_M": m_to_ft(1830),  # raceid=118559
        },
    },

    # 13. Spindlerův Mlýn (CZE) — SL, GS (Women's)
    # SL: raceid=114202, Homol 13683/10/20; GS: raceid=95583, Homol 9617/09/10
    "spindleruv_mlyn": {
        "elev_ft": m_to_ft(1140),   # GS start
        "finish_ft": m_to_ft(757),
        "starts_ft": {
            "SL": m_to_ft(944),     # raceid=114202
            "GS": m_to_ft(1140),    # raceid=95583
        },
    },

    # 14. Levi (FIN) — SL (Men's and Women's)
    # SL W: raceid=122762, SL M: raceid=122763, Homol 13222/09/19
    "levi": {
        "elev_ft": m_to_ft(438),
        "finish_ft": m_to_ft(258),
        "starts_ft": {
            "SL_W": m_to_ft(438),   # raceid=122762
            "SL_M": m_to_ft(438),   # raceid=122763
        },
    },

    # 15. Ruka (FIN) — SL, GS (Men's): NOT_FOUND in WC calendars 2009–2025
    "ruka": {
        "elev_ft": "NOT_FOUND",
        "finish_ft": "NOT_FOUND",
        "starts_ft": {
            "SL": "NOT_FOUND",
            "GS": "NOT_FOUND",
        },
    },

    # 16. Chamonix (FRA) — SL, GS (Men's Les Houches); DH historically
    # DH: raceid=82820 (2016), Homol 10435/01/12; SL: raceid=118557 (2024), Homol 13526/01/20
    # GS: NOT_FOUND (Chamonix M WC only held DH and SL; no GS found in calendars)
    "chamonix": {
        "elev_ft": m_to_ft(1880),   # DH start
        "finish_ft": m_to_ft(985),  # SL finish; DH finish=1030m
        "starts_ft": {
            "DH": m_to_ft(1880),    # raceid=82820
            "SL": m_to_ft(1169),    # raceid=118557
            "GS": "NOT_FOUND",      # No WC GS at Chamonix found in WC records
        },
    },

    # 17. Courchevel (FRA) — SL, GS (Women's)
    # SL: raceid=123081 (2025), Homol 13407/12/19; GS: raceid=104376 (2021), Homol 13406/12/19
    "courchevel": {
        "elev_ft": m_to_ft(2175),   # GS start
        "finish_ft": m_to_ft(1805), # SL; GS finish=1815m
        "starts_ft": {
            "GS": m_to_ft(2175),    # raceid=104376
            "SL": m_to_ft(2015),    # raceid=123081
        },
    },

    # 18. Méribel (FRA) — DH, SuperG (Women's and Men's Finals)
    # W DH: raceid=78979 (2015), Homol 10802/12/12; M DH: raceid=78980
    # W SG: raceid=78981 (2015), Homol 10803/12/12; M SG: raceid=78982
    "meribel": {
        "elev_ft": m_to_ft(2249),   # M DH start
        "finish_ft": m_to_ft(1432),
        "starts_ft": {
            "DH_W": m_to_ft(2145),  # raceid=78979
            "DH_M": m_to_ft(2249),  # raceid=78980
            "SG_W": m_to_ft(1960),  # raceid=78981
            "SG_M": m_to_ft(1960),  # raceid=78982
        },
    },

    # 19. Val d'Isère (FRA) — DH, SuperG, GS, SL (Men's)
    # DH: raceid=107381 (2021), Homol 13372/11/19; SG: raceid=107382, Homol 13373/11/19
    # GS: raceid=122781 (2025), Homol 15430/10/24; SL: raceid=122782, Homol 15430/10/24
    "val_disere": {
        "elev_ft": m_to_ft(2705),   # DH start
        "finish_ft": m_to_ft(1810), # DH/SG finish
        "starts_ft": {
            "DH": m_to_ft(2705),    # raceid=107381
            "SG": m_to_ft(2297),    # raceid=107382
            "GS": m_to_ft(2264),    # raceid=122781
            "SL": m_to_ft(2057),    # raceid=122782
        },
    },

    # 20. Garmisch-Partenkirchen (GER) — DH, SuperG, GS, SL (Men's and Women's)
    # W DH: raceid=122824 (2025), Homol 15657/12/24; W SG: raceid=122825, Homol 15658/01/25
    # M DH: raceid=104332 (2021), Homol 13281/11/19; M SG: raceid=104331, Homol 13282/11/19
    # M SL: raceid=109057 (2022), Homol 14259/11/21; M GS: raceid=100147 (2020), Homol 9097/01/09
    "garmisch": {
        "elev_ft": m_to_ft(1490),   # DH start (same for M and W)
        "finish_ft": m_to_ft(750),  # GS finish; DH/SG finish=770m, SL=735m
        "starts_ft": {
            "DH_W": m_to_ft(1490),  # raceid=122824
            "SG_W": m_to_ft(1308),  # raceid=122825
            "DH_M": m_to_ft(1490),  # raceid=104332
            "SG_M": m_to_ft(1308),  # raceid=104331
            "GS_M": m_to_ft(1080),  # raceid=100147
            "SL_M": m_to_ft(942),   # raceid=109057
        },
    },

    # 21. Ofterschwang (GER) — SL, GS (Women's)
    # GS: raceid=91020 (2018), Homol 12490/11/17; SL: raceid=91021, Homol 12491/11/17
    "ofterschwang": {
        "elev_ft": m_to_ft(1300),
        "finish_ft": m_to_ft(920),
        "starts_ft": {
            "GS": m_to_ft(1300),    # raceid=91020
            "SL": m_to_ft(1115),    # raceid=91021
        },
    },

    # 22. Alta Badia (ITA) — GS, SL (Men's Gran Risa)
    # GS: raceid=122789, Homol 12080/10/16; SL: raceid=122790, Homol 12081/10/16
    "alta_badia": {
        "elev_ft": m_to_ft(1868),
        "finish_ft": m_to_ft(1420),
        "starts_ft": {
            "GS": m_to_ft(1868),    # raceid=122789
            "SL": m_to_ft(1610),    # raceid=122790
        },
    },

    # 23. Bormio (ITA) — DH, SuperG (Men's Stelvio)
    # DH: raceid=122793, Homol 14725/11/22; SG: raceid=122794, Homol 14746/11/22
    "bormio": {
        "elev_ft": m_to_ft(2268),
        "finish_ft": m_to_ft(1245),
        "starts_ft": {
            "DH": m_to_ft(2268),    # raceid=122793
            "SG": m_to_ft(1959),    # raceid=122794
        },
    },

    # 24. Cortina d'Ampezzo (ITA) — DH, SuperG (Women's); GS: NOT_FOUND in WC calendars
    # DH: raceid=122813, Homol 15270/12/23; SG: raceid=122814, Homol 15270/12/23
    "cortina": {
        "elev_ft": m_to_ft(2320),   # DH start
        "finish_ft": m_to_ft(1560),
        "starts_ft": {
            "DH": m_to_ft(2320),    # raceid=122813
            "SG": m_to_ft(2195),    # raceid=122814
            "GS": "NOT_FOUND",      # Cortina WC events only list DH and SG (2009–2025)
        },
    },

    # 25. Madonna di Campiglio (ITA) — SL (Men's 3Tre)
    # SL: raceid=122797, Homol 11828/11/15
    "madonna_di_campiglio": {
        "elev_ft": m_to_ft(1725),
        "finish_ft": m_to_ft(1545),
        "starts_ft": {
            "SL": m_to_ft(1725),    # raceid=122797
        },
    },

    # 26. Santa Caterina Valfurva (ITA) — DH, SuperG (Men's, 2017 WC)
    # NOTE: Task listed Women's DH/SG but WC records show Men's only (2017, 2021 GS)
    # M DH: raceid=86824, Homol 11566/12/14; M SG: raceid=86806, Homol 11567/12/14
    "santa_caterina": {
        "elev_ft": m_to_ft(2720),   # M DH start
        "finish_ft": m_to_ft(1745),
        "starts_ft": {
            "DH_M": m_to_ft(2720),  # raceid=86824
            "SG_M": m_to_ft(2395),  # raceid=86806
        },
    },

    # 27. Sestriere (ITA) — SL, GS (Women's)
    # GS: raceid=122774 (2025), Homol 15049/10/23; SL: raceid=122836, Homol 13894/12/20
    "sestriere": {
        "elev_ft": m_to_ft(2400),
        "finish_ft": m_to_ft(2044),
        "starts_ft": {
            "GS": m_to_ft(2400),    # raceid=122774
            "SL": m_to_ft(2250),    # raceid=122836
        },
    },

    # 28. Val Gardena (ITA) — DH, SuperG (Men's Saslong)
    # DH: raceid=122788, Homol 14179/11/21; SG: raceid=122787, Homol 14179/11/21
    "val_gardena": {
        "elev_ft": m_to_ft(2249),
        "finish_ft": m_to_ft(1410),
        "starts_ft": {
            "DH": m_to_ft(2249),    # raceid=122788
            "SG": m_to_ft(2010),    # raceid=122787
        },
    },

    # 29. Kvitfjell (NOR) — DH, SuperG (Men's); GS listed in task is actually at Hafjell
    # DH: raceid=122830, Homol 15104/11/23; SG: raceid=122847, Homol 13734/10/20
    # GS (Hafjell): raceid=122850, Homol 13763/11/20
    "kvitfjell": {
        "elev_ft": m_to_ft(1020),   # DH start
        "finish_ft": m_to_ft(182),
        "starts_ft": {
            "DH": m_to_ft(1020),    # raceid=122830
            "SG": m_to_ft(709),     # raceid=122847
            # GS is at Hafjell (separate venue), listed separately below
        },
    },

    # GS listed for Kvitfjell is actually at Hafjell
    "hafjell": {
        "elev_ft": m_to_ft(644),
        "finish_ft": m_to_ft(273),
        "starts_ft": {
            "GS": m_to_ft(644),     # raceid=122850, Homol 13763/11/20
        },
    },

    # 30. Narvik (NOR) — SL (Men's): NOT_FOUND in WC calendars 2009–2025
    "narvik": {
        "elev_ft": "NOT_FOUND",
        "finish_ft": "NOT_FOUND",
        "starts_ft": {
            "SL": "NOT_FOUND",
        },
    },

    # 31. Jasná (SVK) — GS, SL (Women's WC); DH, SuperG: NOT_FOUND in WC calendars
    # W GS: raceid=118468, Homol 11663/02/15; W SL: raceid=118469, Homol 11664/02/15
    "jasna": {
        "elev_ft": m_to_ft(1650),   # GS start
        "finish_ft": m_to_ft(1250),
        "starts_ft": {
            "GS": m_to_ft(1650),    # raceid=118468
            "SL": m_to_ft(1450),    # raceid=118469
            "DH": "NOT_FOUND",      # No WC DH at Jasna found in WC records 2009–2025
            "SG": "NOT_FOUND",      # No WC SG at Jasna found in WC records 2009–2025
        },
    },

    # 32. Kranjska Gora (SLO) — GS, SL (Men's Vitranc)
    # GS: raceid=122842, Homol 13938/01/21; SL: raceid=122843, Homol 13939/01/21
    "kranjska_gora": {
        "elev_ft": m_to_ft(1278),
        "finish_ft": m_to_ft(843),
        "starts_ft": {
            "GS": m_to_ft(1278),    # raceid=122842
            "SL": m_to_ft(1038),    # raceid=122843
        },
    },

    # 33. Åre (SWE) — DH, SuperG, GS, SL (Men's and Women's)
    # W GS: raceid=122848 (2025), Homol 11801/10/15; W SL: raceid=122849, Homol 12145/11/16
    # W DH: raceid=91050 (2018 Worlds), Homol 12548/11/17; W SG: raceid=91052, Homol 12549/11/17
    # M DH: raceid=91051, Homol 12547/11/17; M SG: raceid=91053, Homol 11800/10/15
    # M GS: raceid=91056, Homol 11801/10/15
    "are": {
        "elev_ft": m_to_ft(1033),   # M DH start
        "finish_ft": m_to_ft(392),  # GS finish; DH/SG/SL finish=396m
        "starts_ft": {
            "DH_W": m_to_ft(852),   # raceid=91050
            "DH_M": m_to_ft(1033),  # raceid=91051
            "SG_W": m_to_ft(901),   # raceid=91052
            "SG_M": m_to_ft(812),   # raceid=91053
            "GS_W": m_to_ft(722),   # raceid=122848
            "GS_M": m_to_ft(692),   # raceid=91056
            "SL_W": m_to_ft(586),   # raceid=122849
        },
    },

    # 34. Adelboden (SUI) — GS, SL (Men's)
    # GS: raceid=122802, Homol 13614/09/20; SL: raceid=122803, Homol 13615/09/20
    "adelboden": {
        "elev_ft": m_to_ft(1730),
        "finish_ft": m_to_ft(1302), # SL finish; GS finish=1310m
        "starts_ft": {
            "GS": m_to_ft(1730),    # raceid=122802
            "SL": m_to_ft(1513),    # raceid=122803
        },
    },

    # 35. Crans-Montana (SUI) — DH, SuperG (Women's)
    # DH: raceid=118485 (2024), Homol 14750/11/22; SG: raceid=118749, Homol 14751/11/22
    "crans_montana": {
        "elev_ft": m_to_ft(2210),
        "finish_ft": m_to_ft(1545),
        "starts_ft": {
            "DH": m_to_ft(2210),    # raceid=118485
            "SG": m_to_ft(2116),    # raceid=118749
        },
    },

    # 36. Lenzerheide (SUI) — DH, SuperG, GS, SL (Men's and Women's Finals 2021)
    # W DH: raceid=104415, Homol 13197/08/19; M DH: raceid=104416 (empty, use TRA=104414)
    # W SG: raceid=104417, Homol 12021/02/16; M SG: raceid=104418
    # M GS: raceid=104421, Homol 11564/12/14; W GS: raceid=104422
    # W SL: raceid=104420, Homol 11565/12/14; M SL: raceid=104423
    "lenzerheide": {
        "elev_ft": m_to_ft(2290),   # DH start
        "finish_ft": m_to_ft(1530), # SL/GS finish; DH/SG finish=1560m
        "starts_ft": {
            "DH_W": m_to_ft(2290),  # raceid=104415
            "DH_M": m_to_ft(2290),  # raceid=104414 (training, 104416 had no data)
            "SG_W": m_to_ft(2160),  # raceid=104417
            "SG_M": m_to_ft(2160),  # raceid=104418
            "GS_W": m_to_ft(1920),  # raceid=104422
            "GS_M": m_to_ft(1920),  # raceid=104421
            "SL_W": m_to_ft(1750),  # raceid=104420
            "SL_M": m_to_ft(1750),  # raceid=104423
        },
    },

    # 37. Meiringen-Hasliberg (SUI) — GS (Men's): NOT_FOUND in WC calendars 2009–2025
    "meiringen_hasliberg": {
        "elev_ft": "NOT_FOUND",
        "finish_ft": "NOT_FOUND",
        "starts_ft": {
            "GS": "NOT_FOUND",
        },
    },

    # 38. Veysonnaz (SUI) — GS, SL (Women's 4 Vallées): NOT_FOUND in WC calendars 2009–2025
    "veysonnaz": {
        "elev_ft": "NOT_FOUND",
        "finish_ft": "NOT_FOUND",
        "starts_ft": {
            "GS": "NOT_FOUND",
            "SL": "NOT_FOUND",
        },
    },

    # 39. Wengen (SUI) — DH, SuperG, SL (Men's Lauberhorn); GS: NOT_FOUND in WC records
    # DH: raceid=122808, Homol 14117/10/21; SG: raceid=122807, Homol 15429/10/24
    # SL: raceid=122809, Homol 13268/11/19
    # NOTE: Task listed GS but WC calendars show only DH, SG, SL at Wengen
    "wengen": {
        "elev_ft": m_to_ft(2315),   # DH start
        "finish_ft": m_to_ft(1285), # SL finish; DH/SG finish=1287m
        "starts_ft": {
            "DH": m_to_ft(2315),    # raceid=122808
            "SG": m_to_ft(2025),    # raceid=122807
            "SL": m_to_ft(1475),    # raceid=122809
            "GS": "NOT_FOUND",      # No WC GS at Wengen found in calendars 2009–2025
        },
    },

    # 40. Zermatt (SUI) — DH (glacier speed); SG, GS: NOT_FOUND (no WC races held yet)
    # M DH: raceid=118510, Homol 14616/10/22; W DH: raceid=118338
    "zermatt": {
        "elev_ft": m_to_ft(3720),   # M DH start (highest start found)
        "finish_ft": m_to_ft(2840),
        "starts_ft": {
            "DH_M": m_to_ft(3720),  # raceid=118510
            "DH_W": m_to_ft(3505),  # raceid=118338
            "SG": "NOT_FOUND",      # No WC SG at Zermatt held yet (2009–2025)
            "GS": "NOT_FOUND",      # No WC GS at Zermatt held yet (2009–2025)
        },
    },
}


# ── Feet conversion reference table ──────────────────────────────────────────
# 1 m × 3.28084 = ft, rounded to nearest integer

if __name__ == "__main__":
    import json

    def safe_ft(v):
        if isinstance(v, str):
            return v
        return v

    for venue, data in FIS_VENUE_ALTITUDES.items():
        print(f"\n{venue.upper()}:")
        for k, v in data.items():
            if k == "starts_ft":
                print(f"  starts_ft:")
                for disc, ft in v.items():
                    print(f"    {disc}: {ft} ft")
            else:
                print(f"  {k}: {v} ft")
