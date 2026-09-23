from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from pcopt.data import portfolio_returns
from pcopt.metrics import MetricConfig, metric_snapshot

ConstraintSpec = tuple[str, float]


@dataclass(frozen=True)
class OptimizationResult:
    weights: pd.Series
    metrics: dict[str, float]
    fitness: float
    feasible: bool
    generation: int


@dataclass
class GeneticOptimizer:
    asset_returns: pd.DataFrame
    assets: Sequence[str]
    objective: Mapping[str, float]
    constraints: Mapping[str, ConstraintSpec] | None = None
    metric_config: MetricConfig = field(default_factory=MetricConfig)
    population_size: int = 256
    generations: int = 200
    elite_fraction: float = 0.10
    mutation_rate: float = 0.20
    mutation_scale: float = 0.08
    constraint_penalty: float = 1000.0
    constraint_tolerance: float = 1e-6
    random_seed: int | None = None

    def __post_init__(self) -> None:
        if not self.assets:
            raise ValueError("assets must not be empty")
        if not self.objective:
            raise ValueError("objective must contain at least one metric weight")
        if self.population_size < 4:
            raise ValueError("population_size must be at least 4")
        if self.generations < 1:
            raise ValueError("generations must be positive")
        if not np.isfinite(self.constraint_tolerance) or self.constraint_tolerance < 0.0:
            raise ValueError("constraint_tolerance must be a non-negative finite number")
        for asset in self.assets:
            if asset not in self.asset_returns.columns:
                raise KeyError(f"asset {asset!r} not found in return data")

    def optimize(self) -> OptimizationResult:
        rng = np.random.default_rng(self.random_seed)
        population = rng.dirichlet(np.ones(len(self.assets)), size=self.population_size)

        best: OptimizationResult | None = None
        best_feasible: OptimizationResult | None = None

        for generation in range(self.generations + 1):
            evaluated = [self._evaluate(weights, generation) for weights in population]
            evaluated.sort(key=lambda item: item.fitness, reverse=True)

            if best is None or evaluated[0].fitness > best.fitness:
                best = evaluated[0]
            feasible_candidates = [item for item in evaluated if item.feasible]
            if feasible_candidates:
                if best_feasible is None or feasible_candidates[0].fitness > best_feasible.fitness:
                    best_feasible = feasible_candidates[0]

            if generation == self.generations:
                break

            elite_count = max(2, int(self.population_size * self.elite_fraction))
            elites = np.vstack([item.weights.to_numpy(dtype=float) for item in evaluated[:elite_count]])
            children = [*elites]
            while len(children) < self.population_size:
                parent_idx = rng.choice(elite_count, size=2, replace=True)
                child = self._crossover(elites[parent_idx[0]], elites[parent_idx[1]], rng)
                child = self._mutate(child, rng)
                children.append(child)
            population = np.vstack(children[: self.population_size])

        assert best is not None
        return best_feasible or best

    def _evaluate(self, weights: np.ndarray, generation: int) -> OptimizationResult:
        series_weights = pd.Series(weights, index=self.assets, dtype=float)
        returns = portfolio_returns(self.asset_returns, series_weights)
        metrics = metric_snapshot(returns, self.metric_config)
        feasible, violation = self._constraint_violation(metrics)
        objective_score = self._objective_score(metrics)
        fitness = objective_score - self.constraint_penalty * violation
        return OptimizationResult(
            weights=series_weights,
            metrics=metrics,
            fitness=float(fitness),
            feasible=feasible,
            generation=generation,
        )

    def _objective_score(self, metrics: Mapping[str, float]) -> float:
        score = 0.0
        missing: list[str] = []
        for metric, weight in self.objective.items():
            if metric not in metrics:
                missing.append(metric)
            else:
                score += float(weight) * float(metrics[metric])
        if missing:
            raise KeyError(f"objective metric(s) unavailable: {missing}")
        return score

    def _constraint_violation(self, metrics: Mapping[str, float]) -> tuple[bool, float]:
        total = 0.0
        feasible = True
        for metric, spec in (self.constraints or {}).items():
            if metric not in metrics:
                raise KeyError(f"constraint metric {metric!r} unavailable")
            op, bound = spec
            value = float(metrics[metric])
            bound = float(bound)
            scale = max(abs(bound), 1.0)
            tolerance = self.constraint_tolerance * scale

            if op == "<=":
                violation = max(0.0, value - bound - tolerance)
                feasible = feasible and value <= bound + tolerance
            elif op == "<":
                violation = max(0.0, value - bound + tolerance)
                feasible = feasible and value <= bound - tolerance
            elif op == ">=":
                violation = max(0.0, bound - value - tolerance)
                feasible = feasible and value >= bound - tolerance
            elif op == ">":
                violation = max(0.0, bound - value + tolerance)
                feasible = feasible and value >= bound + tolerance
            elif op in {"==", "="}:
                violation = max(0.0, abs(value - bound) - tolerance)
                feasible = feasible and abs(value - bound) <= tolerance
            else:
                raise ValueError(f"unsupported constraint operator {op!r}")
            total += violation / scale

        return feasible, total

    @staticmethod
    def _crossover(parent_a: np.ndarray, parent_b: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        alpha = rng.uniform(0.0, 1.0, size=parent_a.shape)
        child = alpha * parent_a + (1.0 - alpha) * parent_b
        return _renormalize(child)

    def _mutate(self, weights: np.ndarray, rng: np.random.Generator) -> np.ndarray:
        if rng.random() >= self.mutation_rate:
            return weights
        noise = rng.normal(0.0, self.mutation_scale, size=weights.shape)
        return _renormalize(weights + noise)


def _renormalize(weights: np.ndarray) -> np.ndarray:
    out = np.clip(np.asarray(weights, dtype=float), 0.0, None)
    total = float(out.sum())
    if not np.isfinite(total) or total <= 0.0:
        out = np.ones_like(out) / len(out)
    else:
        out = out / total
    return out
