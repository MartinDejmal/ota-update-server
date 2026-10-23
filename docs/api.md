# API v1

Tato specifikace definuje cílový kontrakt. Implementace vystaví odpovídající OpenAPI generované FastAPI. Cesty začínají `/api/v1`, JSON je UTF-8 a čas je RFC 3339 UTC, např. `2026-10-23T12:00:00Z`. UUID jsou UUIDv4. SHA-256 je 64 malých hex znaků; build je integer 1 až 2147483647. Identifikátory v ukázkách jsou ilustrační platná UUID.

## Společná pravidla

Device operace vyžadují `Authorization: Bearer <device-token>`. Chybějící, chybný či odvolaný token vrací `401`. Cizí nebo nepřístupný identifikátor vrací `404`. Správcovská oprávnění se neposuzují podle device tokenu.

Pro zařízení: `Content-Type: application/json`, max. JSON tělo 32 KiB, dávka 0–16 událostí. Neznámá vstupní pole se odmítají `422`; klient ignoruje nová výstupní pole. Změna významu/povinných vstupů vyžaduje nové API major. JSON odpovědi mají `Cache-Control: no-store`.

Chyby mají tvar:

```json
{
  "error": {
    "code": "invalid_transition",
    "message": "Attempt is already terminal.",
    "trace_id": "9df67cbd-c18c-49f6-bb78-d7f8d629fb3e"
  }
}
```

Kódy: `400` neparsovatelné JSON; `401` autentizace; `403` CSRF/role; `404` neviditelný objekt; `409` konflikt stavu nebo idempotence; `413` velikost; `415` typ obsahu; `422` validace; `429` limit; `503` dočasná nedostupnost DB/úložiště. `429` a `503` mohou obsahovat celočíselné `Retry-After` v sekundách. Při neúspěchu check-inu firmware měří dál a přejde do sleepu.

## POST /check-in

Povinné položky jsou `request_id`, `firmware`, `ota_slot_size`, `events`; ostatní jsou volitelné a nullable. `battery_mv` je integer 0–20000, `rssi` integer -127–0, `reset_reason` text do 64 znaků. `ota_slot_size` je kladná kapacita neaktivního app slotu v bajtech. `firmware` obsahuje povinné `build` a `sha256`; volitelně `version` do 64 znaků.

`firmware.sha256` je hash distribuovaného OTA artefaktu, uložený při instalaci v NVS a navázaný na běžící app identitu; není to automaticky ESP-IDF hash app image. Při návratu na starý slot musí klient použít jeho vlastní identitu. Provisioning prvního firmware uloží odpovídající hash. Algoritmus viz [ESP32](esp32.md).

```json
{
  "request_id": "712892b1-ec8a-4ec8-b5f8-03c9c49b163a",
  "firmware": {
    "build": 42,
    "version": "1.4.2",
    "sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
  },
  "ota_slot_size": 1572864,
  "battery_mv": 3970,
  "rssi": -67,
  "reset_reason": "deep_sleep",
  "events": []
}
```

Odpověď `200` bez nabídky:

```json
{
  "request_id": "712892b1-ec8a-4ec8-b5f8-03c9c49b163a",
  "server_time": "2026-10-23T12:00:00Z",
  "accepted_event_ids": [],
  "decision": "no_assignment",
  "ota": null
}
```

Při nabídce je `decision: "offered"` a `ota` má tento tvar:

```json
{
  "offer_id": "fe1d3d05-4763-4d68-ac67-b275fb5a623f",
  "deployment_id": "4ee9dd76-b7df-4c58-bdf0-75e685d18772",
  "release_id": "99a42a73-22ef-4b40-aac9-a2bb80bc33b6",
  "build": 43,
  "version": "1.4.3",
  "product": "meteo",
  "hardware_revision": "v1",
  "chip": "esp32",
  "ota_layout": "meteo-ab-v1",
  "signing_profile": "meteo-prod-1",
  "size": 1048576,
  "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
  "url": "https://ota.example.cz/api/v1/releases/99a42a73-22ef-4b40-aac9-a2bb80bc33b6/firmware",
  "offer_expires_at": "2026-10-23T12:10:00Z"
}
```

Nabídka platí 10 minut pro zahájení pokusu. URL neobsahuje tajemství a vyžaduje device token. Opakovaný check-in se stejným UUID a stejným normalizovaným tělem vrací přesně uloženou odpověď, i pokud nabídka mezitím vypršela. Klient pak provede nový check-in s novým UUID. Stejné UUID s jiným tělem vrací `409 idempotency_conflict`.

Idempotence check-inu je garantována 7 dní od prvního přijetí a je oddělená od retence historie. Nový wake cyklus používá nové UUID. V jedné transakci se přijmou všechny události, kontakt i rozhodnutí, nebo žádné; neplatná událost vrací `409/422` a klient ji nemá bez opravy opakovat ve stejné dávce donekonečna.

## POST /attempts

Zahájí skutečný pokus až po lokální kontrole energie. Tento jeden dodatečný request se dělá pouze při OTA. Tělo obsahuje povinné `attempt_id` (UUID generované a uložené klientem), `offer_id` a `from_firmware` ve stejném tvaru jako `firmware` v check-inu.

Server zkontroluje vlastnictví nabídky, její platnost, aktivní přiřazení/vydání, kompatibilitu a retry politiku. Ověří, že výchozí firmware odpovídá check-inu, a atomicky dovolí maximálně jeden otevřený pokus zařízení. Vrátí `201` s `{ "attempt_id": "...", "status": "started" }`.

Stejné `attempt_id` a stejné vstupy vrátí `200` se současným stavem existujícího pokusu, bez dalšího započtení. Terminální stav v odpovědi znamená nestahovat. Stejné UUID s odlišným obsahem vrací `409`. Změna nabídky pod stejným UUID není dovolena. Expirovaná/zrušená nabídka nebo překročené pokusy vrátí `409 offer_not_startable`.

Klient před downloadem musí obdržet úspěšnou odpověď. Při ztrátě odpovědi opakuje stejné UUID. Nové nabídky samy nespotřebovávají limit pokusů.

## GET /releases/{release_id}/firmware?attempt_id={attempt_id}

Přenos je povolen jen zařízení s odpovídajícím otevřeným pokusem a dostupným přiřazeným vydáním. Neaktivní/withdrawn/zrušené přiřazení blokuje další přenos; pozdní výsledky lze přesto hlásit. Trasa bez `attempt_id` vrací `422`.

- `200`, `application/octet-stream`, přesný `Content-Length`, `ETag: "<sha256>"`, `Content-Encoding` se nepoužívá.
- `Cache-Control: private, no-store`; reverzní proxy nesmí odpověď transformovat ani komprimovat.
- MVP ignoruje `Range` a vrací celý soubor `200`; resume není podporované.
- Klient přidá `attempt_id` z lokálního stavu k manifestové URL.
- Server uloží `download_requested` před přenosem, HTTP výsledek a počet předaných bajtů jako diagnostiku. Neukládá z toho úspěch flashování. Při selhání auditního zápisu download nezahájí.
- Opakovaný GET v témže pokusu je povolen; dlouhý stream nedrží DB transakci. Kontrola oprávnění proběhne před streamem; následné zrušení neodvolá již posílané bajty.

## POST /ota-events

Volitelná okamžitá dávka `{ "events": [...] }` s 1–16 událostmi. Stejný formát událostí se používá v check-inu. `200` vrátí `{ "accepted_event_ids": ["..."] }`. Dávka je atomická.

```json
{
  "event_id": "9eeebad5-40c4-455e-977a-8e469d5e1506",
  "attempt_id": "e24bad5d-069c-43f5-992b-7314b74b1d79",
  "sequence": 2,
  "status": "confirmed",
  "running_firmware": {
    "build": 43,
    "version": "1.4.3",
    "sha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
  },
  "occurred_at": null,
  "error_code": null
}
```

Povinné jsou `event_id`, `attempt_id`, `sequence` (kladné celé číslo), `status`, `running_firmware`. `occurred_at` je nullable klientský čas, `error_code` nullable text do 64 znaků. Stavy klienta jsou `image_verified`, `confirmed`, `failed`, `rolled_back`. Diagnostický text je volitelný, omezený na 256 znaků, bez tajemství. `failed` vyžaduje `error_code`; příklady: `network_timeout`, `hash_mismatch`, `signature_invalid`, `flash_write_failed`, `power_low`, `self_test_failed`.

UUID události a dvojice `(attempt_id, sequence)` jsou unikátní. Identická duplicita je znovu potvrzena, změněný obsah vrací `409`. Události lze přijmout mimo pořadí a některé přeskočit. `confirmed` vyžaduje cílový build a hash, `rolled_back` výchozí build a hash. `failed` může hlásit výchozí nebo cílový firmware podle fáze selhání. Přijetí výsledku nevyžaduje stále aktivní přiřazení ani dostupné vydání.

Server používá `sequence` k projekci stavu, nikoli nedůvěryhodný klientský čas. Opožděný nižší mezistav po terminálním výsledku se uloží, ale stav nezhorší. Konfliktní terminální výsledek vrací `409 terminal_conflict`. Podrobnosti v [OTA stavech](data-and-states.md).

## Správcovské API a UI

Správcovské JSON operace jsou pod `/api/v1/admin`, UI pod `/admin`. Používají session správce a `X-CSRF-Token` u změn. Přihlášení/odhlášení je přes UI; automatizace přes API je mimo MVP. Všechny seznamy používají `limit` 1–100 (výchozí 50) a neprůhledný `cursor`; odpověď `{ "items": [...], "next_cursor": null }`. Stabilní řazení je podle serverového času a ID sestupně.

| Metoda a cesta za /admin | Vstup / účel | Výsledek |
| --- | --- | --- |
| POST /devices | `name`, `product`, `hardware_revision`, `chip`, `ota_layout`, `signing_profile`, volitelně `min_ota_battery_mv` | 201, zařízení a jednorázový token |
| GET /devices; GET /devices/{id} | Přehled a detail; filtr produktu a stavu | 200 |
| POST /devices/{id}/rotate-token | Nový token, starý okamžitě neplatný | 200, token pouze jednou |
| POST /devices/{id}/revoke-token | Odvolání bez náhrady | 204 |
| POST /releases | Multipart: `file` a `metadata` jako JSON string; kompatibilita, `build`, `version`, `notes` | 201; 409 při stejném produktu/build |
| GET /releases; GET /releases/{id} | Metadata, filtry produkt/hardware/stav | 200 |
| PATCH /releases/{id} | Pouze `notes` do 4096 znaků | 200 |
| POST /releases/{id}/withdraw | `reason` do 256 znaků | 200; opakování bez další změny |
| POST /deployments | `device_id`, `release_id` | 201; 409 při aktivním přiřazení nebo downgrade |
| GET /deployments; GET /deployments/{id} | Filtry zařízení/vydání/stav | 200 |
| POST /deployments/{id}/cancel | `reason` | 200; idempotentní |
| POST /deployments/{id}/retry | `reason`; odblokování chybného/neznámého výsledku | 200; nová retry generace |
| GET /devices/{id}/history | Filtry `kind`, `since`, `until`, případně `release_id` | 200, společná časová osa |

Textové identifikátory kompatibility mají 1–64 ASCII znaků `[A-Za-z0-9._-]`, jméno zařízení 1–128 znaků. Upload `metadata` obsahuje `product`, `hardware_revision`, `chip`, `ota_layout`, `signing_profile`, `build`, `version`; `notes` je volitelné. Server vypočítá velikost a hash, nepřebírá je od správce. Seznamy nikdy nevracejí token/digest hesla. Správcovské změny se auditují.

## Provozní endpointy

`GET /health/live` vrací `200`, pokud proces odpovídá. `GET /health/ready` vrací `200`, pokud je schéma aktuální a DB i datový adresář dostupné, jinak `503`. Veřejně nezveřejňují interní cesty ani výjimky. Nezapisují check-in ani historii zařízení.
