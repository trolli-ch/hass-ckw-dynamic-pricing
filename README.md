<p align="center">
  <img src="docs/logo.png" alt="CKW Dynamic Pricing" width="300">
</p>

# CKW Dynamic Pricing for Home Assistant

Integration für dynamische Strompreise von CKW zur ISG Wärmepumpen-Steuerung.

## Installation mit HACS

1. HACS öffnen → Integrationen
2. 3 Punkte → Custom repositories
3. URL eingeben: `https://github.com/trolli-ch/hass-ckw-dynamic-pricing`
4. Kategorie: Integration
5. "Erstellen"
6. Nach "CKW Dynamic Pricing" suchen und installieren
7. Home Assistant neu starten

Nach Installation:
- Einstellungen → Geräte und Dienste
- "+ Neue Integration erstellen"
- "CKW Dynamic Pricing" suchen
- Bestätigen, eine weitere Konfiguration ist nicht nötig

## Entitäten

- `sensor.ckw_current_price` – aktueller Preis (CHF/kWh), aktualisiert sich zu jeder Viertelstunde
- `sensor.ckw_min_price`, `sensor.ckw_max_price`, `sensor.ckw_avg_price` – Tagesstatistik (CHF/kWh)
- `sensor.ckw_all_prices` – Anzahl Preisslots, alle Slots als Attribut `prices`

Schwellen und Schaltlogik definierst du in deinen Automationen auf Basis von `sensor.ckw_current_price`. Seit 2.0.0b4 gibt es keinen Schwellenwert und keinen Binary Sensor mehr.
