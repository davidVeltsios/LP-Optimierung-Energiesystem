
import pulp
import numpy as np
import pandas as pd
import datetime 
import matplotlib.pyplot as plt # Für Diagramme hinzugefügt
import os # Für Pfadausgabe der Excel-Datei
import math 

# --- 1. Eingabedaten und Annahmen ---

print("--- Initialisiere Modellparameter ---")

# Zeitliche Auflösung
time_resolution_hours = 0.25 # 15 Minuten
hours_in_year = 8760
num_timesteps = int(hours_in_year / time_resolution_hours)
print(f"Zeitschritte pro Jahr: {num_timesteps} (Auflösung: {time_resolution_hours*60:.0f} min)")

# Konstantes Lastprofil
demand_per_hour_kwh = 3629
demand_per_timestep_kwh = demand_per_hour_kwh * time_resolution_hours
demand_per_timestep_mwh = demand_per_timestep_kwh / 1000
demand_profile_mwh = np.full(num_timesteps, demand_per_timestep_mwh)
total_demand_mwh = np.sum(demand_profile_mwh)
print(f"Jährlicher Gesamtbedarf: {total_demand_mwh:,.2f} MWh (konstant {demand_per_timestep_mwh:.4f} MWh pro Zeitschritt)")

# Monatliche Erträge (MWh) - Relative Verteilung
monthly_yield_pv_mwh_relative = { 1: 534, 2: 638, 3: 1404, 4: 1567, 5: 2136, 6: 1994, 7: 1954, 8: 2072, 9: 1683, 10: 1528, 11: 638, 12: 425 }
monthly_yield_wind_mwh_relative = { 1: 2107, 2: 1914, 3: 1345, 4: 1310, 5: 877, 6: 820, 7: 820, 8: 751, 9: 1230, 10: 1207, 11: 1424, 12: 1846 }

# Spezifische Jahreserträge
target_annual_specific_yield_pv_mwh_per_mw = 1280
target_annual_specific_yield_wind_mwh_per_mw = 2302
print(f"Ziel-spez. Jahresertrag PV: {target_annual_specific_yield_pv_mwh_per_mw} MWh/MWp")
print(f"Ziel-spez. Jahresertrag Wind: {target_annual_specific_yield_wind_mwh_per_mw} MWh/MW")

# Kosten PV & Wind
specific_capex_pv_eur_per_mw = 800 * 1000
specific_opex_pv_eur_per_mw_pa = 13.3 * 1000
specific_capex_wind_eur_per_mw = 1600 * 1000
specific_opex_wind_eur_per_mw_pa = 32 * 1000

# Kosten Batterie (Annahmen)
specific_capex_battery_eur_per_mw  = 500 * 1000
specific_opex_battery_eur_per_mwh_pa = 6.65 * 1000
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

# Effizienz und Kehrwert berechnen
try:
    if not (0 <= battery_efficiency <= 1): raise ValueError("Batteriewirkungsgrad muss zwischen 0 und 1 liegen.")
    charge_discharge_eff_sqrt = math.sqrt(battery_efficiency)
    if charge_discharge_eff_sqrt > 1e-9: charge_discharge_eff_sqrt_inv = 1.0 / charge_discharge_eff_sqrt
    elif battery_efficiency == 0: print("WARNUNG: Batteriewirkungsgrad ist 0."); charge_discharge_eff_sqrt_inv = 1e12
    else: print("WARNUNG: Batteriewirkungsgrad nahe Null!"); charge_discharge_eff_sqrt_inv = 1.0 / 1e-9
except ValueError as e:
    print(f"WARNUNG: Ungültiger Batteriewirkungsgrad ({battery_efficiency}). Verwende 100%. Fehler: {e}")
    charge_discharge_eff_sqrt = 1.0; charge_discharge_eff_sqrt_inv = 1.0
print(f"Annahme Batterie Wirkungsgrad (round-trip): {battery_efficiency:.1%}")
print(f"Annahme Min. Ladezustand (SoC): {battery_soc_min_percent:.1%}")

# Netzinteraktion
grid_purchase_price_eur_per_mwh = 169.9
feed_in_tariff_eur_per_mwh = 50
negative_price_hours = 459
print(f"Netzbezugspreis: {grid_purchase_price_eur_per_mwh:.2f} €/MWh")
print(f"Einspeisevergütung: {feed_in_tariff_eur_per_mwh:.2f} €/MWh")
print(f"Stunden mit neg. Preisen (Vergütung=0): {negative_price_hours} h")

# --- 2. Zeitreihen generieren ---
print("\n--- Generiere Erzeugungsprofile ---")
days_in_month = { 1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31 }
# Wind Profil
total_relative_yield_wind = sum(monthly_yield_wind_mwh_relative.values())
specific_yield_wind_mwh_per_mw = np.zeros(num_timesteps)
current_timestep = 0; spec_yield_wind_per_ts = 0
for month in range(1, 13):
    num_days = days_in_month[month]; timesteps_in_month = int(num_days * 24 / time_resolution_hours)
    monthly_fraction_wind = monthly_yield_wind_mwh_relative[month] / total_relative_yield_wind if total_relative_yield_wind > 0 else 0
    absolute_yield_wind_per_mw_month = monthly_fraction_wind * target_annual_specific_yield_wind_mwh_per_mw
    spec_yield_wind_per_ts = absolute_yield_wind_per_mw_month / timesteps_in_month if timesteps_in_month > 0 else 0
    end_timestep = min(current_timestep + timesteps_in_month, num_timesteps)
    specific_yield_wind_mwh_per_mw[current_timestep:end_timestep] = spec_yield_wind_per_ts
    current_timestep = end_timestep
specific_yield_wind_mwh_per_mw[current_timestep:] = spec_yield_wind_per_ts
# PV Profil
total_relative_yield_pv = sum(monthly_yield_pv_mwh_relative.values())
initial_specific_yield_pv_mwh_per_mw = np.zeros(num_timesteps)
current_timestep = 0; spec_yield_pv_per_ts = 0
for month in range(1, 13):
    num_days = days_in_month[month]; timesteps_in_month = int(num_days * 24 / time_resolution_hours)
    monthly_fraction_pv = monthly_yield_pv_mwh_relative[month] / total_relative_yield_pv if total_relative_yield_pv > 0 else 0
    absolute_yield_pv_per_mw_month = monthly_fraction_pv * target_annual_specific_yield_pv_mwh_per_mw
    spec_yield_pv_per_ts = absolute_yield_pv_per_mw_month / timesteps_in_month if timesteps_in_month > 0 else 0
    end_timestep = min(current_timestep + timesteps_in_month, num_timesteps)
    initial_specific_yield_pv_mwh_per_mw[current_timestep:end_timestep] = spec_yield_pv_per_ts
    current_timestep = end_timestep
initial_specific_yield_pv_mwh_per_mw[current_timestep:] = spec_yield_pv_per_ts
intervals_per_day = int(24 / time_resolution_hours)
start_day_index = int(6 / time_resolution_hours); end_day_index = int(20 / time_resolution_hours)
daytime_intervals = list(range(start_day_index, end_day_index))
is_daytime = np.array([t % intervals_per_day in daytime_intervals for t in range(num_timesteps)])
total_daytime_yield_initial = np.sum(initial_specific_yield_pv_mwh_per_mw[is_daytime])
scaling_factor = 1.0
if total_daytime_yield_initial > 1e-6: scaling_factor = target_annual_specific_yield_pv_mwh_per_mw / total_daytime_yield_initial
specific_yield_pv_mwh_per_mw = initial_specific_yield_pv_mwh_per_mw * is_daytime * scaling_factor
print(f"Kontrolle Jahresertrag PV pro MW: {np.sum(specific_yield_pv_mwh_per_mw):.2f} MWh")
print(f"Kontrolle Jahresertrag Wind pro MW: {np.sum(specific_yield_wind_mwh_per_mw):.2f} MWh")
# Einspeisevergütungsprofil
negative_price_share = negative_price_hours / hours_in_year
feed_in_tariff_profile_eur_per_mwh = np.full(num_timesteps, feed_in_tariff_eur_per_mwh)
num_negative_timesteps = int(negative_price_share * num_timesteps)
random_indices = np.random.choice(num_timesteps, num_negative_timesteps, replace=False)
feed_in_tariff_profile_eur_per_mwh[random_indices] = 0
print(f"Einspeiseprofil: {num_negative_timesteps} Zeitschritte mit 0 € Vergütung.")

# --- 3. Annuitätenfaktor berechnen ---
def annuity_factor(rate, years):
    if years <= 0: return 0;
    if rate == 0: return 1 / years
    if rate < 1e-9: rate = 1e-9
    q = 1 + rate
    try: qn = q**years; denominator = qn - 1
    except OverflowError: print(f"ERROR: Overflow annuity factor (r={rate}, n={years})."); return 0
    except Exception as e: print(f"ERROR: annuity factor: {e}"); return 0
    if abs(denominator) < 1e-9: return 1 / years
    return (rate * qn) / denominator
af_pv_wind = annuity_factor(discount_rate, lifetime_pv_wind_years)
af_battery = annuity_factor(discount_rate, lifetime_battery_years)
print(f"Annuitätsfaktor PV/Wind (r={discount_rate:.1%}, n={lifetime_pv_wind_years}): {af_pv_wind:.4f}")
print(f"Annuitätsfaktor Batterie (r={discount_rate:.1%}, n={lifetime_battery_years}): {af_battery:.4f}")

# --- 4. Optimierungsproblem definieren (Hauptmodell) ---
print("\n--- Definiere Optimierungsmodell ---")
model = pulp.LpProblem("Renewable_Energy_System_Optimization_with_Battery", pulp.LpMinimize)
# Variablen
pv_capacity_mw = pulp.LpVariable("PV_Capacity_MWp", lowBound=0)
wind_capacity_mw = pulp.LpVariable("Wind_Capacity_MW", lowBound=0)
battery_capacity_mwh = pulp.LpVariable("Battery_Capacity_MWh", lowBound=0)
battery_power_mw = pulp.LpVariable("Battery_Power_MW", lowBound=0)
timesteps = range(num_timesteps)
soc_timesteps = range(num_timesteps + 1)
grid_import = pulp.LpVariable.dicts("Grid_Import", timesteps, lowBound=0)
grid_export = pulp.LpVariable.dicts("Grid_Export", timesteps, lowBound=0)
curtailment = pulp.LpVariable.dicts("Curtailment", timesteps, lowBound=0)
battery_soc = pulp.LpVariable.dicts("Battery_SoC", soc_timesteps, lowBound=0)
battery_charge = pulp.LpVariable.dicts("Battery_Charge", timesteps, lowBound=0)
battery_discharge = pulp.LpVariable.dicts("Battery_Discharge", timesteps, lowBound=0)
print("Variablen definiert.")
# Zielfunktion
annualized_capex_pv_wind = af_pv_wind * (pv_capacity_mw * specific_capex_pv_eur_per_mw + wind_capacity_mw * specific_capex_wind_eur_per_mw)
annualized_capex_battery = af_battery * (  battery_power_mw * specific_capex_battery_eur_per_mw)
total_annualized_capex = annualized_capex_pv_wind + annualized_capex_battery
total_opex_pv_wind = pv_capacity_mw * specific_opex_pv_eur_per_mw_pa + wind_capacity_mw * specific_opex_wind_eur_per_mw_pa
total_opex_battery = battery_capacity_mwh * specific_opex_battery_eur_per_mwh_pa
total_annual_opex = total_opex_pv_wind + total_opex_battery
total_grid_import_cost = pulp.lpSum(grid_import[t] * grid_purchase_price_eur_per_mwh for t in timesteps)
total_feed_in_revenue = pulp.lpSum(grid_export[t] * feed_in_tariff_profile_eur_per_mwh[t] for t in timesteps)
model += (total_annualized_capex + total_annual_opex + total_grid_import_cost - total_feed_in_revenue), "Total_Annualized_System_Cost_with_Battery"
print("Zielfunktion definiert.")
# Nebenbedingungen
print("Definiere Nebenbedingungen...")
# 1. Energiebilanz
for t in timesteps:
    available_pv_gen = specific_yield_pv_mwh_per_mw[t] * pv_capacity_mw
    available_wind_gen = specific_yield_wind_mwh_per_mw[t] * wind_capacity_mw
    model += available_pv_gen + available_wind_gen + grid_import[t] + battery_discharge[t] == demand_profile_mwh[t] + grid_export[t] + curtailment[t] + battery_charge[t], f"Energy_Balance_{t}"
# 2. Batterie-Nebenbedingungen
for t in timesteps:
    model += battery_soc[t+1] == battery_soc[t] + battery_charge[t] * charge_discharge_eff_sqrt - battery_discharge[t] * charge_discharge_eff_sqrt_inv, f"Battery_SoC_Update_{t}"
    model += battery_charge[t] <= battery_power_mw * time_resolution_hours, f"Battery_Charge_Power_Limit_{t}"
    model += battery_discharge[t] <= battery_power_mw * time_resolution_hours, f"Battery_Discharge_Power_Limit_{t}"
    model += battery_soc[t] >= battery_soc_min_percent * battery_capacity_mwh, f"Battery_SoC_Min_Limit_{t}"
    model += battery_soc[t] <= battery_capacity_mwh, f"Battery_SoC_Max_Limit_{t}"
model += battery_soc[num_timesteps] >= battery_soc_min_percent * battery_capacity_mwh, f"Battery_SoC_Min_Limit_{num_timesteps}"
model += battery_soc[num_timesteps] <= battery_capacity_mwh, f"Battery_SoC_Max_Limit_{num_timesteps}"
# 3. Zyklische Bedingung
model += battery_soc[num_timesteps] == battery_soc[0], "Battery_Cyclic_SoC"
print("Nebenbedingungen definiert.")

# --- 5. Optimierung lösen ---
print("\n--- Starte Optimierung (kann einige Zeit dauern) ---")
start_time = datetime.datetime.now()
solver = pulp.PULP_CBC_CMD(msg=True)
model.solve(solver)
end_time = datetime.datetime.now()
print(f"Optimierung abgeschlossen. Dauer: {end_time - start_time}")

# --- 6. Ergebnisse ausgeben ---
print("\n--- Optimierungsergebnisse ---")
print(f"Status: {pulp.LpStatus[model.status]}")

# Globale Variablen für optimale Werte definieren (für spätere Verwendung in Plot-Funktion)
opt_pv_mw = 0
opt_wind_mw = 0
opt_batt_mwh = 0
opt_batt_mw = 0
opt_total_cost = np.inf # Standardwert falls nicht optimal

if pulp.LpStatus[model.status] == 'Optimal':
    opt_pv_mw = pv_capacity_mw.varValue
    opt_wind_mw = wind_capacity_mw.varValue
    opt_batt_mwh = battery_capacity_mwh.varValue
    opt_batt_mw = battery_power_mw.varValue
    opt_total_cost = pulp.value(model.objective)

    print(f"\nOptimale Kapazitäten:")
    print(f"  PV Leistung: {opt_pv_mw:.2f} MWp")
    print(f"  Wind Leistung: {opt_wind_mw:.2f} MW")
    print(f"  Batterie Energie: {opt_batt_mwh:.2f} MWh")
    print(f"  Batterie Leistung: {opt_batt_mw:.2f} MW")

    wind_turbine_size_mw = 6.8
    if opt_wind_mw > 1e-3: print(f"  -> Hinweis Wind: Entspricht ideal {opt_wind_mw / wind_turbine_size_mw:.2f} Anlagen á {wind_turbine_size_mw} MW.")

    # Kosten / Erlöse
    capex_pv_annual = af_pv_wind * opt_pv_mw * specific_capex_pv_eur_per_mw if opt_pv_mw > 0 else 0
    opex_pv_annual = opt_pv_mw * specific_opex_pv_eur_per_mw_pa if opt_pv_mw > 0 else 0
    capex_wind_annual = af_pv_wind * opt_wind_mw * specific_capex_wind_eur_per_mw if opt_wind_mw > 0 else 0
    opex_wind_annual = opt_wind_mw * specific_opex_wind_eur_per_mw_pa if opt_wind_mw > 0 else 0
    capex_batt_annual = af_battery * (opt_batt_mw * specific_capex_battery_eur_per_mw) if opt_batt_mwh > 0 else 0
    opex_batt_annual = opt_batt_mwh * specific_opex_battery_eur_per_mwh_pa if opt_batt_mwh > 0 else 0
    opt_annualized_capex = capex_pv_annual + capex_wind_annual + capex_batt_annual
    opt_total_opex = opex_pv_annual + opex_wind_annual + opex_batt_annual
    opt_total_grid_import_cost = pulp.value(total_grid_import_cost) if isinstance(total_grid_import_cost, pulp.LpAffineExpression) else 0
    opt_total_feed_in_revenue = pulp.value(total_feed_in_revenue) if isinstance(total_feed_in_revenue, pulp.LpAffineExpression) else 0

    print(f"\nJährliche Kosten und Erlöse:")
    print(f"  Annualisierte Gesamtkosten (Zielwert): {opt_total_cost:,.2f} €")
    print(f"    - Ann. CAPEX: {opt_annualized_capex:,.2f} € (PV: {capex_pv_annual:,.0f}, Wind: {capex_wind_annual:,.0f}, Batt: {capex_batt_annual:,.0f})")
    print(f"    - Jhrl. OPEX: {opt_total_opex:,.2f} € (PV: {opex_pv_annual:,.0f}, Wind: {opex_wind_annual:,.0f}, Batt: {opex_batt_annual:,.0f})")
    print(f"    - Jhrl. Netzbezugskosten: {opt_total_grid_import_cost:,.2f} €")
    print(f"    - Jhrl. Einspeiseerlöse: {opt_total_feed_in_revenue:,.2f} €")
    control_sum = opt_annualized_capex + opt_total_opex + opt_total_grid_import_cost - opt_total_feed_in_revenue
    print(f"    -> Kontrollsumme: {control_sum:,.2f} € {'(OK)' if abs(control_sum - opt_total_cost) < 1 else '(Abweichung!)'}")

    # Zeitreihenwerte
    actual_pv_gen_profile = specific_yield_pv_mwh_per_mw * opt_pv_mw
    actual_wind_gen_profile = specific_yield_wind_mwh_per_mw * opt_wind_mw
    grid_import_values = [grid_import[t].varValue for t in timesteps]
    grid_export_values = [grid_export[t].varValue for t in timesteps]
    curtailment_values = [curtailment[t].varValue for t in timesteps]
    battery_charge_values = [battery_charge[t].varValue for t in timesteps]
    battery_discharge_values = [battery_discharge[t].varValue for t in timesteps]
    battery_soc_values = [battery_soc[t].varValue for t in soc_timesteps]

    # Jahreswerte
    total_pv_gen_mwh = np.sum(actual_pv_gen_profile); total_wind_gen_mwh = np.sum(actual_wind_gen_profile)
    total_generation_mwh = total_pv_gen_mwh + total_wind_gen_mwh
    total_grid_import_mwh = sum(grid_import_values); total_grid_export_mwh = sum(grid_export_values)
    total_curtailment_mwh = sum(curtailment_values); total_battery_charge_mwh = sum(battery_charge_values)
    total_battery_discharge_mwh = sum(battery_discharge_values)

    print(f"\nEnergiejahresbilanz:")
    print(f"  Gesamtjahresbedarf: {total_demand_mwh:,.2f} MWh")
    print(f"  Gesamte PV Erzeugung: {total_pv_gen_mwh:,.2f} MWh")
    print(f"  Gesamte Wind Erzeugung: {total_wind_gen_mwh:,.2f} MWh")
    print(f"  Gesamte Erzeugung (PV+Wind): {total_generation_mwh:,.2f} MWh")
    print(f"  Gesamter Netzbezug: {total_grid_import_mwh:,.2f} MWh")
    print(f"  Gesamte Netzeinspeisung: {total_grid_export_mwh:,.2f} MWh")
    print(f"  Gesamte Abregelung: {total_curtailment_mwh:,.2f} MWh")
    print(f"  Gesamte Batterieladung: {total_battery_charge_mwh:,.2f} MWh")
    print(f"  Gesamte Batterieentladung: {total_battery_discharge_mwh:,.2f} MWh")
    total_sources = total_generation_mwh + total_grid_import_mwh + total_battery_discharge_mwh
    total_sinks = total_demand_mwh + total_grid_export_mwh + total_curtailment_mwh + total_battery_charge_mwh
    print(f"  -> Bilanz-Check: Quellen={total_sources:,.2f} MWh, Senken={total_sinks:,.2f} MWh {'(OK)' if abs(total_sources - total_sinks) < 1 else '(Abweichung!)'}")

    # Kennzahlen
    if total_demand_mwh > 1e-6:
        lcoe_eur_per_mwh = opt_total_cost / total_demand_mwh
        lcoe_ct_per_kwh = lcoe_eur_per_mwh / 10
        print(f"\nLCOE (auf Bedarf bezogen): {lcoe_eur_per_mwh:.2f} €/MWh ({lcoe_ct_per_kwh:.2f} ct/kWh)")
        print(f"  Vergleich Netzbezugspreis: {grid_purchase_price_eur_per_mwh:.2f} €/MWh")
    else: print("\nLCOE nicht berechenbar.")
    self_sufficiency_rate = 0; renewable_coverage_rate = 0
    if total_demand_mwh > 1e-6:
        self_sufficiency_rate = (total_demand_mwh - total_grid_import_mwh) / total_demand_mwh * 100
        renewable_coverage_rate = total_generation_mwh / total_demand_mwh * 100
    print(f"\nAutarkiegrad: {self_sufficiency_rate:.2f}%")
    print(f"Erneuerbare Deckungsrate: {renewable_coverage_rate:.2f}%")

    # Diagramm: Lastprofil und EE-Erzeugung
    print("\nErstelle Diagramm: Lastprofil und EE-Erzeugung...")
    try:
        start_date_plot = datetime.datetime(2023, 1, 1)
        time_index_plot = pd.date_range(start_date_plot, periods=num_timesteps, freq=pd.Timedelta(hours=time_resolution_hours))
        plt.figure(figsize=(15, 7))
        plt.plot(time_index_plot, demand_profile_mwh, label='Bedarf', color='black', linewidth=1.5)
        plt.plot(time_index_plot, actual_pv_gen_profile, label='PV Erzeugung', color='orange', linewidth=0.8, alpha=0.8)
        plt.plot(time_index_plot, actual_wind_gen_profile, label='Wind Erzeugung', color='deepskyblue', linewidth=0.8, alpha=0.8)
        plt.title('Lastprofil und Erneuerbare Erzeugung über das Beispieljahr')
        plt.xlabel('Datum'); plt.ylabel(f'Energie (MWh pro {time_resolution_hours*60:.0f} min)')
        plt.grid(True, linestyle=':', alpha=0.7); plt.legend(loc='upper left')
        plt.ylim(bottom=0); plt.tight_layout()
        plot_filename = "lastprofil_erzeugung_jahr_mit_batterie.png"
        plt.savefig(plot_filename); print(f"Diagramm '{plot_filename}' gespeichert.")
    except Exception as e: print(f"Fehler beim Erstellen des Lastprofil/Erzeugungs-Diagramms: {e}")

    # Excel-Datei
    print("\nErstelle Excel-Datei mit 15-Minuten-Intervall-Daten...")
    try:
        if 'time_index_plot' not in locals():
             start_date_excel = datetime.datetime(2023, 1, 1)
             time_index_excel = pd.date_range(start_date_excel, periods=num_timesteps, freq=pd.Timedelta(hours=time_resolution_hours))
        else: time_index_excel = time_index_plot
        self_consumption_values = demand_profile_mwh - np.array(grid_import_values)
        self_consumption_values = np.maximum(0, self_consumption_values)
        excel_data = {
            'Timestamp': time_index_excel, 'Bedarf (MWh)': demand_profile_mwh,
            'PV Erzeugung (MWh)': actual_pv_gen_profile, 'Wind Erzeugung (MWh)': actual_wind_gen_profile,
            'Netzbezug (MWh)': grid_import_values, 'Netzeinspeisung (MWh)': grid_export_values,
            'Abregelung (MWh)': curtailment_values, 'Batterie Ladung (MWh)': battery_charge_values,
            'Batterie Entladung (MWh)': battery_discharge_values, 'Batterie SoC (MWh)': battery_soc_values[:-1],
            'Eigenverbrauch (MWh)': self_consumption_values
        }
        df_export = pd.DataFrame(excel_data)
        excel_filename = "energiebilanz_15min_mit_batterie.xlsx"
        df_export.to_excel(excel_filename, index=False, engine='openpyxl')
        print(f"Excel-Datei '{excel_filename}' erfolgreich erstellt.")
        try: print(f"Pfad: {os.path.abspath(excel_filename)}")
        except Exception: print("Konnte absoluten Pfad nicht bestimmen.")
    except ImportError: print("\nFEHLER: 'openpyxl' fehlt. Installieren mit: pip install openpyxl")
    except Exception as e: print(f"Fehler beim Erstellen der Excel-Datei: {e}")


    # --- 7. Visualisierung der Kostenlandschaft (PV vs Wind, bei optimaler Batterie) ---
    # ACHTUNG: Sehr rechenintensiv!
    print("\n--- Erstelle Visualisierung der Kostenlandschaft (PV/Wind bei opt. Batterie) ---")
    print(f"Hinweis: Verwendet feste Batteriegröße (MWh={opt_batt_mwh:.1f}, MW={opt_batt_mw:.1f}) aus Hauptoptimierung.")
    print("Dies kann SEHR lange dauern, da viele Betriebsoptimierungen durchgeführt werden...")

    # Wichtige Parameter aus Hauptoptimierung für die Funktion unten
    fixed_optimal_batt_mwh = opt_batt_mwh
    fixed_optimal_batt_mw = opt_batt_mw

    # Annuitisierte Fixkosten der optimalen Batterie (werden in der Funktion addiert)
    # Nur berechnen, wenn Batterie > 0
    if fixed_optimal_batt_mwh > 1e-3:
        fixed_annual_capex_batt_opt = af_battery * (fixed_optimal_batt_mw * specific_capex_battery_eur_per_mw)
        fixed_annual_opex_batt_opt = fixed_optimal_batt_mwh * specific_opex_battery_eur_per_mwh_pa
    else:
        fixed_annual_capex_batt_opt = 0
        fixed_annual_opex_batt_opt = 0

    def calculate_total_cost_for_fixed_pv_wind_optimal_battery(fixed_pv_mw, fixed_wind_mw):
        """ Berechnet min. Gesamtkosten für feste PV/Wind-Caps und opt. Batt-Größe. Optimiert nur den Betrieb. """

        # Fall 1: Keine signifikante Batterie in der Hauptoptimierung gefunden -> Berechne Kosten ohne Batteriebetrieb
        if fixed_optimal_batt_mwh < 1e-3 or fixed_optimal_batt_mw < 1e-3:
             op_model_nb = pulp.LpProblem(f"OpOptNoBatt_{fixed_pv_mw:.0f}PV_{fixed_wind_mw:.0f}W", pulp.LpMinimize)
             grid_import_op_nb = pulp.LpVariable.dicts("GI_NB", timesteps, lowBound=0)
             grid_export_op_nb = pulp.LpVariable.dicts("GE_NB", timesteps, lowBound=0)
             curt_op_nb = pulp.LpVariable.dicts("Curt_NB", timesteps, lowBound=0)
             pv_gen_f = specific_yield_pv_mwh_per_mw * fixed_pv_mw
             wind_gen_f = specific_yield_wind_mwh_per_mw * fixed_wind_mw
             capex_pv_wind = af_pv_wind * (fixed_pv_mw * specific_capex_pv_eur_per_mw + fixed_wind_mw * specific_capex_wind_eur_per_mw)
             opex_pv_wind = fixed_pv_mw * specific_opex_pv_eur_per_mw_pa + fixed_wind_mw * specific_opex_wind_eur_per_mw_pa
             grid_imp_cost = pulp.lpSum(grid_import_op_nb[t] * grid_purchase_price_eur_per_mwh for t in timesteps)
             feed_in_rev = pulp.lpSum(grid_export_op_nb[t] * feed_in_tariff_profile_eur_per_mwh[t] for t in timesteps)
             op_model_nb += capex_pv_wind + opex_pv_wind + grid_imp_cost - feed_in_rev, "CostNoBatt"
             for t in timesteps: op_model_nb += pv_gen_f[t] + wind_gen_f[t] + grid_import_op_nb[t] == demand_profile_mwh[t] + grid_export_op_nb[t] + curt_op_nb[t], f"BalNB_{t}"
             op_model_nb.solve(solver=pulp.PULP_CBC_CMD(msg=False))
             if pulp.LpStatus[op_model_nb.status] == 'Optimal': return pulp.value(op_model_nb.objective)
             else: print(f"W: NoBatt-Op failed PV={fixed_pv_mw:.1f} W={fixed_wind_mw:.1f}"); return np.inf

        # Fall 2: Batterie vorhanden -> Betriebsoptimierung mit fester Batteriegröße
        else:
            op_model = pulp.LpProblem(f"OpOptWBatt_{fixed_pv_mw:.0f}PV_{fixed_wind_mw:.0f}W", pulp.LpMinimize)
            # Variablen für Betrieb
            grid_import_op = pulp.LpVariable.dicts("GI_Op", timesteps, lowBound=0)
            grid_export_op = pulp.LpVariable.dicts("GE_Op", timesteps, lowBound=0)
            curtailment_op = pulp.LpVariable.dicts("Curt_Op", timesteps, lowBound=0)
            battery_charge_op = pulp.LpVariable.dicts("BC_Op", timesteps, lowBound=0)
            battery_discharge_op = pulp.LpVariable.dicts("BD_Op", timesteps, lowBound=0)
            battery_soc_op = pulp.LpVariable.dicts("BSOC_Op", soc_timesteps, lowBound=0)
            # Feste Erzeugung
            pv_gen_f = specific_yield_pv_mwh_per_mw * fixed_pv_mw
            wind_gen_f = specific_yield_wind_mwh_per_mw * fixed_wind_mw
            # Fixkosten PV/Wind + Fixkosten der optimalen Batterie
            capex_pv_wind = af_pv_wind * (fixed_pv_mw * specific_capex_pv_eur_per_mw + fixed_wind_mw * specific_capex_wind_eur_per_mw)
            opex_pv_wind = fixed_pv_mw * specific_opex_pv_eur_per_mw_pa + fixed_wind_mw * specific_opex_wind_eur_per_mw_pa
            fixed_costs = capex_pv_wind + opex_pv_wind + fixed_annual_capex_batt_opt + fixed_annual_opex_batt_opt
            # Variable Kosten Netz
            grid_imp_cost = pulp.lpSum(grid_import_op[t] * grid_purchase_price_eur_per_mwh for t in timesteps)
            feed_in_rev = pulp.lpSum(grid_export_op[t] * feed_in_tariff_profile_eur_per_mwh[t] for t in timesteps)
            # Ziel: Fixkosten + variable Kosten
            op_model += fixed_costs + grid_imp_cost - feed_in_rev, "TotalCostOp"
            # Nebenbedingungen Betrieb
            for t in timesteps:
                op_model += pv_gen_f[t] + wind_gen_f[t] + grid_import_op[t] + battery_discharge_op[t] == demand_profile_mwh[t] + grid_export_op[t] + curtailment_op[t] + battery_charge_op[t], f"OpBal_{t}"
                op_model += battery_soc_op[t+1] == battery_soc_op[t] + battery_charge_op[t] * charge_discharge_eff_sqrt - battery_discharge_op[t] * charge_discharge_eff_sqrt_inv, f"OpSoCUp_{t}"
                op_model += battery_charge_op[t] <= fixed_optimal_batt_mw * time_resolution_hours, f"OpBCP_{t}"
                op_model += battery_discharge_op[t] <= fixed_optimal_batt_mw * time_resolution_hours, f"OpBDP_{t}"
                op_model += battery_soc_op[t] >= battery_soc_min_percent * fixed_optimal_batt_mwh, f"OpSoCMin_{t}"
                op_model += battery_soc_op[t] <= fixed_optimal_batt_mwh, f"OpSoCMax_{t}"
            op_model += battery_soc_op[num_timesteps] >= battery_soc_min_percent * fixed_optimal_batt_mwh, f"OpSoCMinN_{num_timesteps}"
            op_model += battery_soc_op[num_timesteps] <= fixed_optimal_batt_mwh, f"OpSoCMaxN_{num_timesteps}"
            op_model += battery_soc_op[num_timesteps] == battery_soc_op[0], "OpSoCCyc"
            # Lösen
            op_model.solve(solver=pulp.PULP_CBC_CMD(msg=False))
            if pulp.LpStatus[op_model.status] == 'Optimal': return pulp.value(op_model.objective)
            else: print(f"W: Batt-Op failed PV={fixed_pv_mw:.1f} W={fixed_wind_mw:.1f} Status={pulp.LpStatus[op_model.status]}"); return np.inf

    # --- Raster für PV/Wind Kapazitäten definieren ---
    pv_steps = 15; wind_steps = 15 # Ggf. reduzieren für schnellere Tests
    max_pv_plot = max(10, opt_pv_mw * 1.5); max_wind_plot = max(10, opt_wind_mw * 1.5)
    if opt_pv_mw < 1: max_pv_plot = max(max_pv_plot, 50)
    if opt_wind_mw < 1: max_wind_plot = max(max_wind_plot, 50)
    pv_range = np.linspace(0, max_pv_plot, pv_steps)
    wind_range = np.linspace(0, max_wind_plot, wind_steps)
    cost_grid = np.full((wind_steps, pv_steps), np.nan)

    # --- Kosten für jede Kombination berechnen ---
    total_combinations = pv_steps * wind_steps; current_combination = 0
    start_time_sens = datetime.datetime.now()
    print(f"Starte Berechnung der Kostenlandschaft ({total_combinations} Punkte)...")
    for i, wind_val in enumerate(wind_range):
        for j, pv_val in enumerate(pv_range):
            current_combination += 1
            # Fortschritt anzeigen (weniger häufig, z.B. alle 5 Punkte)
            if current_combination % 5 == 0 or current_combination == total_combinations:
                 now = datetime.datetime.now()
                 elapsed = now - start_time_sens
                 if current_combination > 0 and elapsed.total_seconds() > 1:
                     est_total_time = elapsed * (total_combinations / current_combination)
                     est_remaining = est_total_time - elapsed
                     print(f"\rBerechne Kostenlandschaft: Punkt {current_combination}/{total_combinations}. Verbleibend ca.: {str(est_remaining).split('.')[0]}", end="")
                 else:
                     print(f"\rBerechne Kostenlandschaft: Punkt {current_combination}/{total_combinations}...", end="")

            cost = calculate_total_cost_for_fixed_pv_wind_optimal_battery(pv_val, wind_val)
            cost_grid[i, j] = cost

    end_time_sens = datetime.datetime.now()
    print(f"\nBerechnung der Kostenlandschaft abgeschlossen. Dauer: {end_time_sens - start_time_sens}")

    # --- Konturdiagramm erstellen ---
    if not np.all(np.isnan(cost_grid)) and np.any(np.isfinite(cost_grid)):
        plt.figure(figsize=(10, 8))
        cost_grid_mio = cost_grid / 1_000_000
        pv_mesh, wind_mesh = np.meshgrid(pv_range, wind_range)
        # Filtern von Inf-Werten für die Plot-Skala
        finite_costs = cost_grid_mio[np.isfinite(cost_grid_mio)]
        levels = np.linspace(np.min(finite_costs), np.min(finite_costs) * 2, 20) if len(finite_costs) > 0 else 20 # Levels anpassen
        # contour = plt.contourf(pv_mesh, wind_mesh, np.nan_to_num(cost_grid_mio, nan=np.inf), levels=levels, cmap='viridis_r', extend='max') # Inf Werte evtl. speziell behandeln
        contour = plt.contourf(pv_mesh, wind_mesh, cost_grid_mio, levels=levels, cmap='viridis_r', extend='max') # Inf Werte werden von contourf oft ignoriert oder speziell behandelt
        plt.colorbar(contour, label='Anualisierte jährliche Gesamtkosten (Mio. €)')
        # Optimum markieren
        plt.scatter(opt_pv_mw, opt_wind_mw, color='red', s=150, edgecolors='black', marker='*', label=f'Optimum ({opt_pv_mw:.1f} MW PV, {opt_wind_mw:.1f} MW Wind)\nKosten: {opt_total_cost/1_000_000:.2f} Mio. €')
        plt.xlabel('Installierte PV-Leistung (MWp)'); plt.ylabel('Installierte Wind-Leistung (MW)')
        plt.title(f'Kostenlandschaft (PV/Wind) bei optimaler Batterie ({opt_batt_mwh:.1f} MWh / {opt_batt_mw:.1f} MW)')
        plt.legend(); plt.grid(True, linestyle=':', alpha=0.6); plt.tight_layout()
        plt.savefig("kostenlandschaft_optimierung_mit_batterie.png")
        print("Diagramm 'kostenlandschaft_optimierung_mit_batterie.png' gespeichert.")
    else:
        print("Kostenlandschaft konnte nicht erstellt werden (keine gültigen Kosten berechnet).")


elif pulp.LpStatus[model.status] != 'Optimal':
    print("Optimierung nicht erfolgreich. Status:", pulp.LpStatus[model.status])
    print("Es werden keine detaillierten Ergebnisse, Diagramme oder Excel-Dateien generiert.")
else:
     print(f"Optimierung endete mit Status '{pulp.LpStatus[model.status]}'.")
     print("Es werden keine detaillierten Ergebnisse, Diagramme oder Excel-Dateien generiert.")

print("\n**WICHTIGER HINWEIS:** Ergebnisse basieren auf skalierten Monatsprofilen. Batterieparameter sind Annahmen.")

# Optional: Zeige alle erstellten Diagramme am Ende gesammelt an
plt.show()
