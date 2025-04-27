# Optimierungsmodell für ein Energiesystem (PV + Wind + Batterie)

## Übersicht

Dieses Python-Skript modelliert und optimiert ein netzgekoppeltes Energiesystem, bestehend aus Photovoltaik (PV), Windkraftanlagen und einem Batteriespeicher. Das Ziel ist es, die kostenoptimalen Kapazitäten für diese Komponenten zu bestimmen und deren Betrieb über ein Jahr zu simulieren, um einen gegebenen Strombedarf zu decken. Die Optimierung minimiert dabei die annualisierten Gesamtkosten des Systems.

## Funktionalität

* **Kapazitätsoptimierung:** Berechnet die optimalen Nennleistungen für PV (MWp) und Wind (MW) sowie die optimale Energie- (MWh) und Leistungskapazität (MW) der Batterie.
* **Betriebssimulation:** Simuliert die Energieflüsse (Erzeugung, Bedarf, Netzbezug/-einspeisung, Batterieladung/-entladung, Abregelung) in 15-Minuten-Auflösung über ein ganzes Jahr.
* **Wirtschaftlichkeitsanalyse:**
    * Berechnet die annualisierten Gesamtkosten des Systems.
    * Ermittelt Stromgestehungskosten (LCOE) für das Gesamtsystem (bezogen auf den gedeckten Bedarf).
    * Bestimmt Kennzahlen wie Autarkiegrad und Erneuerbare Deckungsrate.
* **Ausgabe:** Generiert detaillierte Ergebnisse auf der Konsole, Diagramme (Jahresprofil von Last/Erzeugung, Kostenlandschaft) und exportiert die detaillierten Zeitreihen in eine Excel-Datei.

## Funktionsweise des Codes (Struktur)

Der Code ist in Abschnitte gegliedert:

1.  **Eingabedaten & Annahmen:** Definition aller technischen und ökonomischen Parameter (Kosten, Lebensdauern, Wirkungsgrade, Strompreise, Zinssatz, Lastprofil-Basis, Ertragsdaten etc.). *Anpassungen für eigene Szenarien sind hier möglich.*
2.  **Zeitreihengenerierung:** Erstellung hochaufgelöster Jahresprofile für PV- und Winderzeugung pro MW installierter Leistung aus Monatsdaten, unter Berücksichtigung von Nachtabschaltung (PV). Erstellung des Einspeisevergütungsprofils.
3.  **Annuitätenfaktor:** Berechnung des Faktors zur Umwandlung von Investitionskosten in jährliche Kosten.
4.  **Optimierungsmodell-Definition (PuLP):** Definition des Ziels, der Variablen (Kapazitäten, Betriebsdaten pro Zeitschritt), der Zielfunktion (Summe der annualisierten Kosten/Erlöse) und der Nebenbedingungen (Energiebilanz, Batteriephysik, Limits).
5.  **Optimierung lösen:** Übergabe des Modells an den CBC-Solver.
6.  **Ergebnisauswertung:** Extrahieren der optimalen Werte, Berechnung von Bilanzen, Kosten und Kennzahlen.
7.  **Visualisierung der Kostenlandschaft:** (Optional, rechenintensiv) Erstellt ein Konturdiagramm der Kosten für verschiedene PV/Wind-Kombinationen unter Annahme der zuvor optimierten Batteriegröße.

## Optimierungslogik

Das Skript nutzt ein **Lineares Optimierungsmodell (LP)** mit `PuLP`.

* **Ziel:** Minimierung der **annualisierten Gesamtkosten**.
* **Entscheidungsvariablen:**
    * Kapazitäten: $Cap_{PV}$ (MWp), $Cap_{Wind}$ (MW), $Cap_{Batt}^{MWh}$ (MWh), $Cap_{Batt}^{MW}$ (MW)
    * Betrieb (pro Zeitschritt $t$): $P^{GridBuy}_t$, $P^{GridSell}_t$, $P^{Curtail}_t$, $P^{BattCh}_t$, $P^{BattDis}_t$, $SoC_t$.
* **Zielfunktion (vereinfacht):**
    $$ \min \sum_{tech \in \{PV, W\}} (\text{Ann. CAPEX}_{tech} + \text{Ann. OPEX}_{tech}) + (\text{Ann. CAPEX}_{Batt, MW} + \text{Ann. OPEX}_{Batt, MWh}) + \sum_{t} (\text{Netzbezugskosten}_t - \text{Einspeiseerlöse}_t) $$
    *Hinweis:* In diesem Code-Snippet basiert das annualisierte Batterie-CAPEX (`Ann. CAPEX_{Batt, MW}`) auf der Leistung ($Cap_{Batt}^{MW}$), während das annualisierte Batterie-OPEX (`Ann. OPEX_{Batt, MWh}`) auf der Energiekapazität ($Cap_{Batt}^{MWh}$) basiert. Siehe die Definitionen von `annualized_capex_battery` und `total_opex_battery` in Abschnitt 4.
* **Wichtige Nebenbedingungen (Constraints):**
    * **Energiebilanz (für jeden $t$):** Energiequellen = Energiesenken
        $$ P^{Gen}_{PV,t} + P^{Gen}_{Wind,t} + P^{GridBuy}_t + P^{BattDis}_t = D_t + P^{GridSell}_t + P^{Curtail}_t + P^{BattCh}_t $$
    * **Batterie-Ladezustand ($SoC$) (für jeden $t$):** Berücksichtigt Zu-/Abfluss und Wirkungsgrad ($\eta_{Batt}$).
        $$ SoC_{t+1} = SoC_t + P^{BattCh}_t \cdot \sqrt{\eta_{Batt}} - P^{BattDis}_t / \sqrt{\eta_{Batt}} $$
    * **Batterie-Leistungsgrenzen (für jeden $t$):** $P^{BattCh/Dis}_t \le Cap_{Batt}^{MW} \cdot \Delta t$
    * **Batterie-Kapazitätsgrenzen (für jeden $t$):** $SoC_{min} \cdot Cap_{Batt}^{MWh} \le SoC_t \le Cap_{Batt}^{MWh}$
    * **Zyklischer Betrieb:** $SoC_{N} = SoC_0$.
    * **Nicht-Negativität:** Alle Variablen $\ge 0$.

Der CBC-Solver findet die Werte für die Variablen, die alle Bedingungen erfüllen und die Kosten minimieren.

## Eingabeparameter

Die zentralen Eingabeparameter werden in Abschnitt 1 des Skripts definiert (z.B. `specific_capex_...`, `lifetime_...`, `discount_rate`, `demand_per_hour_kwh`, `monthly_yield_...` etc.).

## Ausgaben

1.  **Konsolenausgaben:** Optimale Kapazitäten, Kostenaufschlüsselung, Jahresenergiebilanz, System-LCOE, Autarkiegrad etc.
2.  **Diagramme (`.png`):**
    * `lastprofil_erzeugung_jahr_mit_batterie.png`: Jahresverlauf Last/Erzeugung.
    * `kostenlandschaft_optimierung_mit_batterie.png`: (Optional) Kostenkontur PV vs. Wind.
3.  **Excel-Datei:**
    * `energiebilanz_15min_mit_batterie.xlsx`: Detaillierte 15-Minuten-Zeitreihen aller Energieflüsse.

## Anforderungen & Installation

* Python 3.x
* Benötigte Bibliotheken: `pulp`, `numpy`, `pandas`, `matplotlib`, `openpyxl`

    Installation über pip:
    ```bash
    pip install pulp numpy pandas matplotlib openpyxl
    ```
    PuLP benötigt einen installierten LP-Solver (z.B. CBC).

## Benutzung

1.  **Parameter anpassen:** Passe die Werte in Abschnitt 1 des Skripts an.
2.  **Ausführen:**
    ```bash
    python dein_skriptname.py
    ```
3.  **Ergebnisse prüfen:** Analysiere die Konsolenausgaben, `.png`-Dateien und die `.xlsx`-Datei.

## Limitationen & Annahmen (Basierend auf diesem Code)

* **Erzeugungsprofile:** Basieren auf Monatsmitteln, keine Simulation von Dunkelflauten oder kurzfristigen Wettereffekten.
* **Lastprofil:** Als konstant über das Jahr angenommen.
* **Perfekte Voraussicht:** Das Modell kennt alle zukünftigen Werte innerhalb des Jahres.
* **Vereinfachte Kosten/Lebensdauer:** Keine Degradation, konstante Kosten/Preise angenommen.
* **Netz:** Keine Berücksichtigung von Netzengpässen etc.
* **Batterie Kostenmodell:** Siehe Hinweis bei der Zielfunktion bezüglich CAPEX/OPEX-Bezug.
