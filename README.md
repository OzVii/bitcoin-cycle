# Bitcoin-sykli

Henkilökohtainen staattinen sivu (englanniksi), joka arvioi Bitcoinin syklivaiheen viikkotasolla
mitattavista indikaattoreista ja näyttää porrastetut osto- ja myyntialueet. Ei sijoitusneuvontaa.

**Käyttöohjeet (ajo omalla koneella, päivittäinen ajo ja GitHub-julkaisu): [OHJEET.md](OHJEET.md)**

## Rakenne

```
config.json             kaikki painot, kynnykset ja parametrit
paivita.bat             hakee datan ja laskee sivun (päivittäinen ajo)
nayta.bat               avaa sivun paikallisesti (http://localhost:8765)
data/                   raakahistoria (CSV) + fetch_status.json
scripts/fetch_*.py      datanhaku (inkrementaalinen)
scripts/indicators.py   indikaattorit (kausaaliset)
scripts/pipeline.py     päivä-, viikko- ja kuukausisarjojen kokoaminen
scripts/scoring.py      alipisteet, kerrokset, vaiheet, alueet
scripts/explanations.py sivun tekstit ja ohjepopupit (englanti, sääntöpohjaiset)
scripts/build.py        → site/data/latest.json, site/data/history.json
scripts/backtest_report.py  backtest-yhteenveto (BACKTEST.md)
site/                   index.html, styles.css, app.js
tests/                  yksikkötestit
.github/workflows/      päivittäinen ajo ja Pages-julkaisu
```
