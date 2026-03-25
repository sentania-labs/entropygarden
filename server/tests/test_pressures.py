"""Tests for hidden pressure accumulation logic."""

import pytest

from sim.state import HiddenPressures, Occupation, Person, SimConfig, Trait


def make_person(
    person_id: str = "p1",
    occupation: Occupation = Occupation.LABORER,
    morale: float = 0.8,
    traits: list[Trait] | None = None,
) -> Person:
    return Person(
        person_id=person_id,
        name="Test",
        age=30.0,
        occupation=occupation,
        health=0.9,
        morale=morale,
        influence=0.1,
        ring_id="ring_1",
        traits=traits or [],
    )


class TestMaintenanceDebt:
    def test_debt_increases_with_no_engineers(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.1, ecological_drift=0.0, social_tension=0.0)
        pop = [make_person(occupation=Occupation.LABORER)]
        new = accumulate_pressures(pressures, pop, cfg)
        assert new.maintenance_debt > pressures.maintenance_debt

    def test_engineers_slow_debt(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.1, ecological_drift=0.0, social_tension=0.0)
        no_engineers = [make_person(f"p{i}", Occupation.LABORER) for i in range(5)]
        with_engineers = [make_person(f"e{i}", Occupation.ENGINEER) for i in range(5)]

        new_no_eng = accumulate_pressures(pressures, no_engineers, cfg)
        new_with_eng = accumulate_pressures(pressures, with_engineers, cfg)
        assert new_with_eng.maintenance_debt < new_no_eng.maintenance_debt

    def test_skilled_engineers_slow_debt_more(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.1, ecological_drift=0.0, social_tension=0.0)
        plain = [make_person("e1", Occupation.ENGINEER)]
        skilled = [make_person("e2", Occupation.ENGINEER, traits=[Trait.SKILLED])]

        new_plain = accumulate_pressures(pressures, plain, cfg)
        new_skilled = accumulate_pressures(pressures, skilled, cfg)
        assert new_skilled.maintenance_debt <= new_plain.maintenance_debt

    def test_debt_capped_at_one(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.9999, ecological_drift=0.0, social_tension=0.0)
        pop = [make_person()]
        new = accumulate_pressures(pressures, pop, cfg)
        assert new.maintenance_debt <= 1.0


class TestEcologicalDrift:
    def test_drift_increases_with_no_farmers(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.0, ecological_drift=0.1, social_tension=0.0)
        pop = [make_person(occupation=Occupation.ENGINEER)]
        new = accumulate_pressures(pressures, pop, cfg)
        assert new.ecological_drift > pressures.ecological_drift

    def test_farmers_slow_drift(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.0, ecological_drift=0.1, social_tension=0.0)
        no_farmers = [make_person(f"p{i}", Occupation.LABORER) for i in range(5)]
        with_farmers = [make_person(f"f{i}", Occupation.FARMER) for i in range(5)]

        new_no = accumulate_pressures(pressures, no_farmers, cfg)
        new_with = accumulate_pressures(pressures, with_farmers, cfg)
        assert new_with.ecological_drift < new_no.ecological_drift


class TestSocialTension:
    def test_tension_rises_with_low_morale(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.0, ecological_drift=0.0, social_tension=0.1)
        low_morale_pop = [make_person(f"p{i}", morale=0.2) for i in range(5)]
        high_morale_pop = [make_person(f"p{i}", morale=0.9) for i in range(5)]

        new_low = accumulate_pressures(pressures, low_morale_pop, cfg)
        new_high = accumulate_pressures(pressures, high_morale_pop, cfg)
        assert new_low.social_tension > new_high.social_tension

    def test_rebellious_low_morale_amplifies_tension(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.0, ecological_drift=0.0, social_tension=0.1)
        normal = make_person("n1", morale=0.2)
        rebellious = make_person("r1", morale=0.2, traits=[Trait.REBELLIOUS])

        new_normal = accumulate_pressures(pressures, [normal], cfg)
        new_rebel = accumulate_pressures(pressures, [rebellious], cfg)
        assert new_rebel.social_tension > new_normal.social_tension

    def test_administrator_dampens_tension(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.0, ecological_drift=0.0, social_tension=0.2)
        no_admin = [make_person(f"p{i}", Occupation.LABORER, morale=0.5) for i in range(5)]
        with_admin = [make_person(f"a{i}", Occupation.ADMINISTRATOR, morale=0.5) for i in range(5)]

        new_no = accumulate_pressures(pressures, no_admin, cfg)
        new_with = accumulate_pressures(pressures, with_admin, cfg)
        assert new_with.social_tension < new_no.social_tension

    def test_tension_capped_at_one(self) -> None:
        from sim.pressures import accumulate_pressures

        cfg = SimConfig()
        pressures = HiddenPressures(maintenance_debt=0.0, ecological_drift=0.0, social_tension=0.9999)
        pop = [make_person(morale=0.1)]
        new = accumulate_pressures(pressures, pop, cfg)
        assert new.social_tension <= 1.0
