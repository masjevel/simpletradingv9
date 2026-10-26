# ============================================================
# config.py
# ------------------------------------------------------------
# Centrala standardvärden, tickerproxys och pedagogiska
# förklaringstexter. Inga beräkningar eller Streamlit-anrop
# här - bara ren konfiguration som övriga moduler importerar.
# ============================================================

from __future__ import annotations

# ------------------------------------------------------------
# Tekniska indikatorer - standardvärden
# ------------------------------------------------------------
DEFAULT_TICKER = "SPY"
DEFAULT_SMA_PERIOD = 200
DEFAULT_RSI_PERIOD = 14
DEFAULT_BUY_RSI_THRESHOLD = 28
DEFAULT_SELL_RSI_FILTER = 65
DEFAULT_COOLDOWN_BARS = 15  # handelsdagar (bars), inte kalenderdagar
DEFAULT_VIX_PANIC_THRESHOLD = 34.0
DEFAULT_HEATMAP_CAP = 150

MACD_FAST = 24
MACD_SLOW = 52
MACD_SIGNAL = 9

# ------------------------------------------------------------
# Execution / kostnader
# ------------------------------------------------------------
DEFAULT_EXECUTION_METHOD = "Nästa dags stängning (Close)"
EXECUTION_METHODS = [
    "Nästa dags stängning (Close)",
    "Nästa dags öppning (Open)",
]
DEFAULT_COST_BPS = 0.0       # courtage/transaktionskostnad, baspunkter
DEFAULT_SLIPPAGE_BPS = 0.0   # slippage, baspunkter
DEFAULT_INITIAL_CAPITAL = 10_000.0
DEFAULT_RISK_FREE_RATE_ANNUAL = 0.0  # används i Sharpe/Sortino, procent/år -> decimal

# ------------------------------------------------------------
# KI / Konjunkturmodellen - standardvärden
# ------------------------------------------------------------
DEFAULT_KI_SELL_THRESHOLD = 110
DEFAULT_KI_BUY_THRESHOLD = 90
DEFAULT_KI_DURATION_MONTHS = 3
DEFAULT_KI_FLOOR_THRESHOLD = 90  # KI måste ha varit under denna nivå innan en "vänd upp"-signal tillåts

KI_BUYBACK_RULES = {
    "classic": "A. Klassisk modell (KI under köpgräns i N månader)",
    "turn_1m": "B. KI vänder upp - 1 månad",
    "turn_2m": "C. KI vänder upp - 2 månader",
    "turn_3m": "D. KI vänder upp - 3 månader",
    "flat_or_up": "E. KI oförändrat eller stigande efter passerad köpgräns",
}
DEFAULT_KI_BUYBACK_RULE = "classic"

KI_SIGNAL_SCOPE_OPTIONS = {
    "all": "Hela portföljen",
    "sweden_only": "Endast Sverige",
    "sweden_em": "Sverige + Emerging Markets",
}
DEFAULT_KI_SIGNAL_SCOPE = "all"

DERISK_LEVELS = [0, 25, 50, 75, 100]
DEFAULT_DERISK_LEVEL = 50

# ------------------------------------------------------------
# Portfölj - proxys och vikter
# ------------------------------------------------------------
# Alla tre proxys handlas i USD (utdelningsjusterade ETF:er via
# yfinance auto_adjust=True). Portföljen normaliseras därefter
# till gemensam basvaluta (default SEK) via USD/SEK-växelkurs.
PORTFOLIO_PROXIES = {
    "global": {"ticker": "URTH", "label": "Global (iShares MSCI World ETF, USD, utd.just.)"},
    "sweden": {"ticker": "EWD", "label": "Sverige (iShares MSCI Sweden ETF, USD, utd.just.)"},
    "em": {"ticker": "EEM", "label": "Emerging Markets (iShares MSCI EM ETF, USD, utd.just.)"},
}
FX_TICKER = "USDSEK=X"
DEFAULT_BASE_CURRENCY = "SEK"

DEFAULT_PORTFOLIO_WEIGHTS = {"global": 0.75, "sweden": 0.10, "em": 0.15}

REBALANCE_OPTIONS = {
    "none": "Ingen rebalansering",
    "annual": "Årlig",
    "quarterly": "Kvartalsvis",
    "monthly": "Månadsvis",
}
DEFAULT_REBALANCE = "annual"

# Originalmodell / Sverige - jämförelseticker (samma proxy som portföljens
# Sverige-del, se README för motivering och begränsningar).
SWEDEN_ORIGINAL_TICKER = PORTFOLIO_PROXIES["sweden"]["ticker"]

# ------------------------------------------------------------
# Räntekonto
# ------------------------------------------------------------
INTEREST_MODES = {
    "historical": "Historisk ränta (statsskuldväxel 3 mån, Riksbanken)",
    "fixed": "Fast ränta",
    "zero": "0 % ränta (jämförelse)",
}
DEFAULT_INTEREST_MODE = "historical"
DEFAULT_ANNUAL_INTEREST_RATE = 0.025  # 2.5 % (används i läget "Fast ränta" och som reserv)
DEFAULT_INTEREST_DEDUCTION = 0.0      # %/år som dras från den historiska räntan (t.ex. fondavgift)
DEFAULT_INTEREST_FLOOR_ZERO = True    # som ett sparkonto: aldrig negativ ränta

# Riksbankens öppna API (SWEA). Gratis, ingen nyckel krävs (anonymt: 5 anrop/minut,
# 1000/dygn per IP). Appen gör ett anrop och cachar svaret ett dygn.
RIKSBANK_API_BASE = "https://api.riksbank.se/swea/v1"
RIKSBANK_RATE_SERIES = "SETB3MBENCH"  # 3-månaders statsskuldväxel, daglig, från 1983
RIKSBANK_RATE_LABEL = "Statsskuldväxel 3 mån (Riksbanken, SETB3MBENCH)"

# ------------------------------------------------------------
# Datumhantering / look-ahead
# ------------------------------------------------------------
# KI publicerar Barometerindikatorn i slutet av SAMMA månad som den avser
# (t.ex. majsiffran 2026 den 28 maj). Värdet tidsstämplas här vid månadsslut,
# så 0 dagar betyder handel första handelsdagen i nästa månad - fortfarande
# några dagar efter den faktiska publiceringen. Exakta historiska
# publiceringsdatum finns inte i det öppna API:et; reglaget i UI låter dig
# testa känsligheten (t.ex. 20 dagar som mycket försiktigt antagande).
KI_PUBLICATION_LAG_DAYS = 0

# ------------------------------------------------------------
# Pedagogiska förklaringar (används som help= och i expanders)
# ------------------------------------------------------------
EXPLANATIONS = {
    "sma": "SMA (Simple Moving Average) är priset i genomsnitt över de senaste X dagarna. "
           "Den visar den långsiktiga prisriktningen: pris över SMA = uppåttrend, pris under SMA = nedåttrend.",
    "rsi": "RSI (Relative Strength Index) mäter kortsiktigt momentum på en skala 0-100. "
           "Här används den framför allt för att identifiera kraftigt översålda lägen (lågt RSI).",
    "macd": "MACD jämför två glidande medelvärden för att försöka identifiera förändringar i momentum. "
            "När MACD-linjen korsar ner under sin signallinje tolkas det som en försvagning.",
    "vix": "VIX mäter förväntad volatilitet/stress på den amerikanska aktiemarknaden. "
           "Höga VIX-nivåer har historiskt ofta sammanfallit med paniknedgångar och efterföljande återhämtningar.",
    "trend": "Positiv trend = priset ligger över sitt glidande medelvärde (SMA). "
             "Negativ trend = priset ligger under. Detta säger inget om framtiden, bara nuläget.",
    "cooldown": "Signal-cooldown (handelsdagar) förhindrar att nya signaler av samma typ skapas för tätt inpå "
                "varandra. Måttet räknas i handelsdagar (börsdagar), inte kalenderdagar.",
    "heatmap": "Heatmap-intensiteten styr bara hur snabbt graf-färgerna mättas ju längre en trend pågått. "
               "Den påverkar enbart visualiseringen, inte några signaler eller backtestresultat.",
    "ki_barometer": "KI:s Barometerindikator är Konjunkturinstitutets sammanvägda mått på stämningsläget i "
                    "svensk ekonomi. Värden kring 100 anses normalläge.",
    "ki_sell": "KI-säljgränsen anger vid vilken nivå konjunkturen anses överhettad. Modellen är konträr: "
               "vid överhettning minskas aktieexponeringen, i tron att risken för avmattning ökat.",
    "ki_buy": "KI-köpgränsen anger vid vilken nivå konjunkturen anses vara i en tydlig lågkonjunktur. "
              "Modellen är konträr: vid svag konjunktur ökas aktieexponeringen igen.",
    "ki_months": "Antal månader i följd över säljgränsen före försäljning. För klassiskt återköp gäller "
                 "samma antal månader under köpgränsen. Övriga återköpsregler har egna villkor.",
    "ki_flat_or_up": "Efter försäljning måste KI först vara strikt under köpgränsen. Köp sedan vid första "
                      "månad som är oförändrad eller högre än månaden innan, även över köpgränsen "
                      "(t.ex. 89 → 91 med köpgräns 90). Två månaders värden jämförs; två uppgångar krävs inte. "
                      "Aktiveringen nollställs efter återköp. Antal bekräftande månader gäller här endast sälj.",
    "cagr": "CAGR (Compound Annual Growth Rate) är den genomsnittliga årliga avkastningen, jämnt utspridd "
            "över hela perioden - även om den faktiska resan var betydligt ojämnare.",
    "total_return": "Totalavkastningen är den sammanlagda procentuella förändringen av portföljvärdet från "
                     "start till slut, inklusive alla mellanliggande upp- och nedgångar.",
    "mdd": "Max Drawdown är det största observerade fallet från en tidigare topp till en efterföljande botten. "
           "Ett mått på det värsta som historiskt hänt en investerare som köpte på fel dag.",
    "sharpe": "Sharpe Ratio mäter avkastning per enhet total risk (volatilitet), justerat för riskfri ränta. "
              "Högre är bättre, men måttet straffar även uppåtgående volatilitet.",
    "sortino": "Sortino Ratio liknar Sharpe men straffar bara nedåtgående volatilitet (förluster), "
               "vilket ofta upplevs som mer rättvisande för investerare.",
    "calmar": "Calmar Ratio ställer CAGR i relation till Max Drawdown. Ett sätt att väga avkastning "
              "mot det värsta historiska fallet.",
    "win_rate": "Win Rate är andelen avslutade affärer som gick med vinst, av samtliga avslutade affärer.",
    "profit_factor": "Profit Factor är summan av alla vinster delat med summan av alla förluster (i kronor/dollar). "
                      "Ett värde över 1 betyder att vinsterna historiskt överstigit förlusterna.",
    "exposure": "Marknadsexponering anger hur stor andel av tidsperioden portföljen faktiskt varit investerad "
                "i aktier, till skillnad från att stå i kassa/räntekonto.",
    "slippage": "Slippage är skillnaden mellan det pris man förväntade sig och det pris man faktiskt fick vid "
                "exekvering, t.ex. på grund av snabba prisrörelser eller låg likviditet.",
    "cost": "Courtage/transaktionskostnad är den avgift som tas ut vid varje köp/sälj, här angiven i baspunkter "
            "(1 baspunkt = 0,01 %) av affärens värde.",
    "risk_free": "Räntekonto/riskfri avkastning är den ränta kapital som inte är investerat i aktier antas "
                 "generera under tiden, t.ex. på ett räntekonto eller i statsskuldväxlar.",
    "derisk_pct": "Anger hur stor andel av aktieexponeringen som säljs av vid en KI-säljsignal. 100 % innebär "
                  "att allt flyttas till räntekontot, 0 % innebär att inget säljs.",
    "ki_scope": "Bestämmer vilken del av portföljen som påverkas av KI-signalen: hela portföljen, "
                "enbart den svenska delen, eller Sverige + Emerging Markets.",
    "rebalance": "Rebalansering innebär att portföljens vikter periodiskt återställs till målvikterna. "
                 "Utan rebalansering driver vinnande tillgångar successivt upp sin andel av portföljen.",
    "currency": "Alla portföljdelar konverteras till en gemensam basvaluta (SEK) via USD/SEK-kursen innan "
                "de vägs samman, så att avkastningar är jämförbara rakt av.",
}

# ------------------------------------------------------------
# Kombinerat återköp efter KI-sälj (reentry.py) - standardvärden
# ------------------------------------------------------------
REENTRY_MODES = {
    "ki_only": "Endast KI-regeln (som tidigare)",
    "combined": "Kombinerat återköp i steg",
}
DEFAULT_REENTRY_MODE = "ki_only"
DEFAULT_REENTRY_VIX_THRESHOLD = 34.0
DEFAULT_REENTRY_VIX_CALM = 25.0
DEFAULT_REENTRY_CREDIT_STRESS = 5.0
DEFAULT_REENTRY_CREDIT_SMA = 50
DEFAULT_REENTRY_RSI = 28.0
DEFAULT_REENTRY_TIME_STOP = 18
CREDIT_TICKERS = ("HYG", "IEF")  # gratis via Yahoo Finance: högräntefond / amerikanska statsobligationer 7-10 år

# ------------------------------------------------------------
# Förklaring av VARJE parameter: vad den gör och vad man ska tänka på.
# Används både som hjälptext (frågetecknet) och i rutan
# "📖 Förklaring av parametrarna" i varje flik (lättare att läsa i mobilen).
# ------------------------------------------------------------
PARAM_HELP = {
    # --- Testperiod ---
    "period_mode": ("Period för backtesten",
        "Längsta historik använder all data som finns för de valda tillgångarna. Välj datum låter dig testa en viss period.",
        "Testa gärna flera olika perioder. En modell som bara fungerar under en enda period är troligen anpassad till just den."),
    "period_dates": ("Start- och slutdatum",
        "Begränsar båda backtesten till perioden. Indikatorer värms upp med data före startdatum.",
        "Ta med minst en hel konjunkturcykel (helst flera) – annars kan resultatet bero på en enda händelse."),
    # --- Teknisk modell ---
    "tech_ticker": ("Tillgång (ticker)",
        "Börssymbolen från Yahoo Finance som den tekniska modellen analyserar, t.ex. SPY, ^OMX eller EWD.",
        "Index utan utdelningar (t.ex. ^OMX) ser sämre ut i köp och behåll än verkligheten. Välj gärna en utdelningsjusterad fond."),
    "tech_use_rsi": ("RSI som köpsignal",
        "Köp när RSI understiger köpgränsen, dvs. när priset fallit snabbt (översålt).",
        "I en björnmarknad kan RSI vara lågt många gånger i rad – den första signalen är ofta för tidig."),
    "tech_use_vix": ("VIX som köpsignal",
        "Köp när VIX (förväntad volatilitet i USA) är över paniktröskeln.",
        "Panik sammanfaller ofta med bottnar, men inte alltid den sista botten. VIX är amerikansk även när du analyserar svenska tillgångar."),
    "tech_use_macd": ("MACD som säljsignal",
        "Sälj när MACD-linjen korsar ned under sin signallinje.",
        "Utan säljsignal behålls köpen till periodens slut. MACD ger många signaler i sidledes marknader."),
    "tech_use_sell_rsi": ("Kräv högt RSI för MACD-sälj",
        "Säljer bara på MACD om RSI samtidigt är över säljfiltret, dvs. efter en stark uppgång.",
        "Minskar antalet säljsignaler. För högt filter kan göra att du nästan aldrig säljer."),
    "tech_use_trend": ("Kräv pris över SMA för köp",
        "Köpsignaler gäller bara när priset ligger över sitt glidande medelvärde (positiv trend).",
        "Skyddar mot att köpa i fallande marknad men stänger ute konträra köp vid paniklägen."),
    "tech_buy_rsi_threshold": ("RSI köpgräns",
        "Nivån RSI måste gå under för en köpsignal. Lägre = färre men mer extrema köp.",
        "Vanliga värden är 25–30. Under 20 blir signalerna mycket sällsynta."),
    "tech_sell_macd_rsi_filter": ("MACD/RSI säljfilter",
        "RSI-nivån som krävs samtidigt som MACD korsar ned för att sälja.",
        "Högre värde = färre säljsignaler, bara efter starka uppgångar."),
    "tech_cooldown_bars": ("Signal-cooldown (handelsdagar)",
        "Minsta antal handelsdagar mellan två signaler av samma typ.",
        "För kort ger många nästan identiska signaler; för långt kan missa en ny, verklig signal."),
    "tech_sma_trend_period": ("SMA-period",
        "Antal dagar i det glidande medelvärdet som definierar trenden.",
        "200 dagar är det vanligaste långsiktiga måttet. Kortare period vänder snabbare men ger fler falska vändningar."),
    "tech_vix_panic_threshold": ("VIX paniktröskel",
        "VIX-nivån som räknas som panik.",
        "Långsiktigt snitt för VIX är runt 20. Över 30–35 har historiskt varit ovanligt och sammanfallit med kraftiga fall."),
    "tech_display": ("Grafval och heatmap",
        "Styr bara vad som syns i diagrammen.",
        "Påverkar aldrig signaler eller resultat."),
    "tech_execution": ("Execution-metod",
        "Om affären görs till nästa dags öppningskurs eller stängningskurs.",
        "Signalen räknas på stängningskursen, så tidigast nästa dag kan du handla. Öppning är snabbare men kan skilja mer från signalpriset."),
    "tech_costs": ("Courtage och slippage (bps)",
        "Kostnad per affär i baspunkter (1 bps = 0,01 %). Slippage är skillnaden mot förväntat pris.",
        "Modeller med många affärer straffas mest. Testa gärna 5–20 bps för att se om modellen tål verkliga kostnader."),
    "tech_capital": ("Startkapital och riskfri ränta",
        "Startbelopp i USD och räntan som används i Sharpe/Sortino.",
        "Startkapitalet påverkar inte procentavkastningen. Kassa i den tekniska modellen förräntas inte."),
    # --- KI Konjunktur ---
    "ki_sell": ("KI säljgräns (överhettning)",
        "Barometerindikatorn måste ligga ÖVER denna nivå i det valda antalet månader för en säljsignal.",
        "Barometern är normerad till medel 100 och standardavvikelse 10, så 110 = 1 standardavvikelse över normalt och 113 = 1,3. "
        "Historiken revideras varje månad. Små skillnader (t.ex. 110 mot 113) kan bero på en enda händelse – kontrollera med robusthetstestet."),
    "ki_buy": ("KI köpgräns (lågkonjunktur)",
        "Nivån som räknas som tydlig lågkonjunktur. Används av återköpsreglerna.",
        "Barometern ligger sällan långt under 90. En för låg köpgräns kan göra att du aldrig köper tillbaka – använd då tidsspärren."),
    "ki_months": ("Antal bekräftande månader",
        "Hur många månader i följd KI måste vara över säljgränsen (och för klassiskt återköp under köpgränsen).",
        "Fler månader = färre falska signaler men senare försäljning. Med 3 månader kommer signalen tidigast tre månader efter första passagen."),
    "ki_rule": ("Återköpsregel (KI)",
        "Hur KI avgör att det är dags att köpa tillbaka efter en försäljning: A = under köpgränsen i N månader, "
        "B–D = KI stiger 1–3 månader efter golvet, E = första oförändrade/stigande månad efter att KI varit under köpgränsen.",
        "KI speglar ekonomin, som brukar ligga efter börsen. Rena KI-regler köper därför ofta tillbaka sent – efter att börsen redan vänt."),
    "ki_floor": ("Golv före återköp",
        "KI måste först ha varit under denna nivå innan regel B–D kan ge återköp.",
        "Förhindrar att en liten studs under fortsatt högkonjunktur tolkas som botten. Används inte av regel E."),
    "ki_lag": ("Publiceringsfördröjning (dagar)",
        "Hur många dagar efter månadsslut KI-värdet antas bli känt för handel.",
        "KI publicerar i slutet av SAMMA månad (t.ex. majsiffran 28 maj), så 0 dagar (standard) betyder handel första "
        "handelsdagen i nästa månad – några dagar efter publiceringen. 20 dagar är ett mycket försiktigt antagande. Jämför för att se hur känslig modellen är."),
    "ki_overlay_vix": ("Visa VIX-panik i KI-grafen",
        "Ritar en markör första dagen i varje period då VIX är över tröskeln.",
        "Bara visning – för att faktiskt testa VIX som återköp väljer du det i Portföljbacktestet."),
    "ki_overlay_rsi": ("Visa Köp (negativ trend) i KI-grafen",
        "Ritar en markör när Sverige (EWD) är översåld (RSI under gränsen) samtidigt som priset ligger under SMA 200.",
        "Beräknas på Sverigepriset, inte på tickern i den tekniska modellen, så modellerna förblir oberoende."),
    "ki_overlay_levels": ("Nivåer för lagren",
        "VIX-tröskel och RSI-gräns för markörerna i KI-grafen.",
        "Påverkar bara grafen i denna flik."),
    # --- Portföljbacktest: återköp ---
    "reentry_mode": ("Återköpsläge",
        "Endast KI = samma modell som tidigare. Kombinerat = återköpet sker i steg där varje valt villkor köper tillbaka en lika stor del.",
        "Ingen enskild signal träffar botten varje gång. Att sprida återköpet minskar risken att allt hänger på en enda bedömning."),
    "re_ki": ("Steg: KI-vändning",
        "Ett steg köps när KI:s valda återköpsregel (A–E) uppfylls.",
        "Ofta det senaste steget eftersom KI släpar efter börsen."),
    "re_vix": ("Steg: VIX-panik",
        "Ett steg köps efter VIX-panik som inträffat EFTER försäljningen.",
        "Panik kommer ofta tidigt i en björnmarknad (2008 passerade VIX 34 redan i september, botten kom i mars 2009). "
        "Därför finns valet att vänta tills paniken lagt sig."),
    "re_vix_threshold": ("VIX-tröskel för panik",
        "Nivån som räknas som panik.",
        "Högre tröskel = färre men mer extrema tillfällen. En långsam björnmarknad kan ha förhöjd men aldrig extrem VIX – då utlöses steget inte alls."),
    "re_vix_calm": ("Köp när VIX åter är under",
        "0 = köp dagen efter paniken. Annars köps steget först när VIX fallit tillbaka under denna nivå.",
        "Att vänta på lugnare VIX missar ofta den allra lägsta punkten men minskar risken att köpa mitt i raset."),
    "re_credit": ("Steg: Kreditspread vänder",
        "Använder kvoten HYG/IEF (högräntefond mot statsobligationer, gratis från Yahoo). När kvoten fallit kraftigt "
        "är kreditmarknaden stressad; ett steg köps när kvoten går över sitt glidande medelvärde igen.",
        "Kreditmarknaden vänder ofta före eller samtidigt med aktiebotten. HYG finns från 2007, så före dess kan steget inte utlösas."),
    "re_credit_stress": ("Kreditstress (% fall från 1-årstopp)",
        "Hur mycket HYG/IEF måste ha fallit från sin högsta nivå senaste året för att räknas som stress.",
        "Lägre värde = känsligare (fler, tidigare signaler). 5 % är en måttlig nivå."),
    "re_credit_sma": ("Kreditspread: medelvärde (dagar)",
        "Kvoten måste gå över detta glidande medelvärde för att stressen ska anses vika.",
        "Kortare medelvärde vänder snabbare men oftare felaktigt."),
    "re_rsi": ("Steg: Köp (negativ trend)",
        "Ett steg köps när portföljens egna aktier (viktat index i SEK av tillgångarna med vikt) är översålda (RSI under gränsen) och ligger under SMA 200.",
        "Inträffar ofta flera gånger i en björnmarknad – första gången är sällan botten. Fungerar bäst som ett av flera steg."),
    "re_rsi_threshold": ("RSI-gräns",
        "RSI-nivån som räknas som översåld.",
        "Lägre gräns = färre, mer extrema tillfällen."),
    "re_trend": ("Steg: Trendvändning",
        "Ett steg köps när portföljens egna aktier (viktat index i SEK) först har legat under sin trend EFTER försäljningen och sedan går över igen.",
        "Missar botten men undviker att köpa i ett fortsatt fall. Trenden behöver uppvärmning (10 månader eller 200 dagar) från första dagen med data, "
        "t.ex. hösten 2012 för Global."),
    "re_trend_mode": ("Trendmått",
        "Månadsvis: pris vid månadsslut över 10-månaders medelvärde. Dagligen: pris över SMA 200.",
        "Månadsvis passar en månadsmodell och ger färre falska vändningar. Dagligen reagerar snabbare."),
    "re_time_stop": ("Tidsspärr (månader)",
        "Om återköpet inte är klart inom så många månader efter försäljningen köps resten tillbaka. 0 = av.",
        "Den största risken med att sälja vid hög KI är att stå utanför en lång fortsatt uppgång. Tidsspärren begränsar den risken."),
    "re_staged": ("Köp i lika stora steg (trappa)",
        "På: varje valt villkor köper tillbaka en lika stor del. Av: första villkoret som uppfylls köper tillbaka allt.",
        "Trappan ger ett genomsnittligt pris över flera tillfällen och är mindre beroende av en enskild signal."),
    "pf_trend": ("Trendfilter för KI-återköp",
        "Endast för läget 'Endast KI': KI-köpet väntar tills portföljens egna aktier (viktat index i SEK) är över SMA 200.",
        "I kombinerat läge ersätts filtret av steget 'Trendvändning'."),
    # --- Portfölj ---
    "pf_weights": ("Vikter Global / Sverige / Emerging Markets",
        "Portföljens målvikter. Måste summera till 100 %.",
        "Global-proxyn (URTH) finns från 2012 och begränsar testets längd. Vill du se längre historik, använd Sverigejämförelsen med lång historik."),
    "pf_rebalance": ("Rebalansering",
        "Hur ofta vikterna återställs till målvikterna. Samma schema används för köp och behåll.",
        "Tätare rebalansering ger fler affärer och kostnader. Årlig är ett vanligt val."),
    "pf_capital": ("Startkapital (kr)",
        "Startbelopp i kronor.",
        "Påverkar inte procentavkastningen, bara beloppen i loggen."),
    "pf_costs": ("Courtage och slippage (bps)",
        "Kostnad per omsatt krona vid köp och sälj (1 bps = 0,01 %).",
        "KI-modellen handlar sällan, så kostnader spelar mindre roll – men trappan ger fler affärer."),
    "pf_scope": ("KI-signalen påverkar",
        "Vilken del av portföljen som säljs vid en KI-signal.",
        "KI mäter svensk ekonomi. Att bara avriska Sverige (eller Sverige + EM) är ett mer försiktigt sätt att använda signalen."),
    "pf_derisk": ("Minska aktieexponeringen med",
        "Hur stor del av den valda portföljdelen som flyttas till räntekontot vid sälj.",
        "100 % är allt eller inget. 50 % ger mindre ånger om marknaden fortsätter upp och fungerar bra ihop med trappan."),
    "pf_interest": ("Räntekonto och ränta",
        "Avkastningen på kapitalet som står utanför aktiemarknaden. Historisk = Riksbankens dagliga ränta på 3-månaders "
        "statsskuldväxlar, hämtad gratis från Riksbankens öppna API. Fast och 0 % finns kvar för jämförelse.",
        "Svensk kortränta låg på eller under 0 % 2015–2022. En fast ränta på 2,5 % hela perioden gör därför KI-strategin bättre än verkligheten. "
        "Hämtningen kan misslyckas tillfälligt; då används den fasta räntan och en varning visas."),
    "pf_interest_deduction": ("Avdrag från räntan (%/år)",
        "Dras från den historiska räntan varje dag, t.ex. avgiften i en räntefond.",
        "En kort räntefond kostar ofta 0,1–0,3 %/år. Sparkonto har ingen avgift men ger ofta lite lägre ränta än statsskuldväxlar."),
    "pf_interest_floor": ("Aldrig under 0 %",
        "På: negativ ränta räknas som 0 %, som på ett sparkonto eller kontanter på ISK. Av: räntan följer statsskuldväxeln även under noll.",
        "2016–2019 låg statsskuldväxeln runt −0,5 %. Korta räntefonder gav då något negativ avkastning, sparkonton 0 %."),
    "pf_robust": ("Robusthetstest",
        "Kör backtestet för alla kombinationer av säljgräns 105–118 och 1–4 bekräftande månader med dina övriga inställningar.",
        "Om ett helt område runt ditt val ger liknande resultat är valet robust. Är ditt val en ensam topp är det troligen tur."),
    "pf_sweden_long": ("Sverige med längsta historik",
        "Kör samma modell enbart på Sverige (EWD i SEK) så långt bak som kurs- och valutadata räcker.",
        "Ger fler konjunkturcykler (t.ex. 2007–2009) än huvudtestet, som begränsas av Global-proxyns start 2012."),
    # --- Månadssparande ---
    "sv_period": ("Start och slut för sparandet",
        "Första och sista dag i sparplanen. Startdatum före första dag med kursdata flyttas automatiskt fram.",
        "Prova att starta strax före en topp (t.ex. 2007 för Sverige, 2021 för Global) och strax efter en botten för att se hur mycket starttidpunkten betyder."),
    "sv_initial": ("Startbelopp (kr)",
        "Engångsbelopp som sätts in på startdagen. 0 = bara månadssparande.",
        "Ett stort startbelopp gör resultatet mer beroende av just startdagen än ett rent månadssparande."),
    "sv_monthly": ("Månadsbelopp (kr)",
        "Belopp som sätts in varje månad på vald dag (eller närmast följande handelsdag).",
        "Månadssparande sprider inköpen över tid, så du köper fler andelar när kurserna är låga."),
    "sv_day": ("Insättningsdag",
        "Dag i månaden då månadsbeloppet sätts in, t.ex. 25 för lönedagen.",
        "Påverkar resultatet mycket lite över lång tid."),
    "sv_growth": ("Årlig ökning av månadsbeloppet (%)",
        "Månadsbeloppet höjs med denna procentsats var tolfte månad räknat från startdatum.",
        "2–3 % motsvarar ungefär inflation, 4–5 % ungefär löneökningar. 0 % = samma belopp hela tiden."),
    "sv_extra": ("Extra insättningar",
        "Valfritt antal engångsinsättningar i en tabell: datum, belopp och en beskrivning (t.ex. bonus, arv, sålt bil). "
        "Lägg till rader via den tomma raden längst ner (eller + i verktygsraden) och ta bort genom att markera raden och trycka på papperskorgen.",
        "Lägg en insättning strax före en krasch och en strax efter för att se skillnaden."),
    "sv_compare": ("Jämför startår",
        "Kör samma månadssparplan (utan extra insättningar) med start i januari varje år och visar resultatet per startår.",
        "Visar hur mycket tur eller otur med starttidpunkten betyder. Korta sparperioder på slutet påverkas mest av de senaste årens börs."),
}


def help_text(key: str) -> str:
    """Hjälptext för frågetecknet: vad parametern gör + vad man ska tänka på."""
    title, what, think = PARAM_HELP[key]
    return f"{what}\n\n**Tänk på:** {think}"
