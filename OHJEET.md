# Käyttöohjeet

Kaikki komennot ajetaan `btc-sykli`-kansiosta (PowerShell tai komentokehote). Siirry sinne ensin:

```
cd C:\Users\ossik\Desktop\ClaudeCode\btc-sykli
```

---

## Osa 1: Ajaminen omalla koneella

### 1.1 Ensimmäinen kerta (tehdään vain kerran)

Tarvitset Pythonin (3.11 tai uudempi). Se on jo koneellasi. Asenna kirjastot:

```
python -m pip install -r requirements.txt
```

### 1.2 Datan päivitys

Tuplaklikkaa **`paivita.bat`** tai aja:

```
python scripts\fetch_all.py
python scripts\build.py
```

- `fetch_all.py` hakee vain uudet rivit ja lisää ne `data/`-kansion historiaan.
- `build.py` laskee indikaattorit, pisteet ja vaiheet ja kirjoittaa sivun datan (`site/data/*.json`).
- `paivita.bat` kirjoittaa tulosteen tiedostoon `paivitys.log`. Sieltä näet, jos jokin lähde ei vastannut.

Virallinen signaali muuttuu vain kerran viikossa, kun viikko sulkeutuu (sunnuntai 24:00 UTC). CoinMetrics julkaisee edellisen päivän datan aamulla. Paras päivitysaika on siis maanantaiaamu klo 9 jälkeen Suomen aikaa. Päivittäinen ajo päivittää hinnan ja keskeneräisen viikon esikatselun.

### 1.3 Sivun katselu

Tuplaklikkaa **`nayta.bat`**. Se käynnistää paikallisen palvelimen ja avaa selaimeen osoitteen **http://localhost:8765**. Lopeta sulkemalla musta ikkuna.

(Sivua ei voi avata suoraan tuplaklikkaamalla `index.html`-tiedostoa, koska selain estää datatiedostojen lukemisen ilman palvelinta.)

Sama käsin:

```
python -m http.server 8765 --directory site
```

### 1.4 Automaattinen päivittäinen ajo Windowsissa

**Tarvitset tätä vain, jos et käytä GitHubia** (osa 2). GitHub hoitaa päivittäisen ajon itse, eikä koneesi tarvitse olla päällä.

Luo ajastettu tehtävä, joka ajaa päivityksen joka päivä klo 9.00:

```
schtasks /Create /SC DAILY /ST 09:00 /TN "Bitcoin-sykli" /TR "\"C:\Users\ossik\Desktop\ClaudeCode\btc-sykli\paivita.bat\""
```

- Aja heti testiksi: `schtasks /Run /TN "Bitcoin-sykli"`. Tarkista sitten `paivitys.log`.
- Tarkista tila: `schtasks /Query /TN "Bitcoin-sykli"`
- Poista: `schtasks /Delete /TN "Bitcoin-sykli" /F`

Tehtävä ajetaan vain, kun kone on päällä ja olet kirjautunut sisään. Jos kone on kiinni klo 9, ajo jää väliin. Avaa silloin **Tehtävien ajoitus** (Task Scheduler), etsi tehtävä "Bitcoin-sykli" ja ruksi kohdasta *Asetukset*: "Suorita tehtävä mahdollisimman pian, jos ajoitettu aloitus jäi väliin".

### 1.5 Backtest, testit ja asetusten säätö

```
python scripts\backtest_report.py --md BACKTEST.md
python -m pytest -q tests
```

Kaikki kynnysarvot, painot ja parametrit ovat tiedostossa **`config.json`**. Muokkaa sitä ja aja sitten `python scripts\build.py` (uutta dataa ei tarvitse hakea). Katso vaikutus backtestillä ennen kuin luotat muutokseen.

---

## Osa 2: Julkaisu GitHubiin (ilmainen verkkosivu)

Lopputulos on osoitteessa `https://<käyttäjätunnus>.github.io/<repon-nimi>/`. GitHub päivittää datan kahdesti päivässä, klo 05.23 ja 17.23 UTC (8.23 ja 20.23 Suomen kesäaikaa), vaikka oma koneesi olisi kiinni. GitHub ei takaa ajastettujen ajojen aikaa: ajo voi myöhästyä tai joskus jäädä väliin, ja siksi ajoja on kaksi. Päivityksen voi aina käynnistää myös käsin (*Actions → Run workflow*).

### 2.1 Valmistelut (kerran)

1. Luo tunnus osoitteessa https://github.com, jos sinulla ei vielä ole.
2. Git on jo koneellasi. Kerro sille nimesi ja sähköpostisi (näkyvät committien tekijänä):

   ```
   git config --global user.name "Oma Nimi"
   git config --global user.email "sinun@sahkoposti.fi"
   ```

### 2.2 Luo repo GitHubissa

1. GitHubissa: oikea yläkulma **+** → **New repository**.
2. Nimi esim. `btc-sykli`.
3. Valitse **Public**. Ilmaisella tilillä GitHub Pages toimii vain julkisista repoista: koodi ja data näkyvät kaikille. Sivu on merkitty niin, että hakukoneet eivät indeksoi sitä, mutta kuka tahansa osoitteen tietävä voi avata sen.
4. **Älä** ruksi "Add a README" tai muita valintoja, koska repon pitää olla tyhjä.
5. Paina **Create repository**. Kopioi sivulla näkyvä osoite, muotoa `https://github.com/<käyttäjä>/btc-sykli.git`.

### 2.3 Lähetä koodi GitHubiin

Aja `btc-sykli`-kansiossa (vaihda osoite omaksesi):

```
git init
git add .
git commit -m "Ensimmäinen versio"
git branch -M main
git remote add origin https://github.com/OzVii/bitcoin-cycle.git
git push -u origin main
```

Ensimmäisellä `git push` -kerralla aukeaa selainikkuna, jossa kirjaudut GitHubiin ja hyväksyt yhteyden. Tämä tehdään vain kerran.

### 2.4 Asetukset GitHubissa

Repon sivulla **Settings**:

1. **Pages** (vasen valikko) → *Build and deployment* → **Source: GitHub Actions**.
2. **Actions → General** → alimpana *Workflow permissions* → valitse **Read and write permissions** → **Save**. Tämä tarvitaan, jotta päivitysajo voi tallentaa uudet datarivit repoon.

3. **Secrets and variables → Actions → New repository secret**: nimi `FRED_API_KEY`, arvoksi ilmainen avaimesi osoitteesta https://fredaccount.stlouisfed.org/apikeys. FRED:n avaimeton CSV-vienti ei vastaa GitHubin palvelimilta, joten ilman avainta makrodata (M2, dollari) ei päivity GitHubissa. Muu sivu toimii silti.

Omalla koneella avainta ei tarvita, koska siellä CSV-vienti toimii.

### 2.5 Ensimmäinen ajo

1. Repon sivulla välilehti **Actions**. Jos GitHub kysyy, salli workflow't ("I understand my workflows, go ahead and enable them").
2. Valitse vasemmalta **Päivitä data ja julkaise sivu** → **Run workflow**. Ruksi **"Aja myös datalähteiden testi"** → **Run workflow**.
3. Odota pari minuuttia, kunnes ajo on vihreä ✓. Klikkaa ajoa nähdäksesi lokin. Kohdasta *Datalähteiden testi* näet, toimivatko kaikki lähteet GitHubin palvelimilta. Jos jokin on `[FAIL]`, kerro minulle.
4. Sivun osoite näkyy ajon yhteenvedossa (*deploy*-kohdassa) ja kohdassa **Settings → Pages**.

Tämän jälkeen sivu päivittyy itsestään joka aamu.

### 2.6 Kun käytät GitHubia

- **Poista koneen ajastettu tehtävä**, jos teit sellaisen (kohta 1.4). Muuten molemmat päivittävät dataa ja tulee ristiriitoja.
- GitHub tallentaa joka päivä uuden datan repoon. **Ennen kuin muokkaat mitään omalla koneellasi**, hae uusin versio:

  ```
  git pull
  ```

- Kun olet muokannut esim. `config.json`-tiedostoa, lähetä muutos:

  ```
  git add .
  git commit -m "Säädetty kynnyksiä"
  git push
  ```

  Seuraava ajastettu ajo käyttää uutta asetusta. Voit myös ajaa sen heti: *Actions → Run workflow*.

### 2.7 Ongelmatilanteet

- **Sivulla punainen varoitus "Data is … hours old"**: päivitysajo on epäonnistunut. Katso *Actions*-välilehdeltä punainen ajo ja sen loki.
- **Oranssi varoitus "Source did not respond"**: yksi lähde oli hetkellisesti alhaalla. Sivu käyttää tallennettua dataa, ja tilanne korjaantuu yleensä seuraavana päivänä itsestään.
- **Ajastus lakkasi toimimasta**: GitHub pysäyttää ajastetut ajot, jos repossa ei ole tapahtunut mitään 60 päivään. Päivittäiset datacommitit pitävät repon yleensä aktiivisena. Jos ajot silti loppuvat, *Actions*-välilehdellä on painike **Enable workflow**.
- **`git push` ei mene läpi ("rejected")**: GitHubissa on uudempaa dataa. Aja `git pull` ja sitten `git push` uudelleen.
