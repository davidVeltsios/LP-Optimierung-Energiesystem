import pulp
import numpy as np
import pandas as pd
import datetime # Wird für Zeitberechnung benötigt
import math # Für Wurzelberechnung


# --- 1. Eingabedaten und Annahmen ---

print("--- Initialisiere Modellparameter ---")

# Zeitliche Auflösung
time_resolution_hours = 0.25 # 15 Minuten

# *** ANGEPASST: Feste Zeitschritte für 366 Tage (Jahr 2024) ***
days_in_period = 366 # 2024 ist ein Schaltjahr
num_timesteps = int(days_in_period * 24 / time_resolution_hours) # 366 * 24 * 4 = 35136
hours_in_period = num_timesteps * time_resolution_hours # Stundenzahl für diesen Zeitraum
print(f"Zeitschritte angepasst an Daten: {num_timesteps} (entspricht {hours_in_period} Stunden / {days_in_period} Tagen)")


# Konstantes Lastprofil (skaliert auf 366 Tage)
demand_per_hour_kwh = 3629
demand_per_timestep_kwh = demand_per_hour_kwh * time_resolution_hours
demand_per_timestep_mwh = demand_per_timestep_kwh / 1000
demand_profile_mwh = np.full(num_timesteps, demand_per_timestep_mwh) # Korrekte Länge
total_demand_period = np.sum(demand_profile_mwh) # Check ob Summe stimmt
print(f"Gesamtbedarf für Analyseperiode ({num_timesteps} Intervalle / {days_in_period} Tage): {total_demand_period:,.2f} MWh")

# Kosten PV & Wind
specific_capex_pv_eur_per_mw = 800 * 1000
specific_opex_pv_eur_per_mw_pa = 13.3 * 1000 # Pro Jahr
specific_capex_wind_eur_per_mw = 1600 * 1000
specific_opex_wind_eur_per_mw_pa = 32 * 1000 # Pro Jahr

# Kosten Batterie
specific_capex_battery_eur_per_mw  = 600 * 1000
specific_opex_battery_eur_per_mwh_pa = 6.65 * 1000 # Pro Jahr
print(f"Annahme Batterie CAPEX:  {specific_capex_battery_eur_per_mw/1000:.0f} k€/MW")
print(f"Annahme Batterie OPEX: {specific_opex_battery_eur_per_mwh_pa/1000:.1f} k€/MWh/Jahr")

# Ökonomische Parameter
discount_rate = 0.06
lifetime_pv_wind_years = 20
lifetime_battery_years = 15
print(f"Diskontierungsrate: {discount_rate:.1%}")
print(f"Lebensdauer PV/Wind: {lifetime_pv_wind_years} Jahre")
print(f"Annahme Lebensdauer Batterie: {lifetime_battery_years} Jahre")

# Batterie Technische Parameter
battery_efficiency = 0.88
battery_soc_min_percent = 0.10
try:
    if not (0 <= battery_efficiency <= 1): raise ValueError("Effizienz nicht zwischen 0 und 1.")
    charge_discharge_eff_sqrt = math.sqrt(battery_efficiency)
    if charge_discharge_eff_sqrt > 1e-9: charge_discharge_eff_sqrt_inv = 1.0 / charge_discharge_eff_sqrt
    elif battery_efficiency == 0: print("WARNUNG: Batt Wirkungsgrad 0."); charge_discharge_eff_sqrt_inv = 1e12
    else: print("WARNUNG: Batt Wirkungsgrad nahe Null!"); charge_discharge_eff_sqrt_inv = 1.0 / 1e-9
except ValueError as e: print(f"WARNUNG: Batterie Wirkungsgrad ungültig ({battery_efficiency}). Fallback: 100%. Fehler: {e}"); charge_discharge_eff_sqrt = 1.0; charge_discharge_eff_sqrt_inv = 1.0
print(f"Annahme Batterie Wirkungsgrad (round-trip): {battery_efficiency:.1%}")
print(f"Annahme Min. Ladezustand (SoC): {battery_soc_min_percent:.1%}")

# Netzinteraktion
grid_purchase_price_eur_per_mwh = 169.9
feed_in_tariff_eur_per_mwh = 50
negative_price_hours = 459 # Absolute Anzahl Stunden mit 0€ Vergütung
print(f"Netzbezugspreis: {grid_purchase_price_eur_per_mwh:.2f} €/MWh")
print(f"Einspeisevergütung: {feed_in_tariff_eur_per_mwh:.2f} €/MWh")
print(f"Stunden mit neg. Preisen (Vergütung=0): {negative_price_hours} h")

# --- 2. Lade reale Zeitreihen aus Excel ---
print("\n--- Lade reale Ertragsdaten aus Excel ---")
excel_filename = r"C:\Users\Anwender\Desktop\Projekt Energiesystem\data\Datenbank_Ertragsprofil.xlsx" 
print("\n!!! WICHTIGER HINWEIS !!!")
print(f"Sicherstellen, dass die Excel-Datei '{excel_filename}' exakt {num_timesteps} Zeilen")
print(f"(für {days_in_period} Tage von 01.01.2024 00:00 bis 31.12.2024 23:45) enthält.")
print("Andernfalls wird das Skript mit einem Fehler abbrechen.")

try:
    print(f"Lese Daten aus: {excel_filename}")
    df_input = pd.read_excel(excel_filename, sheet_name=0, header=0)
    print(f"Datei geladen. {len(df_input)} Zeilen gefunden.")

    # *** ANGEPASST: Überprüfen, ob die Anzahl der Zeitschritte übereinstimmt (jetzt mit 35136) ***
    if len(df_input) != num_timesteps:
         raise ValueError(f"Fehler: Anzahl Zeilen in Excel ({len(df_input)}) stimmt nicht mit erwarteten Zeitschriten ({num_timesteps}) für {days_in_period} Tage überein. Bitte Excel-Datei prüfen.")

    try:
        timestamp_col = df_input.columns[0]; wind_mwh_col = df_input.columns[1]; pv_mwh_col = df_input.columns[2]
        wind_cap_col = df_input.columns[3]; pv_cap_col = df_input.columns[4]
        # Lese installierte Leistung nur, wenn Spalten vorhanden sind (für spezifische Erträge)
        if len(df_input.columns) >= 5:
             installed_wind_cap = df_input[wind_cap_col].iloc[0]; installed_pv_cap = df_input[pv_cap_col].iloc[0]
             print(f"Aus Excel gelesene installierte Leistung (Basis für spezif. Ertrag): Wind={installed_wind_cap:.2f} MW, PV={installed_pv_cap:.2f} MWp")
             if installed_wind_cap <= 1e-6 or installed_pv_cap <= 1e-6: raise ValueError(f"Fehler: Installierte Leistung in Excel ungültig (<= 0).")
             specific_yield_wind_mwh_per_mw = (df_input[wind_mwh_col].values / installed_wind_cap)
             specific_yield_pv_mwh_per_mw = (df_input[pv_mwh_col].values / installed_pv_cap)
        else:
             # Fallback, wenn Kapazitätsspalten fehlen: Nimm die MWh-Werte direkt an, setze spezifisch = MWh
             # Dies funktioniert nur sinnvoll, wenn die Optimierungsvariablen später als 1 MW interpretiert werden.
             # Oder: Setze Kapazität auf 1 MW als Annahme.
             print("WARNUNG: Spalten für installierte Leistung nicht gefunden. Nehme an, die Ertragsspalten sind spezifisch (pro 1 MW).")
             installed_wind_cap = 9294
             installed_pv_cap = 1674
             specific_yield_wind_mwh_per_mw = df_input[wind_mwh_col].values
             specific_yield_pv_mwh_per_mw = df_input[pv_mwh_col].values


        specific_yield_wind_mwh_per_mw = np.maximum(0, specific_yield_wind_mwh_per_mw)
        specific_yield_pv_mwh_per_mw = np.maximum(0, specific_yield_pv_mwh_per_mw)
        print("Reale Ertragsprofile erfolgreich geladen und spezifische Profile berechnet.")
    except IndexError: raise IndexError("Fehler: Nicht genügend Spalten in Excel gefunden (mind. A-C erwartet, A-E für spez. Ertrag).")
    except KeyError as e: raise KeyError(f"Fehler: Spalte {e} konnte nicht zugeordnet werden.")

    # Kontrollen (aktualisiert für 366 Tage)
    total_spec_yield_pv = np.sum(specific_yield_pv_mwh_per_mw); total_spec_yield_wind = np.sum(specific_yield_wind_mwh_per_mw)
    # Ausgabe auf MWh/MW pro Periode (366 Tage)
    print(f"\nKontrolle Ertrag pro MW (Periode, aus Daten): PV={total_spec_yield_pv:.2f} MWh/MWp, Wind={total_spec_yield_wind:.2f} MWh/MW")

    # Einspeisevergütungsprofil (passt sich an num_timesteps an)
    # Umrechnung von Stunden in Timesteps: Anzahl Stunden * (Intervalle pro Stunde)
    timesteps_per_hour = 1 / time_resolution_hours
    negative_price_timesteps = negative_price_hours * timesteps_per_hour # Stunden in Timesteps umrechnen
    num_negative_timesteps = int(min(negative_price_timesteps, num_timesteps)) # Absolute Anzahl TS, max. alle TS
    feed_in_tariff_profile_eur_per_mwh = np.full(num_timesteps, feed_in_tariff_eur_per_mwh)
    np.random.seed(42) # Für Reproduzierbarkeit
    random_indices = np.random.choice(num_timesteps, num_negative_timesteps, replace=False)
    feed_in_tariff_profile_eur_per_mwh[random_indices] = 0
    print(f"Einspeiseprofil: {num_negative_timesteps} Zeitschritte mit 0 € Vergütung generiert.")

except FileNotFoundError: print(f"FEHLER: Excel-Datei '{excel_filename}' nicht gefunden."); exit()
except ImportError: print("FEHLER: Benötigte Bibliotheken ('pandas', 'openpyxl') fehlen. Bitte installieren."); exit()
except ValueError as e: print(f"FEHLER bei der Datenverarbeitung: {e}"); exit()
except Exception as e: print(f"FEHLER beim Laden/Verarbeiten der Excel-Datei: {e}"); exit()

# --- 3. Annuitätenfaktor berechnen ---
# ... (Funktion bleibt unverändert) ...
def annuity_factor(rate, years):
    if years <= 0: return 0;
    if rate == 0: return 1 / years # Sonderfall Zinssatz 0

    # Rate ggf. anpassen, wenn sie extrem klein ist
    if rate < 1e-9:
        # print(f"WARNUNG: Annuitätsfaktor - sehr kleiner Zinssatz ({rate}) wird auf 1e-9 angehoben.") # Weniger Output
        rate = 1e-9

    # q = 1 + rate *jetzt für alle gültigen Raten definieren*
    q = 1 + rate

    try:
        qn = q**years
        denominator = qn - 1

        # Verhindere Division durch Null im Hauptterm (sollte bei rate != 0 kaum vorkommen)
        if abs(denominator) < 1e-9:
             # print(f"WARNUNG: Annuitätsfaktor-Nenner nahe Null für rate={rate}, years={years}") # Weniger Output
             # Fallback auf 1/years wie bei rate=0 könnte sinnvoll sein
             try:
                 return 1 / years
             except ZeroDivisionError: # Falls years auch 0 ist (bereits oben abgefangen)
                 return 0

        # Hauptformel
        return (rate * qn) / denominator

    except OverflowError:
        # Fehler bei sehr großen Jahren oder Raten
        print(f"ERROR: Overflow bei Annuitätsfaktor-Berechnung für rate={rate}, years={years}.")
        return 0 # Im Fehlerfall 0 zurückgeben
    except Exception as e:
        # Andere unerwartete Fehler abfangen
        print(f"ERROR: Unerwarteter Fehler bei Annuitätsfaktor-Berechnung: {e}")
        return 0

af_pv_wind = annuity_factor(discount_rate, lifetime_pv_wind_years); af_battery = annuity_factor(discount_rate, lifetime_battery_years)
print(f"\nAnnuitätsfaktor PV/Wind (r={discount_rate:.1%}, n={lifetime_pv_wind_years}): {af_pv_wind:.4f}")
print(f"Annuitätsfaktor Batterie (r={discount_rate:.1%}, n={lifetime_battery_years}): {af_battery:.4f}")

# --- 4. Optimierungsproblem definieren ---
print("\n--- Definiere Optimierungsmodell ---")
# *** ANGEPASST: Modellname ***
model = pulp.LpProblem(f"Renewable_Energy_System_Optimization_{days_in_period}Days", pulp.LpMinimize)
# Variablen (verwenden das angepasste num_timesteps)
pv_capacity_mw = pulp.LpVariable("PV_Capacity_MWp", lowBound=0); wind_capacity_mw = pulp.LpVariable("Wind_Capacity_MW", lowBound=0)
battery_capacity_mwh = pulp.LpVariable("Battery_Capacity_MWh", lowBound=0); battery_power_mw = pulp.LpVariable("Battery_Power_MW", lowBound=0)
timesteps = range(num_timesteps); soc_timesteps = range(num_timesteps + 1) # SoC braucht t=0 bis t=num_timesteps
grid_import = pulp.LpVariable.dicts("Grid_Import", timesteps, lowBound=0); grid_export = pulp.LpVariable.dicts("Grid_Export", timesteps, lowBound=0)
curtailment = pulp.LpVariable.dicts("Curtailment", timesteps, lowBound=0); battery_soc = pulp.LpVariable.dicts("Battery_SoC", soc_timesteps, lowBound=0)
battery_charge = pulp.LpVariable.dicts("Battery_Charge", timesteps, lowBound=0); battery_discharge = pulp.LpVariable.dicts("Battery_Discharge", timesteps, lowBound=0)
print("Variablen definiert.")

# Zielfunktion (Kosten sind weiterhin "pro Jahr", basierend auf Annuitäten)
# Die Betriebsoptimierung minimiert jedoch die Kosten/Erlöse über die tatsächliche Periode (366 Tage)
annualized_capex_pv_wind =  pv_capacity_mw * af_pv_wind * specific_capex_pv_eur_per_mw + wind_capacity_mw * af_pv_wind * specific_capex_wind_eur_per_mw
annualized_capex_battery =  battery_power_mw * af_battery *  specific_capex_battery_eur_per_mw
total_annualized_capex = annualized_capex_pv_wind + annualized_capex_battery

# OPEX sind auch Jahreswerte
total_opex_pv_wind = pv_capacity_mw * specific_opex_pv_eur_per_mw_pa + wind_capacity_mw * specific_opex_wind_eur_per_mw_pa
total_opex_battery = battery_capacity_mwh * specific_opex_battery_eur_per_mwh_pa # OPEX Batterie pro MWh Kapazität
total_annual_opex = total_opex_pv_wind + total_opex_battery

# Netzinteraktionskosten/-erlöse beziehen sich auf die SUMME über die PERIODE (366 Tage)
total_grid_import_cost_period = pulp.lpSum(grid_import[t] * grid_purchase_price_eur_per_mwh for t in timesteps)
total_feed_in_revenue_period = pulp.lpSum(grid_export[t] * feed_in_tariff_profile_eur_per_mwh[t] for t in timesteps) # Verwendet das Profil

# Zielfunktion: Annualisierte Investitions- und Fixkosten + Betriebskosten (Netzbezug) der Periode - Betriebserlöse (Einspeisung) der Periode
# WICHTIG: Diese Mischung ist üblich, kann aber zu leichten Inkonsistenzen führen, wenn man z.B. LCOE berechnet.
# Alternativ könnte man die Netzinteraktionskosten/-erlöse auf ein Jahr hochrechnen, aber das verzerrt bei stark saisonalen Profilen.
# Wir bleiben bei der üblichen Methode: Ann. CAPEX/OPEX + Perioden-Netzkosten/-erlöse
model += (total_annualized_capex + total_annual_opex + total_grid_import_cost_period - total_feed_in_revenue_period), "Total_Annualized_System_Cost"
print("Zielfunktion definiert.")

# Nebenbedingungen (laufen jetzt über 35136 Zeitschritte)
print("Definiere Nebenbedingungen...")
for t in timesteps:
    # Energiebilanz: Erzeugung + Netzbezug + Batterieentladung = Bedarf + Netzeinspeisung + Abregelung + Batterieladung
    available_pv_gen = specific_yield_pv_mwh_per_mw[t] * pv_capacity_mw; available_wind_gen = specific_yield_wind_mwh_per_mw[t] * wind_capacity_mw
    model += available_pv_gen + available_wind_gen + grid_import[t] + battery_discharge[t] == demand_profile_mwh[t] + grid_export[t] + curtailment[t] + battery_charge[t], f"Energy_Balance_{t}"

    # Batterie SoC Update: SoC(t+1) = SoC(t) + Ladung * Wirkungsgrad_in - Entladung / Wirkungsgrad_out
    # Mit Roundtrip-Effizienz: efficiency = eff_in * eff_out => eff_in = sqrt(eff), eff_out = sqrt(eff)
    # SoC(t+1) = SoC(t) + charge[t] * sqrt(eff) - discharge[t] / sqrt(eff)
    model += battery_soc[t+1] == battery_soc[t] + battery_charge[t] * charge_discharge_eff_sqrt - battery_discharge[t] * charge_discharge_eff_sqrt_inv, f"Battery_SoC_Update_{t}"

    # Batterie Leistungslimits (Laden/Entladen)
    model += battery_charge[t] <= battery_power_mw * time_resolution_hours, f"Battery_Charge_Power_Limit_{t}"
    model += battery_discharge[t] <= battery_power_mw * time_resolution_hours, f"Battery_Discharge_Power_Limit_{t}"

    # Batterie SoC Grenzen (bezogen auf Energiekapazität MWh)
    # WICHTIG: SoC(t) ist der Zustand *vor* der Aktion in Zeitschritt t.
    model += battery_soc[t] >= battery_soc_min_percent * battery_capacity_mwh, f"Battery_SoC_Min_Limit_{t}"
    model += battery_soc[t] <= battery_capacity_mwh, f"Battery_SoC_Max_Limit_{t}" # Max = 100% der Kapazität

# SoC Grenzen auch für den letzten Zeitschritt (t = num_timesteps) sicherstellen
model += battery_soc[num_timesteps] >= battery_soc_min_percent * battery_capacity_mwh, f"Battery_SoC_Min_Limit_End"
model += battery_soc[num_timesteps] <= battery_capacity_mwh, f"Battery_SoC_Max_Limit_End"

# Zyklische Randbedingung für den Speicher: SoC am Ende = SoC am Anfang
model += battery_soc[num_timesteps] == battery_soc[0], "Battery_Cyclic_SoC"
print("Nebenbedingungen definiert.")

# --- 5. Optimierung lösen ---
print(f"\n--- Starte Optimierung ({num_timesteps} Zeitschritte / {days_in_period} Tage) ---")
start_time = datetime.datetime.now()
solver = pulp.PULP_CBC_CMD(msg=True) # msg=True zeigt Solver-Output
model.solve(solver)
end_time = datetime.datetime.now()
print(f"Optimierung abgeschlossen. Dauer: {end_time - start_time}")

# --- 6. Ergebnisse ausgeben ---
print("\n--- Optimierungsergebnisse ---")
print(f"Status: {pulp.LpStatus[model.status]}")
opt_pv_mw = 0; opt_wind_mw = 0; opt_batt_mwh = 0; opt_batt_mw = 0; opt_total_cost = np.inf

if pulp.LpStatus[model.status] == 'Optimal':
    opt_pv_mw = pv_capacity_mw.varValue; opt_wind_mw = wind_capacity_mw.varValue
    opt_batt_mwh = battery_capacity_mwh.varValue; opt_batt_mw = battery_power_mw.varValue
    opt_total_cost = pulp.value(model.objective) # Dies sind die *annualisierten* Systemkosten + *Perioden*-Netzkosten/-Erlöse

    print(f"\nOptimale Kapazitäten:")
    print(f"  PV Leistung: {opt_pv_mw:.2f} MWp"); print(f"  Wind Leistung: {opt_wind_mw:.2f} MW")
    print(f"  Batterie Energie: {opt_batt_mwh:.2f} MWh"); print(f"  Batterie Leistung: {opt_batt_mw:.2f} MW")
    if opt_wind_mw > 1e-3: print(f"  -> Hinweis Wind: Entspricht ideal {opt_wind_mw / 6.8:.2f} Anlagen á 6.8 MW.") # Beispielrechnung

    # Kosten / Erlöse (nochmal berechnen für Klarheit)
    capex_pv_annual = af_pv_wind * opt_pv_mw * specific_capex_pv_eur_per_mw if opt_pv_mw > 0 else 0
    opex_pv_annual = opt_pv_mw * specific_opex_pv_eur_per_mw_pa if opt_pv_mw > 0 else 0
    capex_wind_annual = af_pv_wind * opt_wind_mw * specific_capex_wind_eur_per_mw if opt_wind_mw > 0 else 0
    opex_wind_annual = opt_wind_mw * specific_opex_wind_eur_per_mw_pa if opt_wind_mw > 0 else 0
    capex_batt_annual = af_battery * (opt_batt_mw * specific_capex_battery_eur_per_mw) if opt_batt_mwh > 0 else 0
    opex_batt_annual = opt_batt_mwh * specific_opex_battery_eur_per_mwh_pa if opt_batt_mwh > 0 else 0

    opt_annualized_capex = capex_pv_annual + capex_wind_annual + capex_batt_annual
    opt_total_annual_opex = opex_pv_annual + opex_wind_annual + opex_batt_annual

    # Netzinteraktion für die *gesamte Periode* (366 Tage) auslesen
    # Sicherstellen, dass die Ausdrücke existieren (könnten 0 sein, wenn z.B. kein Netzbezug stattfindet)
    opt_total_grid_import_cost_period = pulp.value(total_grid_import_cost_period) if isinstance(total_grid_import_cost_period, pulp.LpAffineExpression) else 0
    opt_total_feed_in_revenue_period = pulp.value(total_feed_in_revenue_period) if isinstance(total_feed_in_revenue_period, pulp.LpAffineExpression) else 0

    # Gesamtkosten aus Zielwert (Kontrolle)
    calculated_total_cost = opt_annualized_capex + opt_total_annual_opex + opt_total_grid_import_cost_period - opt_total_feed_in_revenue_period

    print(f"\nKosten und Erlöse (annualisiert bzw. für die {days_in_period}-Tage-Periode):")
    print(f"  Gesamtkosten (Zielwert): {opt_total_cost:,.2f} €")
    print(f"    - Ann. CAPEX: {opt_annualized_capex:,.2f} € (PV: {capex_pv_annual:,.0f}, Wind: {capex_wind_annual:,.0f}, Batt: {capex_batt_annual:,.0f})")
    print(f"    - Ann. OPEX: {opt_total_annual_opex:,.2f} € (PV: {opex_pv_annual:,.0f}, Wind: {opex_wind_annual:,.0f}, Batt: {opex_batt_annual:,.0f})")
    print(f"    - Netzbezugskosten (Periode): {opt_total_grid_import_cost_period:,.2f} €")
    print(f"    - Einspeiseerlöse (Periode): {opt_total_feed_in_revenue_period:,.2f} €")
    print(f"  -> Kontrollsumme: {calculated_total_cost:,.2f} € {'(OK)' if abs(opt_total_cost - calculated_total_cost) < 1 else '(Abweichung!)'}")


    # Zeitreihenwerte und Gesamtwerte für die PERIODE (366 Tage)
    actual_pv_gen_profile = specific_yield_pv_mwh_per_mw * opt_pv_mw; actual_wind_gen_profile = specific_yield_wind_mwh_per_mw * opt_wind_mw
    grid_import_values = np.array([grid_import[t].varValue for t in timesteps]); grid_export_values = np.array([grid_export[t].varValue for t in timesteps])
    curtailment_values = np.array([curtailment[t].varValue for t in timesteps]); battery_charge_values = np.array([battery_charge[t].varValue for t in timesteps])
    battery_discharge_values = np.array([battery_discharge[t].varValue for t in timesteps]); battery_soc_values = np.array([battery_soc[t].varValue for t in soc_timesteps]) # Länge num_timesteps + 1

    total_pv_gen_period = np.sum(actual_pv_gen_profile); total_wind_gen_period = np.sum(actual_wind_gen_profile); total_generation_period = total_pv_gen_period + total_wind_gen_period
    total_grid_import_period = np.sum(grid_import_values); total_grid_export_period = np.sum(grid_export_values); total_curtailment_period = np.sum(curtailment_values)
    total_battery_charge_period = np.sum(battery_charge_values); total_battery_discharge_period = np.sum(battery_discharge_values)

    print(f"\nEnergiebilanz (für Analyseperiode von {num_timesteps} Zeitschritten / {days_in_period} Tagen):")
    print(f"  Gesamtbedarf (Periode): {total_demand_period:,.2f} MWh"); print(f"  Gesamte PV Erzeugung (Periode): {total_pv_gen_period:,.2f} MWh"); print(f"  Gesamte Wind Erzeugung (Periode): {total_wind_gen_period:,.2f} MWh")
    print(f"  Gesamte Erzeugung (PV+Wind, Periode): {total_generation_period:,.2f} MWh"); print(f"  Gesamter Netzbezug (Periode): {total_grid_import_period:,.2f} MWh"); print(f"  Gesamte Netzeinspeisung (Periode): {total_grid_export_period:,.2f} MWh")
    print(f"  Gesamte Abregelung (Periode): {total_curtailment_period:,.2f} MWh"); print(f"  Gesamte Batterieladung (Periode): {total_battery_charge_period:,.2f} MWh"); print(f"  Gesamte Batterieentladung (Periode): {total_battery_discharge_period:,.2f} MWh")

    # Bilanz-Check über die Periode
    total_sources = total_generation_period + total_grid_import_period + total_battery_discharge_period
    total_sinks = total_demand_period + total_grid_export_period + total_curtailment_period + total_battery_charge_period
    # Berücksichtige Batterie-SoC-Änderung (sollte nahe 0 sein wegen zyklischer Bedingung)
    soc_diff = battery_soc_values[-1] - battery_soc_values[0]
    # Korrigierte Bilanz: Quellen = Senken + SoC-Änderung (wenn SoC steigt, ist es eine "Senke")
    # Oder: Quellen - Senken = SoC-Änderung
    balance_diff = total_sources - total_sinks
    print(f"  -> Bilanz-Check: Quellen={total_sources:,.2f} MWh, Senken={total_sinks:,.2f} MWh")
    print(f"     SoC-Änderung (Ende-Anfang): {soc_diff:,.4f} MWh")
    print(f"     Differenz (Quellen-Senken): {balance_diff:,.4f} MWh {'(OK)' if abs(balance_diff - soc_diff) < 1 else '(Abweichung!)'}")


    # --- LCOE Gesamt (bezogen auf Bedarf der Periode) ---
    print("\nLevelized Cost of Energy (LCOE):")
    lcoe_system_eur_per_mwh = 0
    # Verwende die annualisierten Gesamtkosten (CAPEX+OPEX) und teile sie durch den *jährlichen* Bedarf
    # Annahme: Der Bedarf der Periode (366 Tage) entspricht ungefähr dem Jahresbedarf
    annual_demand_approx = total_demand_period * (365.25 / days_in_period) # Skalierung auf Standardjahr
    total_annualized_costs_only = opt_annualized_capex + opt_total_annual_opex

    if annual_demand_approx > 1e-6:
         # LCOE der Erzeugung (nur ann. CAPEX/OPEX der Anlagen / Jährlicher Bedarf)
         lcoe_generation_eur_per_mwh = total_annualized_costs_only / annual_demand_approx
         print(f"  LCOE (nur Erzeugung+Speicher CAPEX/OPEX / Jahresbedarf approx.): {lcoe_generation_eur_per_mwh:.2f} €/MWh")

         # LCOE Gesamtsystem (inkl. Netzinteraktion, bezogen auf Jahresbedarf)
         # Hier ist die Verwendung des Zielwerts problematisch, da er Perioden-Netzkosten enthält.
         # Besser: Annualisierte Kosten + (Perioden-Netzkosten - Perioden-Erlöse) * Skalierungsfaktor
         net_cost_period = opt_total_grid_import_cost_period - opt_total_feed_in_revenue_period
         net_cost_annual_approx = net_cost_period * (365.25 / days_in_period)
         total_system_cost_annual_approx = total_annualized_costs_only + net_cost_annual_approx
         lcoe_system_annual_approx = total_system_cost_annual_approx / annual_demand_approx
         print(f"  LCOE Gesamtsystem (alle ann. Kosten inkl. Netz approx. / Jahresbedarf approx.): {lcoe_system_annual_approx:.2f} €/MWh")
         print(f"  (Vergleich: Netzbezugspreis = {grid_purchase_price_eur_per_mwh:.2f} €/MWh)")

    else: print("  LCOE: nicht berechenbar (Bedarf ist Null).")


    # --- Autarkiegrad etc. (bezogen auf die Periode von 366 Tagen) ---
    self_sufficiency_rate = 0; renewable_coverage_rate = 0
    if total_demand_period > 1e-6:
        # Autarkiegrad = (Bedarf - Netzbezug) / Bedarf
        self_sufficiency_rate = (total_demand_period - total_grid_import_period) / total_demand_period * 100
        # EE-Deckungsrate = (PV-Erzeugung + Wind-Erzeugung) / Bedarf
        renewable_coverage_rate = total_generation_period / total_demand_period * 100
    print(f"\nAutarkiegrad (Periode {days_in_period} Tage): {self_sufficiency_rate:.2f}%"); print(f"Erneuerbare Deckungsrate (Periode {days_in_period} Tage): {renewable_coverage_rate:.2f}%")

    
print("\nSkriptausführung beendet.")
