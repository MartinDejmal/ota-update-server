# Docker a provoz

## Cílové nasazení

Jedna instance Linux kontejneru, jeden Uvicorn worker, lokální persistentní volume pro SQLite i binárky. TLS ukončuje existující proxy nebo samostatný Caddy kontejner. Přímý backendový port není dostupný z internetu. CPU architektura hostitele se zohlední při sestavení image; ARM64 i AMD64 se ověří až v implementační CI.

Následující Compose je návrh nasazení, nikoli dnes funkční balíček. `Dockerfile`, příkazy `ota-server` i aplikace budou vytvořeny v implementaci:

```yaml
services:
  ota-server:
    build: .
    command: ["ota-server", "serve", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
    init: true
    restart: unless-stopped
    user: "10001:10001"
    read_only: true
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=64m
    environment:
      PUBLIC_BASE_URL: https://ota.example.cz
      DATA_DIR: /data
      DISPLAY_TIMEZONE: Europe/Prague
      CHECKIN_RETENTION_DAYS: "90"
      MAX_FIRMWARE_BYTES: "8388608"
    volumes:
      - ota-data:/data
    ports:
      - "127.0.0.1:8000:8000"
    cap_drop: [ALL]
    security_opt:
      - no-new-privileges:true
    stop_grace_period: 30s
    healthcheck:
      test: ["CMD", "ota-server", "healthcheck", "--url", "http://127.0.0.1:8000/health/ready"]
      interval: 30s
      timeout: 5s
      retries: 3
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  ota-data:
```

Tento příklad používá proxy běžící na hostiteli, která forwarduje na localhost:8000. Proxy v kontejneru se místo toho spojí přes privátní Docker síť na `ota-server:8000`; `ports` backendu se vynechá. HTTP bez TLS je přípustné jen uvnitř tohoto spojení, nikoli pro ESP32 přes internet.

Dockerfile připraví prázdný `/data` s UID/GID 10001 a deklarovanými podadresáři. Při prvním vytvoření named volume se ověří práva; existující/bind volume musí správce připravit před startem. Proces práva neopravuje jako root. `/data/tmp` leží na stejném filesystemu jako `firmware`, aby publikování uploadu používalo atomický rename.

## Konfigurace

| Parametr | Výchozí / požadavek |
| --- | --- |
| `PUBLIC_BASE_URL` | Povinná absolutní HTTPS URL, bez uživatelských dat a query |
| `DATA_DIR` | `/data`; pouze lokální disk pro SQLite WAL |
| `DISPLAY_TIMEZONE` | `Europe/Prague`, IANA timezone |
| `MAX_FIRMWARE_BYTES` | 8 MiB; nezávisle se kontroluje skutečný OTA slot klienta |
| `CHECKIN_RETENTION_DAYS` | 90 |
| `OFFER_TTL_SECONDS` | 600 |
| `ATTEMPT_IDLE_TIMEOUT_SECONDS` | 1800 |
| `RETRY_BACKOFF_SECONDS` | 21600 |
| `MAX_ATTEMPTS_PER_GENERATION` | 3 |
| `TRUSTED_PROXY_IPS` | Prázdné; explicitní IP/CIDR proxy, ne `*` |
| `MAX_CONCURRENT_DOWNLOADS` | 4; po překročení 429 + Retry-After |
| `MAX_CONCURRENT_UPLOADS` | 1 |

Nastavení musí být validované při startu; chybné hodnoty znamenají ukončení procesu. Device tokeny a heslo správce se nedávají do image ani repozitáře. Ukládají se do DB jen v hashované podobě. Pro bootstrap správce slouží interaktivní `ota-server admin create`; reset session a hesla má vlastní CLI s auditem. Session cookie je náhodný neprůhledný token, jehož digest je uložen v DB.

## První spuštění a migrace

1. Sestavit připnutý image z lockfile; připravit volume a reverzní proxy s DNS/TLS.
2. Při zastavené aplikaci spustit `ota-server db upgrade` jako jednorázový kontejner nad stejným volume.
3. Interaktivně založit správce a spustit službu; ověřit live/ready a HTTPS z klientské sítě.
4. Registrovat testovací zařízení, bezpečně mu předat token a ověřit první check-in.
5. Nahrát podepsané testovací vydání, zkontrolovat metadata a přiřadit ho jen testovacímu zařízení.
6. Ověřit potvrzený výsledek, restart serveru a zachování historie.

`serve` nedělá automatické migrace; při nesouladu schématu odmítne start s jasnou chybou. Aktualizace serveru probíhá po záloze a zastavení služby. Návrat starého image je dovolen jen se slučitelným schématem; jinak je nutné obnovit zálohu. Chyba OTA serveru nesmí blokovat odesílání měření ze stanice.

## Zálohování a obnova

Zálohuje se DB, všechny referencované binárky a manifest zálohy obsahující verzi schématu/serveru a hashe. Certifikáty proxy se zálohují jejím postupem. Záloha DB obsahuje hashe tokenů a session, proto má omezený přístup a šifrované úložiště.

MVP postup je denní konzistentní offline záloha: zastavit aplikaci i CLI údržbu, zkopírovat celý `/data` včetně případných `-wal`/`-shm` souborů a ověřit kopii DB i hashe binárek. Neprovádět prosté kopírování samotného živého `ota.sqlite`. Pro pozdější online zálohy použít SQLite Backup API a neměnné artefakty podle snapshotu DB. [SQLite Backup API](https://www.sqlite.org/backup.html)

Obnova se nejprve provede do odděleného volume bez kontaktu produkčních zařízení. Ověří se schéma, `PRAGMA integrity_check`, existence a hash každého referencovaného artefaktu, přihlášení a čtení historie. Teprve pak se přepne provoz. Po obnově se zneplatní správcovské session. Starší snapshot může ztratit historii či znovu nabídnout starý záměr; před připojením klientů správce zkontroluje aktivní přiřazení. ESP32 kontrola běžícího hashe a lokální blacklist dále brání zbytečnému či chybnému přeflashování.

## Údržba a pozorovatelnost

Denně lze přes hostitelský scheduler spustit `ota-server maintenance run` v kontejneru. Úloha musí mít DB lease proti souběhu; maže retenční data po dávkách, uzavírá neaktivní pokusy a uklízí staré dočasné soubory. Nepřepíná přiřazení na úspěch. Osiřelé finální soubory pouze vypíše ke kontrole, nemaže automaticky.

Strukturované JSON logy: čas, trace ID, normalizovaná route, stav, latence a po autentizaci device/attempt ID. Bez Authorization, cookies, tokenů a celých těl. UI ukáže počet zařízení bez kontaktu, neznámé výsledky, chyby storage a neúspěšné aktualizace. „Offline“ je odvozený indikátor po 60 minutách bez kontaktu, není důkaz chyby zařízení ani OTA.

Při plném disku, DB lock timeoutu či nedostupném artefaktu server nevrací úspěch bez uloženého stavu. Vrací 503, loguje důvod a chrání stávající binárky. Nedostupnost jednoho souboru blokuje pouze jeho vydání. Readiness nekontroluje hashe všech souborů při každém volání; to dělá explicitní integrity audit.

## Zdroje

- [Docker: persistentní volumes](https://docs.docker.com/engine/storage/volumes/).
- [SQLite: WAL a omezení filesystemu](https://www.sqlite.org/wal.html).
- [FastAPI: Docker deployment](https://fastapi.tiangolo.com/deployment/docker/).
