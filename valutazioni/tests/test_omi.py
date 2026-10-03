from app import omi


def test_scelte():
    assert omi.codice_zona("zona B1") == "B1"
    assert omi.codice_zona("D11 - Periferica") == "D11"
    assert omi.nome_provincia("tv") == "TREVISO"
    opz = [("1", "2024 - Semestre 2"), ("2", "2025 - Semestre 1"), ("3", "2025 - Semestre 2"), ("4", "2023 - 1")]
    assert omi.scegli(opz, "", "semestre") == ("3", "2025 - Semestre 2")
    zone = [("a", "B10/Centrale/ALTRO"), ("b", "B1/Centrale/CENTRO STORICO"), ("c", "C1/Semicentrale/B1 vicino")]
    assert omi.scegli(zone, "B1", "zona") == ("b", "B1/Centrale/CENTRO STORICO")
    assert omi.scegli([("x", "TREVISO (TV)"), ("y", "VENEZIA")], "Treviso", "comune") == ("x", "TREVISO (TV)")
    assert omi.scegli([("x", "MOGLIANO VENETO")], "Treviso", "comune") is None


def test_ricerca_su_sito_simulato(tmp_path):
    import sito_omi_finto
    r = omi.cerca("TV", "Treviso", "B1", tmp_path, configura=sito_omi_finto.configura)
    assert r.semestre == "2° semestre 2025"
    assert r.destinazioni == ["Residenziale", "Commerciale"]
    assert len(r.immagini) == 2 and all(p.exists() for p in r.immagini)
    assert r.logo and r.logo.exists()
    res, com = r.tabelle
    assert res["destinazione"] == "Residenziale" and com["destinazione"] == "Commerciale"
    assert ("Codice di zona", "B1") in res["info"] and res["semestre"] == "2° semestre 2025"
    assert res["colonne"] == 8 and res["intestazione"] == 2
    assert [c["t"] for c in res["celle"] if c["r"] == 2][:4] == ["Abitazioni civili", "NORMALE", "2100", "2900"]
    assert (tmp_path / "auto_OMI.json").exists()


def test_zona_inesistente(tmp_path):
    import pytest
    import sito_omi_finto
    with pytest.raises(omi.ErroreOMI, match="Zona"):
        omi.cerca("TV", "Treviso", "Z9", tmp_path, destinazioni=["Residenziale"],
                  configura=sito_omi_finto.configura)
    assert (tmp_path / "errore_OMI.png").exists()


def test_zona_per_nome():
    import pytest
    zone = [("a", "B1/Centrale/CENTRO STORICO ALL'INTERNO DELLE MURA"), ("b", "C1/Semicentrale/SAN ZENO"),
            ("c", "D2/Periferica/SAN ZENO SUD"), ("d", "C2/Semicentrale/SANT'ANTONINO")]
    assert omi.scegli(zone, "Centro storico", "zona")[0] == "a"
    assert omi.scegli(zone, "San Zeno", "zona")[0] == "b"          # nome esatto preferito
    assert omi.scegli(zone, "zona B1", "zona")[0] == "a"
    with pytest.raises(omi.ErroreOMI, match="più zone"):
        omi.scegli(zone, "Semicentrale", "zona")
    assert omi.scegli(zone, "Fiera", "zona") is None


def test_ricerca_zona_per_nome_su_sito_simulato(tmp_path):
    import sito_omi_finto
    r = omi.cerca("TV", "Treviso", "Centro storico", tmp_path, destinazioni=["Residenziale"],
                  configura=sito_omi_finto.configura)
    assert ("Codice di zona", "B1") in r.tabelle[0]["info"]


def test_filtra_righe_con_celle_unite():
    from app import ricerca_omi
    from app.omi import griglia
    th = lambda t, cs=1, rs=1: {"t": t, "cs": cs, "rs": rs, "th": True}    # noqa: E731
    td = lambda t, rs=1: {"t": t, "cs": 1, "rs": rs, "th": False}         # noqa: E731
    g = griglia([[th("Tipologia"), th("Stato"), th("Min"), th("Max")],
                 [td("Abitazioni civili", rs=2), td("NORMALE"), td("2300"), td("2900")],
                 [td("OTTIMO"), td("3400"), td("4300")],
                 [td("Box"), td("NORMALE"), td("1500"), td("2500")]])
    righe = ricerca_omi.righe_dati(g)
    assert [r["celle"][:2] for r in righe] == [["Abitazioni civili", "NORMALE"], ["Abitazioni civili", "OTTIMO"],
                                                ["Box", "NORMALE"]]
    f = ricerca_omi.filtra(g, [righe[1]["r"]])            # tolta "Abitazioni civili - OTTIMO"
    assert f["righe"] == 3
    civili = next(c for c in f["celle"] if c["t"] == "Abitazioni civili")
    assert civili["rs"] == 1 and "OTTIMO" not in [c["t"] for c in f["celle"]]
    f = ricerca_omi.filtra(g, [righe[0]["r"], righe[1]["r"]])
    assert "Abitazioni civili" not in [c["t"] for c in f["celle"]]
    assert next(c for c in f["celle"] if c["t"] == "Box")["r"] == 1
