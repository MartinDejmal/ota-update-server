# Plán implementace a akceptace

## Organizace aplikace

Cílová struktura; soubory zatím nejsou implementované:

```text
app/
  main.py                 # FastAPI a lifecycle
  config.py               # validovaná konfigurace
  api/                    # device/admin routery a Pydantic schémata
  services/               # eligibility, ingest událostí, upload, retry
  db/                     # SQLAlchemy modely, transakce
  storage/                # neměnné soubory, atomický upload
  security/               # tokeny, session, CSRF
  templates/              # server-rendered administrace
  cli.py                  # migrace, správce, údržba, healthcheck
migrations/
tests/
Dockerfile
compose.yaml
pyproject.toml
uv.lock
docs/
```

Rozhodovací vrstva je nezávislá na HTTP a šablonách. Čas a úložiště jsou předávané závislosti pro smysluplné testy timeoutů a selhání. SQLAlchemy používá krátké explicitní transakce; blokující DB/file operace nesmějí blokovat async event loop. Lze použít synchronní routy/threadpool a streamování s řízeným souběhem. Jeden worker neznamená serializaci všech requestů.

## Etapy a dokončovací kritéria

| Etapa | Dodávka | Hotovo, když |
| --- | --- | --- |
| 1. Základ | Konfigurace, DB modely/migrace, device tokeny, bootstrap správce, Docker skeleton | Nová DB vznikne migrací, restart zachová stav, chybné schéma zabrání startu |
| 2. Vydání | Streaming upload, hash, kontroly, immutable storage, list/detail/withdraw | Neúplný upload se nenabízí, nelze nahradit soubor pod existujícím vydáním |
| 3. Check-in | Registrace zařízení, přiřazení, eligibility, nabídky, deduplikace | Opakování requestu nevytváří nové záznamy ani nemění odpověď v 7denním okně |
| 4. OTA výsledky | Start pokusu, autorizovaný download, ingest událostí, retry a timeout | Download sám neznamená úspěch, duplicity a pozdní výsledky mají definované chování |
| 5. Administrace | Zařízení, vydání, přiřazení, časová osa, login/CSRF | Správce provede celý cyklus bez ručního zásahu do DB |
| 6. Provoz | Proxy příklad, zálohy/obnova, údržba, limity, logování | Obnova do čistého volume zachová metadata, binárky a historii |
| 7. Integrace | Simulátor klienta a fyzická ESP32 akceptace | Ověřený update i rollback a zotavení při výpadku napájení |

Server lze vyvíjet se simulátorem před rozšířením reálného firmware. Fyzické testy klienta se však nesmějí označit za splněné jen na základě simulátoru.

## Akceptační scénáře

| ID | Scénář | Očekávaný výsledek |
| --- | --- | --- |
| A01 | Zařízení bez přiřazení | 200, ota:null, jeden kontakt a důvod no_assignment |
| A02 | Stejné request UUID a stejné tělo | Stejná odpověď, bez další nabídky/kontaktu |
| A03 | Stejné request UUID, jiné tělo | 409, žádná částečná změna |
| A04 | Nízká/chybějící baterie s nastaveným prahem | Odklad; žádný spotřebovaný pokus |
| A05 | Špatný hardware, slot, layout nebo signing profile | Žádná nabídka/start, srozumitelný důvod |
| A06 | Úspěšná instalace | Nabídka → pokus → download → potvrzení; from/to a oba serverové časy dohledatelné |
| A07 | Pouze stažení, zařízení se už neozve | Žádný úspěch; po timeoutu unknown |
| A08 | Check-in cílové verze bez confirmed | Pozorovaná verze se změní, instalace nepotvrzená, znovu se nestahuje |
| A09 | Ztracená odpověď při startu pokusu | Opakování stejného attempt UUID vrátí stejný pokus |
| A10 | Opakované/out-of-order události | Bez duplicit, projekce neregresuje; konflikt obsahu vrací 409 |
| A11 | Pozdní výsledek po unknown/zrušení/přiřazení jiné verze | Doplní správný starý pokus, nepřepíše aktuální pozorování/nové přiřazení |
| A12 | Dva souběžné starty nebo přiřazení | Databázově nejvýše jeden aktivní objekt daného typu |
| A13 | Vyčerpané retry, rollback, chybný podpis/hash | Blokace, auditovaný ruční zásah; nabídky samy limit nespotřebují |
| A14 | Cizí device token u nabídky/pokusu/artefaktu | 404, nelze stáhnout ani hlásit za jiné zařízení |
| A15 | Odvolání tokenu / stažení vydání | Nové starty/downloady blokované; historie zůstává |
| A16 | Useknutý upload, plný disk, pád mezi rename a DB commit | Žádné dostupné vydání odkazující na neúplný soubor |
| A17 | Pád aplikace během downloadu | Starý firmware dále použitelný; neúplný download log není potvrzení |
| A18 | Záloha a obnova včetně WAL | Integrity check i hashe projdou, historie zůstane čitelná |
| A19 | Retence odstraní starý check-in | Pokusy, firmware observations a výsledky zůstanou; idempotence přežije své celé okno |
| A20 | Neplatná CSRF/session, upload s path traversal jménem | Změna odmítnutá, soubor nemůže uniknout z storage |
| A21 | Slabá baterie nebo výpadek napájení na fyzické ESP32 | Zařízení po obnově nabootuje funkční slot; žádné falešné confirmed |
| A22 | Nový obraz spadne či selže self-test | Bootloader rollback, následné hlášení rolled_back a blokace vydání |
| A23 | Potvrzení obrazu proběhne, ale vypadne síť/napájení před hlášením | NVS journal rekonstruuje událost a doručí ji později |
| A24 | 100 simulovaných zařízení, 4 souběžné downloady a check-iny | Bez 5xx při běžné zátěži, check-in p95 do 500 ms na zdokumentovaném testovacím hostu |
| A25 | Expirovaná nabídka vrácená idempotentním replayem | Start odmítnut; nový check-in může získat čerstvou nabídku |
| A26 | Odpověď check-inu ztracena; události se opakují v novém check-inu | Již přijaté události znovu potvrzeny bez duplicit |
| A27 | Upgrade serveru s nekompatibilní DB | Start odmítnut, zdokumentovaná obnova zálohy |
| A28 | Pozdní historická událost přijde po check-inu novější verze | Historie doplněna, současná pozorovaná verze nezměněna |

## Kontroly před vydáním serveru

CI spustí formát/lint, typové kontroly aplikačních rozhraní, doménové a integrační testy nad skutečnou SQLite, kontrolu API kontraktu a sestavení image. Smoke test Compose pokryje migraci, bootstrap, check-in, upload, přiřazení, download a zachování dat po výměně kontejneru. Souběžnost a fault injection se testují tam, kde chrání uvedené invarianty.

Runtime OpenAPI se porovná se schváleným API v1; změny kontraktu musí změnit i dokumentaci a klientský simulátor. Docker image a Python závislosti mají připnuté verze. Testovací report zaznamená hostitele, omezení a které fyzické scénáře byly skutečně provedeny.

## Vstupy nutné před implementací ESP32

- Přesný model ESP32, velikost flash, současná partition table, framework a jeho verze.
- Velikost dnešního firmware a rezerva na růst, podpisové schéma a identita klíče.
- Baterie, regulátor, měření napětí a experimentálně stanovený bezpečný práh.
- Doména/TLS, hostitel Dockeru a způsob provisioning tokenů.

Tyto údaje neblokují implementaci serverového MVP; firmware kompatibilitu a fyzickou akceptaci je však nelze uzavřít bez nich.
