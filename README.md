# Uppdaterad version – 26 oktober 2026 (kväll)

## Nytt: USA som signalkälla, snabbare månadssparande och belopp med mellanslag

**USA – OECD:s ledande indikator (CLI).** Under *Portföljbacktest → KI-signal → Signalkälla* kan du välja USA i stället
för KI. OECD:s CLI för USA hämtas gratis från FRED (ingen nyckel, OECD-data är öppna). Den svänger bara några enheter
runt 100 och räknas därför om till KI:s skala: 100 = normalt, 110 = en standardavvikelse över normalt. Omräkningen
använder bara historik som fanns vid varje tidpunkt. Samma gränser, återköp, robusthetstest och månadssparande fungerar
som för KI. Publiceringsfördröjningen är 15 dagar som standard (OECD publicerar i mitten av månaden efter). CLI revideras
mycket i efterhand, så backtestet blir något bättre än verkligheten. Nya fördjupningen *USA med längsta historik* kör
modellen på S&P 500-fonden SPY i SEK.

**Månadssparande.** Sparplanen fylls i ett formulär och räknas först när du trycker **Beräkna sparplanen**. Fliken räknar
bara om sin egen del, så det går på någon sekund i stället för att hela appen laddas om vid varje ändring.

**Belopp.** Skriv 10000 eller 10 000 – fälten visar 10 000. Alla kronbelopp och graferna använder mellanslag.

**Verifiering:** 165 automatiska tester passerar (syntetiska data, nätverk spärrat).

---

# Uppdaterad version – 26 oktober 2026

## Nytt: månadssparande, historisk ränta och portföljens egen trend

**💰 Månadssparande (ny flik 5).** Välj när du började spara, startbelopp, månadsbelopp, hur mycket månadsbeloppet
ökar per år och vilken dag i månaden pengarna sätts in. Lägg till hur många större insättningar du vill (bonus, arv,
försäljning …) i en tabell med datum, belopp och valfri beskrivning. Rader utan datum eller belopp räknas inte och visas
med en varning.
Samma sparplan körs i köp och behåll och i KI-strategin (med inställningarna från Portföljbacktestet).

- *Årsavkastning på dina insättningar* (pengaviktad, XIRR) visar hur din sparplan faktiskt gick, med hänsyn till när
  pengarna sattes in. *Tidsviktad årsavkastning* visar strategin oberoende av insättningarna (jämförbar med CAGR).
- När KI har sålt placeras nya insättningar enligt modellens aktuella vikter, alltså delvis på räntekontot.
- *Jämför startår* kör samma plan med start i januari varje år – bra för att se vad det betydde att börja strax före
  en topp eller strax efter en botten. Global (URTH) finns från 2012; för att börja tidigare, välj 100 % Sverige.

**Historisk ränta från Riksbanken (nytt standardläge).** Räntekontot följer den dagliga räntan på 3-månaders
statsskuldväxlar (serie SETB3MBENCH) från Riksbankens öppna API. Det är gratis, kräver ingen nyckel och appen gör ett
anrop per dygn. Du kan dra av en avgift (t.ex. för en räntefond) och välja att räntan aldrig går under 0 % (standard,
som ett sparkonto). Om hämtningen misslyckas används den fasta räntan och en varning visas. Fast ränta och 0 % finns kvar.

**Publiceringsfördröjning 0 dagar som standard.** KI publicerar barometern i slutet av samma månad som den avser, så
0 dagar betyder handel första handelsdagen i nästa månad. Tidigare standard var 20 dagar.

**Trend och RSI på portföljens egna aktier.** Återköpsstegen *Trendvändning* och *Köp (negativ trend)* samt
KI-trendfiltret räknas nu på ett viktat index av portföljens tillgångar i SEK, inte alltid på Sverige. 100 % Global följer
alltså Globals trend. Med 100 % Sverige blir resultatet detsamma som tidigare. Trenden behöver uppvärmning från första
dagen med kursdata (för Global ungefär hösten 2012).

**Verifiering:** 143 automatiska tester passerar (syntetiska data, nätverk spärrat). Appen har körts med syntetiska data
och granskats i webbläsare i dator- och mobilbredd.

---

# Uppdaterad version – 16 oktober 2026

## Nytt: kombinerat återköp, nuläge och förklaring av alla parametrar

**Kombinerat återköp i steg** (Portföljbacktest → "Återköp – kombinerade signaler"). KI säljer som tidigare.
Återköpet kan sedan ske i steg där varje valt villkor köper tillbaka en lika stor del av det sålda:

| Steg | Villkor (alltid efter försäljningen, med föregående handelsdags data) |
|---|---|
| KI-vändning | Vald KI-återköpsregel (A–E) uppfylls |
| VIX-panik | VIX över tröskeln (standard 34); valfritt först när VIX fallit tillbaka under en lugnare nivå (standard 25) |
| Kreditspread vänder | HYG/IEF har fallit minst X % från 1-årstoppen och går åter över sitt glidande medelvärde |
| Köp (negativ trend) | RSI(14) under gränsen medan portföljens egna aktier ligger under SMA 200 (före 26 okt: alltid Sverige) |
| Trendvändning | Portföljens egna aktier har legat under sin trend efter försäljningen och går över igen (månadsvis 10-mån eller dagligen SMA 200) |
| Tidsspärr | Om återköpet inte är klart efter X månader (standard 18) köps resten tillbaka |

- **Trappa eller allt på en gång:** med trappa köper varje steg 1/N; annars köper första uppfyllda villkor allt.
- **Återaktivering:** efter ett fullt återköp kan en ny försäljning först ske när KI har varit nere på eller under
  säljgränsen igen. Annars skulle ett tidigt VIX-återköp direkt följas av en ny försäljning.
- Standardläget är fortfarande **Endast KI-regeln**, så tidigare resultat är oförändrade tills du väljer kombinerat läge.
- Med bara KI-steget påslaget ger motorn exakt samma affärer som den klassiska modellen (testat för regel A, B, C och E).

**Grafer:** egen markör per orsak (▲ KI, ◆ VIX, ■ kredit, ● RSI, △ trend, ★ tidsspärr), gul bakgrund när portföljen är
delvis återköpt, lila prickad linje där tidsspärren skulle slå till, och en separat graf över aktieandelen.
Text vid markörerna kan stängas av (bra i mobilen).

**KI-fliken:** nulägesruta (månader över säljgränsen, modellens läge, VIX, trend Sverige) och valbara lager i KI-grafen:
VIX-panik och Köp (negativ trend) – av/på med egna nivåer. Lagren är bara visning.

**Nya fördjupningar i Portföljbacktestet:**
- Återköpsvarianter: enbart KI, KI + trendfilter, kombinerat och köp och behåll sida vid sida.
- Hur nära toppen sålde modellen? Dagar från topp, missad uppgång, största fall efter sälj och återköpsnivå.
- Robusthetstest: säljgräns 105–118 × 1–4 bekräftande månader som färgkarta. Ett robust val ligger i ett område
  med liknande resultat, inte som en ensam bra ruta.
- Sverige med längsta historik (EWD i SEK så långt valutadata räcker), med samma modell och händelsetabell.
- Publiceringsfördröjning för KI som reglage (0–30 dagar). KI publicerar normalt i slutet av samma månad,
  så 0–5 dagar ligger nära verkligheten; 20 dagar är försiktigt.

**Förklaringar:** varje parameter har en hjälptext (frågetecknet) med *vad den gör* och *vad man ska tänka på*.
Samma texter finns i rutan "📖 Förklaring av parametrarna" i varje flik, som är lättare att läsa i mobilen.

**Gratis data:** allt hämtas fortfarande gratis från Yahoo Finance (yfinance) och KI:s öppna API.
HYG och IEF hämtas bara när kreditsteget är påslaget. Inga API-nycklar behövs.

### Köra på Streamlit Community Cloud (GitHub)

1. Lägg alla filer i mappen `projekt` i ditt GitHub-repo (ersätt de gamla filerna, inklusive den nya `reentry.py`).
2. På share.streamlit.io: välj repot, gren och huvudfil `projekt/app.py` (eller `app.py` om filerna ligger i roten).
3. Välj Python 3.12 under *Advanced settings*. `requirements.txt` installeras automatiskt.
4. Appen fungerar i mobilens webbläsare. Data cachas en timme (KI ett dygn) för att minska anropen till Yahoo.

`requirements.txt` kräver nu Streamlit 1.50 eller senare (`width="stretch"` ersätter `use_container_width`,
som Streamlit håller på att ta bort).

**Verifiering:** 123 automatiska tester passerar (syntetiska data, nätverk spärrat). Appen har dessutom körts med
syntetiska data och granskats i webbläsare i dator- och mobilbredd.

---

# Uppdaterad version – 8 oktober 2026

## Tydligare jämförelser och valbara villkor

- **Testperiod** överst gäller båda backtesten. Välj start/slut eller längsta tillgängliga historik.
  Den tekniska modellen och KI har olika tillgångar/valutor och kan därför ha olika faktisk
  täckning; datumen redovisas. Alla jämförelser inom KI använder samma handelsdagar.
- Bara portföljdelar med positiv vikt begränsar KI-historiken eller kräver prisdata.
  Vid 100 % Sverige döljs den dubblerade Sverigejämförelsen. Annars ligger Sverige under
  Fördjupning, på huvudportföljens period. Saknas täckning visas ingen jämförelse på annan period.
- RSI och VIX kan väljas som alternativa tekniska köpsignaler. MACD-sälj, dess RSI-filter
  och SMA-köpfilter har egna val. Inga köpsignaler ger kassa; utan säljsignal behålls köpen.
  Endast aktiva RSI/MACD-villkor kräver indikatorernas uppvärmning.
- SMA-köpfilter är av som standard. När SMA endast visas påverkar dess uppvärmning inte
  längre den tekniska testperioden. Detta kan ändra resultat jämfört med föregående version.
- Grafvisning styr bara diagram. Aktiv strategi sammanfattas separat.
- **Återställ standard** finns för teknisk modell, KI Konjunktur och KI Portföljbacktest.
  Varje knapp återställer endast den modellens kontroller. Testperioden har egen återställning.
- **KI-trendfilter**, av som standard, väntar efter ett KI-köpbesked tills föregående handelsdags
  Sverigepris i SEK ligger strikt över SMA 200. (Sedan 26 oktober 2026: portföljens egna aktier är trendreferens, se överst.)
  Värden före teststart används för uppvärmning. Saknad SMA tillåter inte köp; nästa sälj avbryter
  väntande återköp. En separat jämförelse visar KI med/utan filtret under samma period.
- KI-startallokering följer det senaste kända beslutet före start. Äldre signaler blir inte
  flera affärer första dagen. Utan tidigare beslut startar KI fullt investerat; teknisk strategi
  startar i kassa. Startallokeringen räknas inte som en avslutad sälj–återköpscykel.
- KI-affärsloggen visar villkor, signalmånad, antaget tillgänglighetsdatum, handelsdatum och
  aktieandel före/efter. Avslutade cykler och längsta tid under tidigare topp visas i huvudvyn.
  Återhämtningstid anges i kalenderdagar och inkluderar en ännu pågående nedgång.

### Granskning av KI-data

KI uppger att databasen uppdateras vid publicering och att indikatorerna revideras varje månad
vid säsongsrensning och standardisering. En förskjuten tidsstämpel tar inte bort revisionsbias.
Den integrerade API-hämtningen innehåller ingen komplett verifierad historik med ursprungliga
publiceringsvärden och publiceringsdatum. Därför behålls den tydligt redovisade schablonen
månadsslut + 20 dagar; den presenteras inte som ett faktiskt historiskt publiceringsdatum.
Handel sker efter den antagna tillgängligheten och trendvillkor använder föregående dags stängning.
Exempelvis publicerades majrapporten 2026 den 28 maj, vilket visar att schablonen kan fördröja signaler.

Källor kontrollerade 8 oktober 2026:
- https://www.konj.se/statistik-och-data/
- https://www.konj.se/publikationer/konjunkturbarometern/2026-09-29-kraftigt-forbattrat-stamningslage-hos-hushallen/
- https://www.konj.se/publikationer/konjunkturbarometern/2026-05-28-oforandrat-stamningslage-men-fler-foretag-forvantar-sig-prisokningar-framover/

---

**Ny återköpsregel i båda KI-flikarna:** välj ”E. KI oförändrat eller stigande efter passerad köpgräns”.
Efter försäljning aktiveras återköp när KI är strikt under köpgränsen. Första efterföljande
oförändrade eller stigande månad ger köp, även över köpgränsen: med gräns 90 ger både
89 → 89 och 89 → 91 köp, medan 89 → 87 inte gör det. Två intilliggande månaders värden
jämförs; saknade månader ger ingen jämförelse över datagapet. Aktiveringen nollställs efter köp.
Det separata golvet används inte för denna regel, och antal bekräftande månader gäller endast sälj.
Regeln ingår också i portföljbacktestets automatiska jämförelse. Handel följer befintlig publiceringsfördröjning.

**Windows:** packa upp hela ZIP-filen och dubbelklicka på `Starta.bat` i mappen `projekt`.
Python 3.11–3.13 behöver vara installerat. Första starten hämtar paketen och kräver internet.
Senare starter återanvänder installationen. Stäng kommandofönstret för att stoppa appen.

**Verifiering (8 oktober):** 102 automatiska tester passerade, inklusive interaktiva Streamlit-tester med syntetiska data.
Signalkopplingar, separat KI-ränta/kostnad, heatmap-isolering, handelsdatum och öppna affärer har testats.
Gränssnitt och tekniska transaktionsmarkörer har dessutom granskats i webbläsare med syntetiska data.
Testerna verifierar inte tillgängligheten hos externa datakällor i realtid.

---

# simpletradingv3 — Trend Heatmap & Kvantanalys

En Streamlit-app för teknisk trendanalys, Konjunkturinstitutets (KI) Barometerindikator
("Konjunkturmodellen") och backtesting — med separata, fristående backtestmotorer för
den tekniska modellen och för KI-portföljstrategin.

⚠️ **Om verktyget och riskerna

Appen är ett experimentellt analys- och utbildningsverktyg. Innehållet är inte personlig investeringsrådgivning eller en rekommendation att köpa eller sälja.

Signaler och backtest bygger på historiska data och förenklade antaganden. Data och beräkningar kan innehålla fel. Historiska resultat garanterar inte framtida avkastning.

Alla investeringar innebär risk och du kan förlora hela eller delar av ditt kapital. Du ansvarar själv för dina investeringsbeslut. Gör en egen, välgrundad bedömning utifrån din ekonomi, dina mål och din risktolerans. Använd inte appen som enda beslutsunderlag.

---

## 1. Vad appen gör

Appen innehåller tre principiellt olika angreppssätt:

1. **Teknisk RSI/VIX/MACD-modell** — kortsiktig, tillgångsspecifik trendmodell för en enskild ticker.
2. **KI/Konjunkturmodellen** — långsiktig, konträr makromodell baserad på KI:s Barometerindikator,
   använd som en **portföljallokeringsstrategi** (aktier vs. räntekonto), inte som en aktiesignal.
3. **Buy & Hold** — passiv referens med samma målvikter och rebalanseringsschema som KI-strategin.

Fyra flikar, grupperade efter modell:

| Flik | Innehåll |
|---|---|
| 📈 Teknisk modell – Signaler | Gemensamma tekniska signalparametrar och separat grafvisning |
| 🧪 Teknisk modell – Backtest | Aktuella signalvärden, egna handelsantaganden, kapitalgraf och svensk affärslogg |
| 🌍 KI-modellen – Konjunktur | Egna KI-parametrar, valbar återköpsregel och Sverige som prisreferens |
| 🏦 KI-modellen – Portföljbacktest | Egen KI-signal, portfölj, avriskning och defensiv placering |

Översikten ”Om modellerna” ligger i en utfällbar ruta under flikarna.

### Nytt gränssnitt

- Ingen global parameterpanel. Tekniska signaler och tekniskt backtest använder samma beräknade signalserie.
- Heatmap-intensitet påverkar enbart trendgrafens färger.
- KI-kon­junktursidan och KI-portföljbacktestet har separata, tydligt märkta parametrar.
- Kostnader och riskfri jämförelseränta är separata för tekniskt backtest och KI.
- Båda backtesten visar hela den aktuella konfigurationen överst.
- Kapitalgraferna visar faktiska transaktioner med stora markörer, datum i hover och streckade linjer.
- KI-hover visar faktisk aktieandel före/efter och nettobelopp till/från räntekontot efter kostnader.
- Grön bakgrund betyder investerat/fullt investerat; grå betyder kassa/avriskat läge.
- Öppna tekniska affärer har inga säljdatum eller säljkurser i affärsloggen. Avkastningen är orealiserad.
- En ogiltig teknisk börssymbol blockerar inte KI-flikarna.
- Samtliga befintliga återköpsregler, jämförelsetabeller och Sverigejämförelsen finns kvar.

## 2. Installation

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Starta appen

```bash
streamlit run app.py
```

## 4. Köra testerna

```bash
python -m pytest -v
```

Alla tester använder **syntetisk data** och kräver ingen internetuppkoppling efter
installation av beroendena. Nätverksanslutningar spärras av en automatisk pytest-fixture;
UI-tester ersätter samtliga datahämtare. Tidigare version: **67 tester passerade** (37 befintliga
och 30 nya testfall), med Python 3.13.2, pytest 8.4.2, Pandas 2.3.3, NumPy 2.1.3
och Streamlit 1.63.0. Se `CHANGELOG.md` för ändringar och testinventering.

## 5. Projektstruktur

```
app.py          Streamlit UI - all beräkningslogik ligger i övriga moduler
config.py       Standardvärden, tickerproxys, pedagogiska förklaringstexter
data.py         All nätverksdatahämtning (yfinance, KI:s PXWeb-API), cachad
indicators.py   SMA, RSI (Wilder), MACD, trend-streak - ren Pandas/NumPy
signals.py      EN central funktion avgör den tekniska modellens köp/sälj-signal
backtest.py     Backtestmotor för den tekniska modellen (RSI/MACD/VIX)
ki_model.py     KI-signalens state machine + flera återköpsregler
reentry.py      Kombinerat återköp i steg (KI, VIX, kredit, RSI, trend, tidsspärr) på daglig kalender
portfolio.py    Backtestmotor för KI-portföljstrategin (helt separat från backtest.py)
savings.py      Månadssparande: sparplan, insättningar, XIRR och tidsviktad avkastning, belopp med mellanslag
signal_sources.py  Alternativ signal: OECD CLI för USA omräknad till KI-skala utan look-ahead
metrics.py      CAGR, MDD, Sharpe, Sortino, Calmar, Win Rate, Profit Factor m.fl.
charts.py       Plotly-figurer (inga Streamlit-anrop)
test_*.py       Pytest-svit med syntetisk data (i projektroten)
```

Beräkningsmotorerna (`indicators`, `signals`, `backtest`, `ki_model`, `portfolio`, `metrics`)
importerar **inte** Streamlit och går att testa/köra helt fristående.

## 6. Datakällor och proxys

| Del | Källa | Ticker | Kommentar |
|---|---|---|---|
| Teknisk analys | Yahoo Finance (yfinance) | valfri, default `SPY` | `auto_adjust=True` (split/utdelningsjusterad) |
| VIX | Yahoo Finance | `^VIX` | |
| KI Barometerindikator | Konjunkturinstitutets PXWeb-API | — | Månadsdata, tidsstämplad vid månadsslut |
| Portfölj — Global | Yahoo Finance | `URTH` (iShares MSCI World ETF) | USD, utdelningsjusterad |
| Portfölj — Sverige | Yahoo Finance | `EWD` (iShares MSCI Sweden ETF) | USD, utdelningsjusterad |
| Portfölj — Emerging Markets | Yahoo Finance | `EEM` (iShares MSCI EM ETF) | USD, utdelningsjusterad |
| Valutakurs | Yahoo Finance | `USDSEK=X` | Används för att konvertera portföljen till SEK |
| Kreditspread (valfritt) | Yahoo Finance | `HYG`, `IEF` | Kvoten HYG/IEF; hämtas bara när kreditsteget är på. HYG finns från 2007 |
| Räntekonto (historisk ränta) | Riksbankens öppna API (SWEA) | `SETB3MBENCH` | 3-månaders statsskuldväxel, daglig från 1983. Gratis, ingen nyckel |
| Signalkälla USA (valfritt) | FRED (OECD) | `USALOLITOAASTSAM` | OECD Composite Leading Indicator för USA, månadsdata från 1955. Gratis CSV, ingen nyckel |
| USA med längsta historik | Yahoo Finance | `SPY` | S&P 500-fond, USD, utdelningsjusterad, räknas om till SEK |

**Varför ETF-proxys och inte råa index?** Rena prisindex (t.ex. `^OMX`) inkluderar inte
utdelningar och överskattar därmed hur mycket sämre en avriskad/defensiv strategi ser ut
jämfört med verkligheten. De utdelningsjusterade ETF:erna ovan är alla brett diversifierade,
likvida och yfinance-kompatibla.

**"Originalmodell / Sverige"-fliken** använder av samma robusthetsskäl `EWD` snarare än ett
renodlat svenskt totalavkastningsindex (t.ex. OMXSGI), eftersom ett stabilt sådant inte kunde
hämtas robust via yfinance. Detta är alltså **samma proxy** som portföljens Sverige-del — en
förenkling som tydligt dokumenteras här och i UI:t.

## 7. Indikatorerna (teknisk modell)

- **SMA** (konfigurerbar period, default 200) — långsiktig trendriktning.
- **RSI (14, Wilders metod)** — kortsiktigt momentum, används för att identifiera översålda lägen.
  Första genomsnittliga upp-/nedgången är ett enkelt medelvärde över 14
  prisförändringar (15 priser). Därefter: `(föregående medel × 13 + ny förändring) / 14`.
  Efter datagap börjar uppvärmningen om. En helt platt serie ger RSI 50.
  RSI är `NaN` under uppvärmningsperioden (de första 14 observationerna) — sätts **aldrig**
  artificiellt till 100.
- **MACD (24/52/9)** — identifierar momentumförändringar; säljsignal vid nedåtkorsning + högt RSI.
- **VIX** — paniksignal (köp) när VIX överstiger en tröskel.

## 8. Signalregler (teknisk modell)

En **enda central funktion** (`signals.generate_signals`) avgör den slutgiltiga signalen för
varje dag. Grafen, signalserien och backtesten läser alltid samma output — det finns ingen
duplicerad signallogik.

**Prioritering vid ev. konflikt samma dag:**
1. Säljsignal (MACD) prioriteras framför köpsignal, eftersom sälj är riskreducerande.
2. Bland köpkandidater prioriteras VIX-panik framför RSI-köp.
3. Köp och sälj har separata cooldown-räknare, mätta i **handelsdagar** (bars), inte
   kalenderdagar.

## 9. Konjunkturmodellens princip

Konjunkturmodellen (inspirerad av
[cornucopia.se](https://cornucopia.se/2015/02/konjunkturmodellen-haller-fortfarande/))
använder KI:s Barometerindikator för att identifiera extrema delar av konjunkturcykeln.
Idén är **konträr**:

- mycket stark konjunktur/överhettning → minska aktieexponeringen
- mycket svag konjunktur → öka aktieexponeringen igen

**Standardvärden:** säljgräns 110, köp/lågkonjunkturgräns 90, bekräftelse 3 månader.

### State machine

En **state machine** garanterar att en enda lång överhettningsperiod bara ger EN säljsignal
(inte en ny varje månad):

```
NORMAL --(KI > säljgräns i N månader)--> DERISKED
DERISKED --(KI passerar golvnivån, default 90)--> FLOOR_REACHED
FLOOR_REACHED --(återköpsregel uppfylld)--> NORMAL (köpsignal)
```

Golvkravet förhindrar att en liten studs vid fortsatt överhettning (t.ex. 113→115→112→113)
felaktigt tolkas som konjunkturbotten.

### Återköpsregler

- **A. Klassisk** — KI under köpgränsen i N bekräftande månader.
- **B/C/D. KI vänder upp (1/2/3 månader)** — N stigande månadsobservationer i följd, efter att
  golvnivån passerats.
- **E. Oförändrat eller stigande KI** — KI har varit strikt under köpgränsen efter sälj.
  Första oförändrade eller stigande månad ger återköp även över köpgränsen. Separat golv används inte.

## 10. KI-standardvärden

| Parameter | Default |
|---|---|
| Säljgräns | 110 |
| Köpgräns | 90 |
| Bekräftande månader | 3 |
| Golv för återköp | 90 |
| Återköpsregel | Klassisk |
| Avriskningsgrad vid sälj | 50 % |
| KI-signalen påverkar | Hela portföljen |

## 11. Portföljvikterna

Standardportfölj: **75 % Global / 10 % Sverige / 15 % Emerging Markets**, justerbar i sidomenyn.
Appen validerar att vikterna summerar till 100 % innan backtesten körs.

## 12. Räntekonto

Kapital som avriskas placeras på ett räntekonto snarare än att stå overäntat. Tre lägen:

1. **Historisk ränta** (standard) — Riksbankens dagliga ränta på 3-månaders statsskuldväxlar
   (SETB3MBENCH), hämtad gratis från Riksbankens öppna API. Valfritt avdrag (%/år) och golv på 0 %
   (standard på). Räntan som gällde föregående handelsdag används för perioden fram till nästa.
   Misslyckas hämtningen används den fasta räntan och en varning visas.
2. **Fast ränta** (2,5 %/år) — för jämförelse.
3. **0 % ränta** — för jämförelse.

Alla lägen förräntas över faktiska kalenderdagar (`(1 + ränta) ^ (dagar / 365)`).

## 13. Execution

Signaler exekveras **tidigast nästa handelsdag** (t+1) efter att de uppstått — aldrig
retroaktivt samma dag. Den tekniska modellen har två execution-metoder: nästa dags Open eller nästa dags Close
(default, för att matcha tidigare beteende). Se `backtest.py`.

## 14. Courtage/slippage

Anges i baspunkter (bps) och appliceras vid varje exekvering (default 0, så att kostnadsfria
och kostnadsjusterade resultat kan jämföras). Samma UI-parametrar används i båda motorerna.

- Teknisk modell: slippage justerar köp-/säljpriset och courtage dras enligt
  `ExecutionParams` i `backtest.py`. Den tekniska Buy & Hold-kurvan är fortsatt kostnadsfri.
- KI-portfölj: kostnad = `(cost_bps + slippage_bps) / 10000 × omsatt aktievärde`.
  Det är en additiv bps-approximation av courtage och slippage på portföljnivå, inte
  tekniska motorns separata prisjustering. Både köp och försäljning räknas; cash-benets
  förändring räknas inte ytterligare en gång. Nettoförmögenheten löses så att målvikterna
  uppnås efter kostnader utan negativ kassa.
- Kostnader dras vid initialköp, avriskning, återköp och periodisk rebalansering.
  Utan omsättning blir kostnaden noll. Samtidig KI-signal och rebalansering ger en enda
  omallokering. Ingen framtvingad slutlikvidering görs.
- KI, KI:s Buy & Hold, parameterjämförelsen och Sverigejämförelsen använder samma modell.
  Returvärdena `transaction_costs` och `turnover` visar dagliga belopp i basvalutan.
- KI-kurvan börjar efter initialköpets kostnad. `equity.attrs["initial_capital"]` sparar
  ursprungligt kapital; totalavkastning, CAGR, drawdown och Calmar räknas från detta.
  Behåll attributet när kurvan skickas till `metrics`. Sharpe/Sortino baseras på
  förändringar mellan observerade dagsvärden och inkluderar därför inte initialköpets
  engångsavdrag, men inkluderar alla senare transaktionskostnader.

## 15. Valutahantering

Portföljens tre delar (Global/Sverige/EM) handlas som USD-denominerade ETF:er. De konverteras
till en gemensam basvaluta (**SEK**) via `USDSEK=X` **innan** de vägs samman — serier i olika
valutor multipliceras eller adderas aldrig direkt. Buy & Hold-benchmarken använder exakt samma
valutametodik som KI-strategin. Se `portfolio.to_common_currency`.
Endast senast kända FX-observation på eller före prisdatum används (`ffill` på unionen
av kalendrarna, sedan återindexering). Ingen `bfill` används. Innan första kända FX-kurs
förblir konverterade priser `NaN`; `align_prices` tar bort dessa datum. Tidigare FX på
dagar utan ETF-handel bevaras. Under två gemensamma datum ger ett tydligt fel i UI.
Dagliga FX-stängningar behandlas som tillgängliga vid dagens portföljvärdering;
intradagssynkronisering av olika marknaders stängningstider modelleras inte.

**Förenkling:** valutaexponeringen antas fullt genomslående (ingen valutasäkring modelleras).

## 16. Rebalansering

Fyra alternativ: ingen, årlig (default), kvartalsvis, månadsvis. **Samma** schema används för
KI-strategin och dess Buy & Hold-benchmark, så att jämförelsen är rättvis (annars skulle
skillnader i resultat delvis bero på rebalanseringen i sig, inte på KI-signalen).

## 17. Backtestantaganden — sammanfattning

- Ingen look-ahead: en signal från dag/månad t kan tidigast påverka portföljen nästa handelsdag.
- KI-data antas tillgänglig för handel `KI_PUBLICATION_LAG_DAYS` (standard 0) kalenderdagar efter
  månadsslut, alltså första handelsdagen i nästa månad. KI publicerar i slutet av samma månad, se avsnitt 18.
- Öppna positioner vid periodens slut räknas **inte** som avslutade affärer i Win Rate/Profit
  Factor, utan redovisas separat.
- Profit Factor beräknas på faktisk realiserad P&L (kronor/dollar), inte summerade
  procentavkastningar.
- RSI är `NaN` under uppvärmningsperioden — ingen signal kan genereras innan indikatorerna är
  riktiga tal.

## 18. Antagande: KI-publiceringsfördröjning

Det öppna KI-APIet exponerar inte ett tillförlitligt historiskt publiceringsdatum per
observation. KI publicerar i slutet av samma månad som värdet avser (t.ex. majsiffran 2026 den 28 maj).
Appen använder därför `config.KI_PUBLICATION_LAG_DAYS` (standard 0 dagar efter månadsslut, tidigare 20)
innan en KI-signal anses tillgänglig för handel, och
exekverar därefter strikt nästa tillgängliga handelsdag: `Exec_Date > Available_Date`.
Även en senare tidsstämpel samma kalenderdag utesluts; signaler utan en senare handelsdag utelämnas. Detta är ett medvetet, dokumenterat antagande —
justera konstanten i `config.py` om ett mer exakt publiceringsschema blir tillgängligt.

## 19. Mått som visas

Totalavkastning, CAGR, Max Drawdown, Sharpe Ratio, Sortino Ratio, Calmar Ratio, Win Rate,
Profit Factor (visas som `∞` eller `N/A` istället för konstgjorda tal som 99.9), Slutvärde,
Marknadsexponering, antal avslutade/öppna affärer, tid i aktier vs. tid defensivt.

KI-räntan används för KI-räntekontot och KI:s Sharpe/Sortino-anrop, inklusive jämförelsetabellen.
Tekniskt backtest har en egen riskfri jämförelseränta (standard 0 %); teknisk kassa förräntas inte.
I läget Historisk ränta används snitträntan under perioden (efter avdrag/golv) i Sharpe/Sortino. Fast ränta och nollränta finns kvar som val.

## 20. Historiklängd och proxyval

URTH/EWD/EEM behålls. [URTH:s faktablad](https://www.ishares.com/us/literature/fact-sheet/urth-ishares-msci-world-etf-fund-fact-sheet-en-us.pdf)
anger fondstart 10 januari 2012. Den gemensamma historiken kan därför tidigast börja då,
och kan börja senare beroende på hämtade ETF- och FX-data. UI visar faktisk start och
slut **efter** konvertering och kalenderanpassning, samt varnar för få konjunkturcykler.
Finanskrisen 2008 ingår inte i standardportföljens test. Antalet kompletta cykler beräknas
inte; varningen är en metodbegränsning, inte en automatisk cykelklassificering.
Sverigejämförelsen har egen kalender och visar sina egna start-/slutdatum.

[EFA](https://www.ishares.com/us/products/239623/ishares-msci-eafe-etf) har längre historik
(fondstart 14 augusti 2001) men exkluderar USA och Kanada. Den är därför inte ett likvärdigt
byte för MSCI World. En syntetisk kombination med nordamerikanska ETF:er skulle kräva
historiska regionvikter, separat rebalanseringsmetod och validering. Ingen sådan skarvning
eller retroaktiv prisfyllning införs här. Utdelningsjusterade ETF-priser förblir proxy för
totalavkastning efter fondkostnader, inte ett officiellt total-return-index.

Alla tre proxyserier krävs fortsatt i huvudtestets gemensamma kalender, även om en vikt
sätts till noll. Detta bevarar den befintliga jämförelsens urval.

## 21. Begränsningar

- Backtester är historiska och **förutsäger inte** framtiden. Undvik att tolka
  parameterjämförelsetabellen (avriskning × återköpsregel) som en optimeringsrekommendation.
- Resultat per portföljdel (flik 4) är en **approximation**: eftersom kapital flyttas mellan
  delarna vid rebalansering/KI-signaler är kurvorna inte renodlade "köp och behåll enbart den
  tillgången"-kurvor.
- KI-seriens historiska värden kan vara reviderade; någon vintage-databas används inte.
- KI-publiceringsdatum är en schablon (se avsnitt 18), inte exakta historiska publiceringsdatum.
- Ingen valutasäkring modelleras.
- Walk-forward/in-sample-/out-of-sample-analys är **inte** implementerat i denna version —
  jämförelsetabellerna är uttryckligen historiska, inte prediktiva.
- Experimentella indikatorer (ATR, ADX, market breadth) är **inte** implementerade i denna
  version, i linje med kravet att undvika "indicator bloat" i huvudmodellen.

---

## Sammanfattning av större förändringar jämfört med tidigare version

- **Refaktorerat** monolitiskt `app.py` (~1200 rader) till separata moduler
  (`data/indicators/signals/backtest/ki_model/portfolio/metrics/charts/config`), samtliga
  testbara utan Streamlit.
- **Rättat bias-källor** i tekniska backtesten: RSI sätts inte längre artificiellt till 100
  under uppvärmning; samtidiga köp/sälj-signaler kan inte längre skriva över varandra
  inkonsekvent (en central, dokumenterad prioriteringsregel); öppna positioner särredovisas
  från avslutade affärer i Win Rate/Profit Factor; Profit Factor räknas nu på faktisk P&L i
  kronor/dollar.
- **Lagt till realistisk execution**: t+1-exekvering, valbar Open/Close, courtage och
  slippage i baspunkter.
- **Ny, helt separat KI-portföljbacktest** (flik 4) med en egen state machine för KI-signalen,
  fyra återköpsregler, valbar scope (hela portföljen/Sverige/Sverige+EM), partiell avriskning,
  räntekonto, valutakonvertering till SEK och periodisk rebalansering — med identiskt schema
  för KI-strategin och dess Buy & Hold-benchmark.
- **Bytt SMA-kolumnnamn** från hårdkodat `SMA_200` till `SMA` (perioden är en parameter).
- **Bytt UI-etikett** för cooldown till "Signal-cooldown (handelsdagar)" för att förtydliga
  att måttet är barbaserat, inte kalenderdagsbaserat.
- **Lagt till pedagogiska förklaringar** (`help=` och expanders) för samtliga begrepp i
  kravspecifikationen.
- **Lagt till en pytest-svit** (ursprungligen 37 tester, nu förstärkt med regressionstester) med syntetisk data som täcker bl.a. no-look-ahead,
  RSI-uppvärmning, signalkonflikter, öppna/avslutade affärer, Profit Factor-hantering,
  partiell avriskning, räntekontots tillväxt, rebalansering och valutakonvertering.
- **Rättat `.gitignore`**-filnamnet (låg tidigare som `gitignore.txt`).
- Förbättrad felhantering: nätverksfel loggas med `logging` och fångas aldrig tyst; UI visar
  begripliga felmeddelanden och degraderar snyggt (t.ex. om KI-APIet eller en ticker inte
  svarar) istället för att krascha.

## Metodantaganden jag behövde välja själv

1. **Proxyval** för Global/Sverige/EM (URTH/EWD/EEM) och för valutakurs (`USDSEK=X`) — valda
   för att vara breda, likvida, utdelningsjusterade och robust yfinance-kompatibla.
2. **KI-publiceringsfördröjning** satt till en schablon på 20 dagar (se avsnitt 18) i brist på
   robust historisk publiceringsdata.
3. **Signalprioritering** vid samtidig köp/sälj-konflikt: sälj vinner (riskreducering främst),
   och VIX-panik prioriteras framför RSI bland köpkandidater.
4. **"Originalmodell/Sverige"** återanvänder Sverige-proxyn (EWD) snarare än ett separat
   totalavkastningsindex, av samma datarobusthetsskäl som för huvudportföljen.
5. Historisk svensk kortränta hämtas sedan 26 oktober 2026 från Riksbankens öppna API (gratis, ingen nyckel),
   med fast ränta som automatisk reserv om API:et inte svarar.
