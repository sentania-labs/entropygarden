# Generation Ship Simulator – Design Doc (v1)

## Overview
A persistent, multiplayer-capable generation ship simulation inspired by Aurora and Oregon Trail.

## Core Concept
- Continuous real-time simulation
- Structured decision windows
- Asymmetric multiplayer roles
- Ecological + social drift over generations

## Game Loop
1. Continuous simulation runs on server
2. Periodic decision windows open
3. Players/agents submit actions
4. System resolves conflicts
5. Consequences propagate

## Time Model
- 100 years (game) = 1 year (real)
- Simulation always running
- Decision windows every 6–12 hours

## Roles
- Captain: policy + priorities
- Engineer: systems + power + rotation
- Ecologist: food + atmosphere
- Governor: order + enforcement
- Ring Delegate: local influence

## Core Systems
Resources:
- Food, Water, Oxygen, Power, Morale

Hidden:
- Drift, Maintenance Debt, Social Tension

## Drift System
- Gradual degradation of systems
- Cultural and ecological divergence
- Partial irreversibility

## Multiplayer Design
- Asymmetric information
- Negotiation-driven gameplay
- Policy + action model

## Technical Architecture
- Server: authoritative sim engine
- Client: web-based dashboard
- LLM: role agents + narration

## MVP Scope
- 3 rings
- 3–5 roles
- Turn windows
- Event system

## Key Principle
Slow, compounding failure with incomplete information.