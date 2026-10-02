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

Alle Entitäten gehören zum Gerät «CKW». Preise in CHF/kWh, Zustände werden zu jeder Viertelstunde neu berechnet.

**Preise**
- `sensor.ckw_current_price` – aktueller Preis
- `sensor.ckw_next_price` – Preis des nächsten Slots (Attribut `starts_at`)
- `sensor.ckw_price_in_one_hour` – Preis in einer Stunde
- `sensor.ckw_price_rank_today` – Rang des aktuellen Slots heute in % (0 = günstigster, 100 = teuerster)

**Tagesstatistik**
- `sensor.ckw_min_price`, `sensor.ckw_max_price`, `sensor.ckw_avg_price` – heute
- `sensor.ckw_min_price_tomorrow`, `sensor.ckw_max_price_tomorrow`, `sensor.ckw_avg_price_tomorrow` – morgen, sobald CKW die Preise veröffentlicht hat (sonst unbekannt; ab 18 Uhr wird alle 30 Minuten nachgefragt)

**Fenster** (heute und morgen, nur noch nicht beendete Slots)
- `sensor.ckw_cheapest_2h_window`, `sensor.ckw_cheapest_4h_window`, `sensor.ckw_most_expensive_2h_window` – Startzeit, Attribute `end` und `avg_price`
- `binary_sensor.ckw_in_cheapest_2h_window`, `..._in_cheapest_4h_window`, `..._in_most_expensive_2h_window` – an, solange die aktuelle Zeit im Fenster liegt

**Sonstiges**
- `sensor.ckw_all_prices` – Anzahl Preisslots, alle Slots als Attribut `prices`

Die Sensoren bleiben verfügbar, solange zwischengespeicherte Preise vorhanden sind, auch wenn ein API-Abruf fehlschlägt. Gibt es für die aktuelle Zeit keinen Preis, ist `sensor.ckw_current_price` unbekannt.

Schwellen und Schaltlogik definierst du in deinen Automationen. Seit 2.0.0b4 gibt es keinen Schwellenwert und keinen Binary Sensor `below_threshold` mehr.
