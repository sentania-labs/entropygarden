"""
Hidden pressure accumulation for a single ring per tick.

All functions are pure: (current_pressures, population, config) -> HiddenPressures.
"""

from __future__ import annotations

from sim.state import HiddenPressures, Occupation, Person, SimConfig, Trait


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def accumulate_pressures(
    pressures: HiddenPressures,
    population: list[Person],
    cfg: SimConfig,
) -> HiddenPressures:
    """Return updated hidden pressures after one tick."""
    n = max(len(population), 1)  # avoid division by zero

    engineers = [p for p in population if p.occupation == Occupation.ENGINEER]
    farmers = [p for p in population if p.occupation == Occupation.FARMER]
    life_support = [p for p in population if p.occupation == Occupation.LIFE_SUPPORT]
    admins = [p for p in population if p.occupation == Occupation.ADMINISTRATOR]

    # Worker fractions — reductions are fraction-based so they scale with ring size
    eng_fraction = len(engineers) / n
    farmer_fraction = len(farmers) / n
    life_support_fraction = len(life_support) / n
    admin_fraction = len(admins) / n

    # SKILLED engineers count 25% more
    skilled_eng_bonus = sum(
        cfg.trait_skilled_output_mult - 1.0
        for e in engineers
        if Trait.SKILLED in e.traits
    ) / n

    # --- Maintenance Debt ---
    # Engineers counteract up to 85% of the base rate at full staffing (~18% of ring)
    eng_reduction = (eng_fraction + skilled_eng_bonus) * cfg.maintenance_debt_rate * 4.5
    new_debt = pressures.maintenance_debt + cfg.maintenance_debt_rate - eng_reduction
    new_debt = _clamp(new_debt)

    # --- Ecological Drift ---
    # Farmers + life_support slow drift; even at full staffing, drift creeps slightly
    eco_reduction = (
        farmer_fraction * cfg.ecological_drift_rate * 2.5
        + life_support_fraction * cfg.ecological_drift_rate * 1.5
    )
    new_drift = pressures.ecological_drift + cfg.ecological_drift_rate - eco_reduction
    new_drift = _clamp(new_drift)

    # --- Social Tension ---
    # Rises when morale is below 0.5; REBELLIOUS people amplify; admins dampen
    mean_morale = sum(p.morale for p in population) / n
    morale_pressure = max(0.0, 0.5 - mean_morale) * cfg.social_tension_rate * 10.0

    # REBELLIOUS individuals with low morale add extra tension (fraction-based)
    rebel_fraction = sum(
        1.0 for p in population
        if Trait.REBELLIOUS in p.traits and p.morale < cfg.trait_rebellious_threshold
    ) / n
    rebel_pressure = rebel_fraction * cfg.social_tension_rate * cfg.trait_rebellious_tension_mult * 5.0

    admin_reduction = admin_fraction * cfg.social_tension_rate * 3.0
    new_tension = pressures.social_tension + morale_pressure + rebel_pressure - admin_reduction
    new_tension = _clamp(new_tension)

    return HiddenPressures(
        maintenance_debt=new_debt,
        ecological_drift=new_drift,
        social_tension=new_tension,
    )
