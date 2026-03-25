"""Tests for per-person update logic, reproduction, and trait mechanics."""

import random

import pytest

from sim.state import Occupation, Person, SimConfig, Trait


def make_person(
    person_id: str = "p1",
    age: float = 30.0,
    health: float = 0.9,
    morale: float = 0.8,
    traits: list[Trait] | None = None,
    occupation: Occupation = Occupation.LABORER,
    ring_id: str = "ring_1",
) -> Person:
    return Person(
        person_id=person_id,
        name="Test",
        age=age,
        occupation=occupation,
        health=health,
        morale=morale,
        influence=0.1,
        ring_id=ring_id,
        traits=traits or [],
    )


class TestAging:
    def test_age_advances_one_day_per_tick(self) -> None:
        from sim.population import age_person

        cfg = SimConfig()
        p = make_person(age=30.0)
        updated = age_person(p, cfg)
        assert updated.age == pytest.approx(30.0 + 1.0 / 365.0)

    def test_health_decays_slowly(self) -> None:
        from sim.population import age_person

        cfg = SimConfig()
        p = make_person(health=1.0)
        updated = age_person(p, cfg)
        assert updated.health < 1.0
        assert updated.health > 0.99  # slow decay

    def test_resilient_decays_health_slower(self) -> None:
        from sim.population import age_person

        cfg = SimConfig()
        base = make_person(health=1.0)
        resilient = make_person(health=1.0, traits=[Trait.RESILIENT])
        base_updated = age_person(base, cfg)
        res_updated = age_person(resilient, cfg)
        assert res_updated.health > base_updated.health

    def test_health_does_not_go_below_zero(self) -> None:
        from sim.population import age_person

        cfg = SimConfig()
        p = make_person(health=0.0)
        updated = age_person(p, cfg)
        assert updated.health >= 0.0


class TestMoraleUpdate:
    def test_low_resources_reduce_morale(self) -> None:
        from sim.population import update_morale

        cfg = SimConfig()
        p = make_person(morale=0.8)
        # resource_fill of 0.3 means 70% deficit — should hurt morale
        updated = update_morale(p, resource_fill=0.3, social_tension=0.0, cfg=cfg)
        assert updated.morale < p.morale

    def test_full_resources_preserve_morale(self) -> None:
        from sim.population import update_morale

        cfg = SimConfig()
        p = make_person(morale=0.8)
        updated = update_morale(p, resource_fill=1.0, social_tension=0.0, cfg=cfg)
        # Should not drop morale significantly with full resources and no tension
        assert updated.morale >= p.morale - 0.01

    def test_anxious_loses_more_morale(self) -> None:
        from sim.population import update_morale

        cfg = SimConfig()
        base = make_person(morale=0.8)
        anxious = make_person(morale=0.8, traits=[Trait.ANXIOUS])
        base_updated = update_morale(base, resource_fill=0.3, social_tension=0.5, cfg=cfg)
        anx_updated = update_morale(anxious, resource_fill=0.3, social_tension=0.5, cfg=cfg)
        assert anx_updated.morale < base_updated.morale

    def test_resilient_loses_less_morale(self) -> None:
        from sim.population import update_morale

        cfg = SimConfig()
        base = make_person(morale=0.8)
        resilient = make_person(morale=0.8, traits=[Trait.RESILIENT])
        base_updated = update_morale(base, resource_fill=0.3, social_tension=0.5, cfg=cfg)
        res_updated = update_morale(resilient, resource_fill=0.3, social_tension=0.5, cfg=cfg)
        assert res_updated.morale > base_updated.morale

    def test_morale_does_not_go_below_zero(self) -> None:
        from sim.population import update_morale

        cfg = SimConfig()
        p = make_person(morale=0.0)
        updated = update_morale(p, resource_fill=0.0, social_tension=1.0, cfg=cfg)
        assert updated.morale >= 0.0

    def test_morale_does_not_exceed_one(self) -> None:
        from sim.population import update_morale

        cfg = SimConfig()
        p = make_person(morale=1.0)
        updated = update_morale(p, resource_fill=1.0, social_tension=0.0, cfg=cfg)
        assert updated.morale <= 1.0


class TestReproduction:
    def test_child_has_parent_ids(self) -> None:
        from sim.population import reproduce

        cfg = SimConfig()
        rng = random.Random(42)
        parent_a = make_person("pa", age=25.0)
        parent_b = make_person("pb", age=27.0)
        child = reproduce(parent_a, parent_b, rng, cfg, child_id="c1", ring_id="ring_1")
        assert child.parent_ids == ("pa", "pb")

    def test_child_starts_at_age_zero(self) -> None:
        from sim.population import reproduce

        cfg = SimConfig()
        rng = random.Random(42)
        parent_a = make_person("pa")
        parent_b = make_person("pb")
        child = reproduce(parent_a, parent_b, rng, cfg, child_id="c1", ring_id="ring_1")
        assert child.age == 0.0

    def test_child_trait_count_capped(self) -> None:
        from sim.population import reproduce

        cfg = SimConfig()
        rng = random.Random(42)
        # Parents with max traits
        parent_a = make_person("pa", traits=[Trait.RESILIENT, Trait.SKILLED, Trait.INFLUENTIAL])
        parent_b = make_person("pb", traits=[Trait.ANXIOUS, Trait.REBELLIOUS, Trait.LAZY])
        child = reproduce(parent_a, parent_b, rng, cfg, child_id="c1", ring_id="ring_1")
        assert len(child.traits) <= cfg.max_traits

    def test_both_parents_trait_inherited_often(self) -> None:
        """Statistical: if both parents have RESILIENT, child should inherit it ~70% of the time."""
        from sim.population import reproduce

        cfg = SimConfig()
        parent_a = make_person("pa", traits=[Trait.RESILIENT])
        parent_b = make_person("pb", traits=[Trait.RESILIENT])
        n = 1000
        inherited = sum(
            Trait.RESILIENT in reproduce(
                parent_a, parent_b, random.Random(i), cfg, child_id=f"c{i}", ring_id="ring_1"
            ).traits
            for i in range(n)
        )
        rate = inherited / n
        assert 0.60 <= rate <= 0.80, f"Expected ~70% inheritance, got {rate:.2%}"

    def test_no_parents_trait_spontaneous_rare(self) -> None:
        """Statistical: if neither parent has REBELLIOUS, child should rarely inherit it (~5%)."""
        from sim.population import reproduce

        cfg = SimConfig()
        parent_a = make_person("pa", traits=[])
        parent_b = make_person("pb", traits=[])
        n = 1000
        inherited = sum(
            Trait.REBELLIOUS in reproduce(
                parent_a, parent_b, random.Random(i), cfg, child_id=f"c{i}", ring_id="ring_1"
            ).traits
            for i in range(n)
        )
        rate = inherited / n
        assert rate <= 0.12, f"Spontaneous trait rate too high: {rate:.2%}"


class TestAcquiredTraits:
    def test_apply_adds_trait(self) -> None:
        from sim.population import apply_trait_event

        p = make_person(traits=[])
        updated = apply_trait_event(p, Trait.RESILIENT, add=True)
        assert Trait.RESILIENT in updated.traits

    def test_apply_removes_trait(self) -> None:
        from sim.population import apply_trait_event

        p = make_person(traits=[Trait.RESILIENT])
        updated = apply_trait_event(p, Trait.RESILIENT, add=False)
        assert Trait.RESILIENT not in updated.traits

    def test_add_existing_trait_no_duplicate(self) -> None:
        from sim.population import apply_trait_event

        p = make_person(traits=[Trait.RESILIENT])
        updated = apply_trait_event(p, Trait.RESILIENT, add=True)
        assert updated.traits.count(Trait.RESILIENT) == 1

    def test_remove_absent_trait_is_noop(self) -> None:
        from sim.population import apply_trait_event

        p = make_person(traits=[Trait.SKILLED])
        updated = apply_trait_event(p, Trait.RESILIENT, add=False)
        assert updated.traits == [Trait.SKILLED]

    def test_add_respects_max_trait_cap(self) -> None:
        from sim.population import apply_trait_event

        cfg = SimConfig()
        p = make_person(traits=[Trait.RESILIENT, Trait.SKILLED, Trait.ANXIOUS])
        assert len(p.traits) == cfg.max_traits
        updated = apply_trait_event(p, Trait.REBELLIOUS, add=True)
        assert len(updated.traits) <= cfg.max_traits
