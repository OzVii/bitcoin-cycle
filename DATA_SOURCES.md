# Datalähteiden testiraportti

Testattu 2026-10-04 skriptillä `scripts/probe_sources.py` **paikalliselta koneelta (Suomi)**.
GitHub Actionsin (US/Azure) palvelimelta ei voi testata ennen kuin repo on olemassa. Ajetaan sama skripti workflow'ssa vaiheessa 7 ja päivitetään tämä raportti.

## Yhteenveto

| Data | Lähde | Tila | Historia | Huomiot |
|---|---|---|---|---|
| BTC päiväsulku | CoinMetrics `PriceUSD` | ✅ | 2010-07-18 → eilinen | Päivittyy päivän viiveellä |
| MVRV | CoinMetrics `CapMVRVCur` | ✅ | 2010-07-18 → | |
| Markkina-arvo | CoinMetrics `CapMrktCurUSD` | ✅ | 2010-07-18 → | |
| Liikkeeseenlasku USD | CoinMetrics `IssTotUSD` | ✅ | 2010-07-18 → | |
| Tarjonta | CoinMetrics `SplyCur` | ✅ | 2009-01-03 → | Lisäkenttä, helpottaa myyntitasojen laskua |
| Realisoitu arvo | CoinMetrics `CapRealUSD` | ❌ 403 | – | Ei ilmaisessa tasossa. **Ei haittaa:** realisoitu arvo = `CapMrktCurUSD / CapMVRVCur` |
| Viikko-OHLC | Kraken OHLC, interval 10080 | ⚠️ | 2013-10 → (max 720 kynttilää) | **Kraken-viikot alkavat torstaina 00:00 UTC**, eivät maanantaina |
| Päivä-OHLC | Bitstamp `/api/v2/ohlc/btcusd/` step 86400 | ✅ | 2011-09 → tänään | 1000 riviä/sivu, sivutus `start`-parametrilla. Voidaan koostaa maanantaiviikoiksi |
| Päivä-OHLC | Kraken interval 1440 | ⚠️ | vain viim. 720 pv | Kelpaa vain varalähteeksi uusille riveille |
| Hinta (varalla) | CoinGecko `market_chart` | ⚠️ | vain 365 pv ilman avainta | `days=max` → 401. Kelpaa vain varalähteeksi uusille riveille |
| Binance viikko | `api.binance.com` | ✅ täältä | 2017-08 → | Todennäköisesti 451 US-palvelimilta, ei käytetä |
| Fear & Greed | alternative.me `/fng/?limit=0` | ✅ | 2018-02-01 → tänään | Kentät: value, value_classification, timestamp |
| M2 | FRED `M2SL` | ✅ (CSV ilman avainta) | 1959-01 → 2026-08 | Kuukausidata, ~1 kk viive |
| Dollari-indeksi | FRED `DTWEXBGS` | ✅ (CSV ilman avainta) | 2006-01 → 2026-09-25 | Päivädata, ~1 vko viive |
| FRED API (avaimella) | `api.stlouisfed.org` | ensisijainen GitHubissa | – | Secret `FRED_API_KEY`. CSV-vienti aikakatkaistui GitHub Actionsista (testi 2026-10-08), joten API on ensisijainen ja CSV varalla |

Viimeisimmät arvot (2026-10-03): PriceUSD ≈ 84 756 $, MVRV ≈ 1,58, F&G = 65.

## Havainnot ja vaikutukset suunnitelmaan

1. **Viikkokynttilöiden kohdistus.** Speksin mukaan viikko sulkeutuu maanantaina 00:00 UTC, mutta Krakenin viikkokynttilät on kohdistettu torstaihin. Ehdotus: haetaan Bitstampin päivä-OHLC (koko historia 2011 alkaen, kertaalleen) ja koostetaan siitä maanantai–sunnuntai-viikot itse. Kraken jää varalähteeksi päiväriveille.
2. **Indikaattorien laskenta** tehdään CoinMetricsin `PriceUSD`-päiväsulusta, kuten speksissä. Kaavion kynttilät tulevat Bitstampista. Pörssikohtaiset sulkuhinnat eroavat hieman CoinMetricsin referenssihinnasta (tyypillisesti alle 0,5 %).
3. **Realisoitu hinta** = `PriceUSD / CapMVRVCur` toimii. Tarjonta saadaan suoraan `SplyCur`-kentästä, joten myyntitasot = (realisoitu arvo + k × σ) / SplyCur.
4. **Historian pituus vs. backtest.** 200 viikon SMA vaatii 1400 päivää, joten se on saatavilla vasta noin 2014-05 alkaen (data alkaa 2010-07). Backtest vuodesta 2014 on mahdollinen, mutta arvostuskerros on täysi vasta kesästä 2014. Fear & Greed puuttuu ennen 2018-02, joten sen paino jaetaan muille.
5. **FRED toimii ilman API-avainta** CSV-viennin (`fredgraph.csv`) kautta. Secretin voi siis jättää kokonaan pois, tai käyttää API:a ensisijaisena ja CSV:tä varalla.
6. **Viiveet:** CoinMetrics päivittyy noin vuorokauden viiveellä. Jos eilinen ei ole vielä mukana aamun 05:23 UTC -ajossa, iltaajo (17:23 UTC) hakee sen. M2 julkaistaan noin kuukauden viiveellä, mikä riittää makrokerrokselle.
