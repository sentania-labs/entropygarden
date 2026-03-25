"""Tests for state model serialization and validation."""

import json

import pytest

from sim.state import (
    GameState,
    HiddenPressures,
    Occupation,
    Person,
    ResourcePool,
    RingState,
    SimConfig,
    Trait,
)


def make_person(
    person_id: str = "p1",
    ring_id: str = "ring_1",
    traits: list[Trait] | None = None,
    parent_ids: tuple[str, str] | None = None,
) -> Person:
    return Person(
        person_id=person_id,
        name="Test Person",
        age=30.0,
        occupation=Occupation.LABORER,
        health=0.9,
        morale=0.8,
        influence=0.1,
        ring_id=ring_id,
        traits=traits or [],
        parent_ids=parent_ids,
    )


def make_ring(ring_id: str = "ring_1", population: list[Person] | None = None) -> RingState:
    return RingState(
        ring_id=ring_id,
        population=population or [make_person(ring_id=ring_id)],
        resources=ResourcePool(food=350.0, water=350.0, oxygen=350.0, power=350.0, morale=0.8),
        pressures=HiddenPressures(maintenance_debt=0.05, ecological_drift=0.02, social_tension=0.01),
    )


def make_game_state(seed: int = 42) -> GameState:
    return GameState(
        game_id="test-game",
        tick=0,
        seed=seed,
        rings={
            "ring_1": make_ring("ring_1"),
            "ring_2": make_ring("ring_2"),
            "ring_3": make_ring("ring_3"),
        },
    )


class TestPersonModel:
    def test_person_defaults(self) -> None:
        p = make_person()
        assert p.traits == []
        assert p.parent_ids is None

    def test_person_with_traits(self) -> None:
        p = make_person(traits=[Trait.RESILIENT, Trait.SKILLED])
        assert Trait.RESILIENT in p.traits
        assert Trait.SKILLED in p.traits

    def test_person_with_parent_ids(self) -> None:
        p = make_person(parent_ids=("p_mom", "p_dad"))
        assert p.parent_ids == ("p_mom", "p_dad")

    def test_health_clamped(self) -> None:
        with pytest.raises(Exception):
            Person(
                person_id="p",
                name="x",
                age=20.0,
                occupation=Occupation.FARMER,
                health=1.5,  # invalid
                morale=0.5,
                influence=0.1,
                ring_id="ring_1",
            )

    def test_morale_clamped(self) -> None:
        with pytest.raises(Exception):
            Person(
                person_id="p",
                name="x",
                age=20.0,
                occupation=Occupation.FARMER,
                health=0.5,
                morale=-0.1,  # invalid
                influence=0.1,
                ring_id="ring_1",
            )


class TestSerialization:
    def test_person_roundtrip(self) -> None:
        p = make_person(traits=[Trait.ANXIOUS], parent_ids=("a", "b"))
        assert Person.model_validate(p.model_dump()) == p

    def test_person_json_roundtrip(self) -> None:
        p = make_person(traits=[Trait.RESILIENT])
        json_str = p.model_dump_json()
        p2 = Person.model_validate_json(json_str)
        assert p2 == p

    def test_game_state_roundtrip(self) -> None:
        gs = make_game_state()
        assert GameState.model_validate(gs.model_dump()) == gs

    def test_game_state_json_roundtrip(self) -> None:
        gs = make_game_state()
        json_str = gs.model_dump_json()
        gs2 = GameState.model_validate_json(json_str)
        assert gs2 == gs

    def test_game_state_is_plain_json(self) -> None:
        """State must be serializable to standard JSON (no custom types)."""
        gs = make_game_state()
        raw = json.loads(gs.model_dump_json())
        assert isinstance(raw, dict)
        assert "rings" in raw


class TestGameStateHelpers:
    def test_year_property(self) -> None:
        gs = make_game_state()
        gs2 = gs.model_copy(update={"tick": 365})
        assert gs2.year == pytest.approx(1.0)

    def test_year_at_tick_0(self) -> None:
        gs = make_game_state()
        assert gs.year == 0.0

    def test_all_people_flat(self) -> None:
        gs = make_game_state()
        people = gs.all_people()
        assert len(people) == 3  # one per ring in our test setup

    def test_all_people_includes_all_rings(self) -> None:
        gs = make_game_state()
        ring_ids = {p.ring_id for p in gs.all_people()}
        assert ring_ids == {"ring_1", "ring_2", "ring_3"}


class TestSimConfig:
    def test_default_config_instantiates(self) -> None:
        cfg = SimConfig()
        assert cfg.food_per_person > 0
        assert cfg.max_traits == 3

    def test_occupation_weights_cover_all_occupations(self) -> None:
        cfg = SimConfig()
        total = sum(cfg.occupation_weights.values())
        assert abs(total - 1.0) < 0.01, f"Occupation weights sum to {total}, expected ~1.0"
