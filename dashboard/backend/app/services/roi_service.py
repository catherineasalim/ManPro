from __future__ import annotations

from copy import deepcopy

from app.core.roi_defaults import DETECTION_DEFAULTS, RUPIAH_PER_UB, SCENARIOS
from app.schemas.models import ROIRequest, ROIResponse, ROIScenario


def calculate(costs: dict[str, float]) -> dict[str, float]:
    p = {**costs, **DETECTION_DEFAULTS}
    failures = p["kegagalan_per_unit_tahun"]
    reactive_per_failure = p["downtime_jam_per_kegagalan"] * p["biaya_downtime_per_jam"] + p["biaya_perbaikan_darurat"]
    reactive = failures * reactive_per_failure
    preventive_failures = failures * p["kegagalan_lolos_preventif"]
    preventive = 12 / p["interval_penggantian_bulan"] * p["biaya_penggantian_preventif"] + preventive_failures * reactive_per_failure
    true_positives = failures * p["official_recall"]
    false_negatives = failures - true_positives
    false_positives = p["false_red_alarms_per_week"] * 52
    predictive = (
        true_positives * p["biaya_perbaikan_terencana"]
        + false_negatives * reactive_per_failure
        + false_positives * p["biaya_inspeksi"]
        + p["biaya_sistem"]
    )
    return {
        "reactive": reactive,
        "preventive": preventive,
        "predictive": predictive,
        "savings_reactive": reactive - predictive,
        "savings_preventive": preventive - predictive,
        "roi_reactive": (reactive - predictive) / p["biaya_sistem"] * 100 if p["biaya_sistem"] else 0,
        "roi_preventive": (preventive - predictive) / p["biaya_sistem"] * 100 if p["biaya_sistem"] else 0,
    }


def _scenario(name: str, costs: dict[str, float]) -> ROIScenario:
    result = calculate(costs)
    return ROIScenario(
        name=name,
        costs=costs,
        annual_costs={"Reaktif": result["reactive"], "Preventif": result["preventive"], "Prediktif": result["predictive"]},
        savings_vs_reactive=result["savings_reactive"],
        savings_vs_preventive=result["savings_preventive"],
        roi_vs_reactive_percent=result["roi_reactive"],
        roi_vs_preventive_percent=result["roi_preventive"],
    )


def calculate_roi(request: ROIRequest) -> ROIResponse:
    scenarios = deepcopy(SCENARIOS)
    selected_costs = scenarios[request.scenario]
    if request.costs:
        unknown = set(request.costs) - set(selected_costs)
        if unknown:
            raise ValueError(f"Parameter biaya tidak dikenal: {', '.join(sorted(unknown))}")
        for key, value in request.costs.items():
            if value < 0:
                raise ValueError(f"Nilai {key} tidak boleh negatif.")
            if key == "interval_penggantian_bulan" and value <= 0:
                raise ValueError("Interval penggantian harus lebih dari nol.")
            if key == "kegagalan_lolos_preventif" and value > 1:
                raise ValueError("Kegagalan lolos preventif harus di antara 0 dan 1.")
            scenarios[request.scenario][key] = value
    selected = _scenario(request.scenario, scenarios[request.scenario])
    all_scenarios = [_scenario(name, costs) for name, costs in scenarios.items()]

    sensitivity = []
    for key, value in scenarios[request.scenario].items():
        if value == 0:
            continue
        low_costs, high_costs = dict(scenarios[request.scenario]), dict(scenarios[request.scenario])
        low_costs[key], high_costs[key] = value * 0.7, value * 1.3
        low, high = calculate(low_costs)["roi_reactive"], calculate(high_costs)["roi_reactive"]
        sensitivity.append({"parameter": key, "nilai": value, "roi_minus_30": low, "roi_plus_30": high, "rentang": abs(high - low)})
    sensitivity.sort(key=lambda item: item["rentang"], reverse=True)

    base = dict(scenarios[request.scenario])
    break_even = []
    for key in ("biaya_perbaikan_darurat", "biaya_inspeksi", "biaya_sistem", "kegagalan_per_unit_tahun"):
        original = base[key]
        if key == "biaya_sistem":
            baseline = calculate(base)
            threshold = baseline["reactive"] - (baseline["predictive"] - original)
            break_even.append({"parameter": key, "nilai_sekarang": original, "titik_impas": round(threshold, 3) if threshold > 0 else None})
            continue
        lo, hi = 0.0, max(original * 50, 1.0)
        def roi_at(value: float) -> float:
            candidate = dict(base)
            candidate[key] = value
            return calculate(candidate)["roi_reactive"]
        a, b = roi_at(lo), roi_at(hi)
        value = None
        if a == 0:
            value = 0.0
        elif a * b < 0:
            rising = b > a
            for _ in range(60):
                mid = (lo + hi) / 2
                if (roi_at(mid) < 0) == rising:
                    lo = mid
                else:
                    hi = mid
            value = round((lo + hi) / 2, 3)
        break_even.append({"parameter": key, "nilai_sekarang": original, "titik_impas": value})

    return ROIResponse(
        detection_basis=DETECTION_DEFAULTS,
        rupiah_per_ub=RUPIAH_PER_UB,
        selected=selected,
        scenarios=all_scenarios,
        sensitivity=sensitivity,
        break_even=break_even,
    )
