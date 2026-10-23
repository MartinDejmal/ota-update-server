# OTA Update Server

Server pro distribuci firmware do bateriových a solárních ESP32 zařízení, která se typicky jednou za 15 minut probouzejí z deep sleepu.

Zařízení při probuzení kontaktuje server přes HTTPS, oznámí běžící firmware a získá případný OTA manifest. Server uchovává binárky, přiřazení aktualizací a historii kontaktů i výsledků.

**Stav projektu:** implementační specifikace, revize 1, 2026-10-23. Aplikace, Docker image ani ESP32 handler zatím nejsou implementované. Konfigurační příklady popisují cílovou implementaci.

## Dokumentace

| Dokument | Obsah |
| --- | --- |
| [Architektura a rozsah](docs/architecture.md) | Komponenty, rozhodování, bezpečnost, administrace |
| [API v1](docs/api.md) | Požadavky, odpovědi, autentizace, idempotence a chyby |
| [Data a OTA stavy](docs/data-and-states.md) | Datový model, historie, pokusy, potvrzení a rollback |
| [Docker a provoz](docs/operations.md) | Volume, konfigurace, zálohy, obnova a údržba |
| [Integrace ESP32](docs/esp32.md) | Klientský cyklus, NVS, kontrola energie a bootu |
| [Plán implementace a akceptace](docs/implementation-plan.md) | Etapy, struktura aplikace a ověřovací scénáře |

## Základní rozhodnutí

- Python, FastAPI, Pydantic, SQLAlchemy a Alembic; webová administrace přes Jinja2.
- Jedna instance aplikace, jeden worker, SQLite na lokálním persistentním volume.
- Binárky jako neměnné soubory adresované SHA-256 mimo Docker image.
- Explicitní přiřazení vydání konkrétnímu zařízení; upload sám aktualizaci nespouští.
- Samostatný OTA check-in vedle existující služby pro měření.
- Vlastní token každého zařízení a oddělené přihlášení správce.
- Úspěch pouze po explicitním potvrzení zařízení; download ani změna pozorované verze samy nestačí.

Technologické verze se při implementaci zafixují v lockfile a image. Dokumentace je smlouvou zamýšleného chování; runtime OpenAPI a testy s ní musí zůstat v souladu.
