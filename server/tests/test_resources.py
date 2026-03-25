"""Tests for resource consumption and production logic."""

from sim.state import Occupation, Person, SimConfig, Trait


def make_person(
    person_id: str = "p1",
    occupation: Occupation = Occupation.LABORER,
    health: float = 1.0,
    traits: list[Trait] | None = None,
) -> Person:
    return Person(
        person_id=person_id,
        name="Test",
        age=30.0,
        occupation=occupation,
        health=health,
        morale=0.8,
        influence=0.1,
        ring_id="ring_1",
        traits=traits or [],
    )


class TestConsumption:
    def test_single_person_food_consumption(self) -> None:
        from sim.resources import consumption_for_ring

        cfg = SimConfig()
        pop = [make_person()]
        consumed = consumption_for_ring(pop, cfg)
        assert consumed["food"] == pytest.approx(cfg.food_per_person)
        assert consumed["water"] == pytest.approx(cfg.water_per_person)
        assert consumed["oxygen"] == pytest.approx(cfg.oxygen_per_person)

    def test_consumption_scales_with_population(self) -> None:
        from sim.resources import consumption_for_ring

        cfg = SimConfig()
        pop = [make_person(f"p{i}") for i in range(10)]
        consumed = consumption_for_ring(pop, cfg)
        assert consumed["food"] == pytest.approx(cfg.food_per_person * 10)

    def test_power_consumption_is_per_ring(self) -> None:
        from sim.resources import consumption_for_ring

        cfg = SimConfig()
        pop1 = [make_person("p1")]
        pop10 = [make_person(f"p{i}") for i in range(10)]
        c1 = consumption_for_ring(pop1, cfg)
        c10 = consumption_for_ring(pop10, cfg)
        # Power has a fixed ring overhead component
        assert c10["power"] > c1["power"]


class TestProduction:
    def test_farmer_produces_food(self) -> None:
        from sim.resources import production_for_ring

        cfg = SimConfig()
        farmer = make_person(occupation=Occupation.FARMER)
        prod = production_for_ring([farmer], cfg)
        assert prod["food"] == pytest.approx(cfg.food_per_farmer)

    def test_skilled_farmer_produces_more(self) -> None:
        from sim.resources import production_for_ring

        cfg = SimConfig()
        base = make_person(occupation=Occupation.FARMER)
        skilled = make_person(occupation=Occupation.FARMER, traits=[Trait.SKILLED])
        base_prod = production_for_ring([base], cfg)
        skilled_prod = production_for_ring([skilled], cfg)
        assert skilled_prod["food"] > base_prod["food"]
        assert skilled_prod["food"] == pytest.approx(
            base_prod["food"] * cfg.trait_skilled_output_mult
        )

    def test_lazy_farmer_produces_less(self) -> None:
        from sim.resources import production_for_ring

        cfg = SimConfig()
        base = make_person(occupation=Occupation.FARMER)
        lazy = make_person(occupation=Occupation.FARMER, traits=[Trait.LAZY])
        base_prod = production_for_ring([base], cfg)
        lazy_prod = production_for_ring([lazy], cfg)
        assert lazy_prod["food"] < base_prod["food"]

    def test_life_support_produces_oxygen_and_water(self) -> None:
        from sim.resources import production_for_ring

        cfg = SimConfig()
        worker = make_person(occupation=Occupation.LIFE_SUPPORT)
        prod = production_for_ring([worker], cfg)
        assert prod["oxygen"] == pytest.approx(cfg.oxygen_per_life_support)
        assert prod["water"] == pytest.approx(cfg.water_per_life_support)

    def test_non_producing_occupations_produce_zero_food(self) -> None:
        from sim.resources import production_for_ring

        cfg = SimConfig()
        engineer = make_person(occupation=Occupation.ENGINEER)
        prod = production_for_ring([engineer], cfg)
        assert prod["food"] == pytest.approx(0.0)


import pytest
