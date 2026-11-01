"""Score-distribution markets and exact fractional-stake settlement.

Rows of ``grid`` are the selected period's home score; columns are away score.
The distribution must be supplied by a model of that sport, statistic and
period. A football-goals grid is not a model of cards, corners or player props.
Every function is mathematical/research-only and never creates an order.
"""
from __future__ import annotations

import math
from functools import lru_cache
from typing import Iterable

OUTCOMES = ("win", "half_win", "push", "half_loss", "loss")
FRACTIONS = {
    "win": (1.0, 0.0, 0.0), "half_win": (0.5, 0.0, 0.5),
    "push": (0.0, 0.0, 1.0), "half_loss": (0.0, 0.5, 0.5),
    "loss": (0.0, 1.0, 0.0),
}
MARKET_ALIASES = {
    "h2h": "1x2", "1X2": "1x2", "doublechance": "double_chance",
    "draw_no_bet": "dnb", "over_under": "totals", "spreads": "asian_handicap",
    "team_total": "team_totals", "exact_score": "correct_score",
}
SELECTION_ALIASES = {
    "1": "home", "x": "draw", "2": "away", "local": "home",
    "empate": "draw", "visitante": "away", "yes": "yes", "sí": "yes",
    "si": "yes", "no": "no", "1x": "home_draw", "x2": "draw_away",
    "12": "home_away", "home_or_draw": "home_draw", "away_or_draw": "draw_away",
    "home_or_away": "home_away", "más": "over", "mas": "over", "menos": "under",
    "impar": "odd", "par": "even",
}


def _number(value, label):
    if isinstance(value, bool):
        raise ValueError(label + " debe ser numérico y finito.")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(label + " debe ser numérico y finito.") from None
    if not math.isfinite(number):
        raise ValueError(label + " debe ser numérico y finito.")
    return number


def _score(value, label):
    value = _number(value, label)
    if value < 0 or value != int(value):
        raise ValueError(label + " debe ser un entero no negativo.")
    return int(value)


def split_line(line: float) -> tuple[float, ...]:
    """Quarter lines split equally between the neighbouring half lines."""
    line = _number(line, "La línea")
    quarters = round(line * 4)
    if abs(line * 4 - quarters) > 1e-8:
        raise ValueError("La línea debe ser múltiplo de 0,25.")
    line = quarters / 4
    return (line - 0.25, line + 0.25) if quarters % 2 else (line,)


def _sign(value):
    return 1 if value > 1e-10 else -1 if value < -1e-10 else 0


def _outcome_from_parts(parts):
    average = sum(parts) / len(parts)
    return {1.0: "win", 0.5: "half_win", 0.0: "push", -0.5: "half_loss", -1.0: "loss"}[average]


def settle_score(home, away, market, selection, *, line=None, score=None, team=None) -> dict:
    """Settle one unit against a known score, retaining win/loss/void fractions.

    An Asian line is attached to the *selected* team. For away +0.25, pass
    selection='away', line=0.25. This is pre-match/whole-period settlement;
    in-play remainder markets need an explicitly conditioned distribution.
    """
    home, away = _score(home, "Marcador local"), _score(away, "Marcador visitante")
    market = str(market).strip().lower()
    market = MARKET_ALIASES.get(market, market)
    selection = SELECTION_ALIASES.get(str(selection).lower(), str(selection).lower())
    if market == "1x2":
        if selection not in ("home", "draw", "away"):
            raise ValueError("Selección 1X2 inválida.")
        won = (selection == "home" and home > away or selection == "draw" and home == away
               or selection == "away" and away > home)
        outcome = "win" if won else "loss"
    elif market == "double_chance":
        if selection not in ("home_draw", "draw_away", "home_away"):
            raise ValueError("Selección de doble oportunidad inválida.")
        won = (home >= away if selection == "home_draw" else away >= home if selection == "draw_away" else home != away)
        outcome = "win" if won else "loss"
    elif market == "dnb":
        if selection not in ("home", "away"):
            raise ValueError("DNB requiere local o visitante.")
        margin = (home-away) * (1 if selection == "home" else -1)
        outcome = "win" if margin > 0 else "loss" if margin < 0 else "push"
    elif market == "btts":
        if selection not in ("yes", "no"):
            raise ValueError("Ambos marcan requiere sí o no.")
        outcome = "win" if (home > 0 and away > 0) == (selection == "yes") else "loss"
    elif market == "correct_score":
        if score is None:
            score = selection
        if isinstance(score, str):
            pieces = score.replace(":", "-").replace("–", "-").split("-")
        else:
            pieces = list(score)
        if len(pieces) != 2:
            raise ValueError("Marcador exacto inválido.")
        target = (_score(pieces[0], "Gol local"), _score(pieces[1], "Gol visitante"))
        outcome = "win" if (home, away) == target else "loss"
    elif market in ("totals", "team_totals"):
        if selection not in ("over", "under"):
            raise ValueError("Totales requiere más o menos.")
        if market == "team_totals" and team not in ("home", "away"):
            raise ValueError("Total de equipo requiere team='home' o 'away'.")
        value = home + away if market == "totals" else home if team == "home" else away
        parts = [_sign((value-component) * (1 if selection == "over" else -1)) for component in split_line(line)]
        outcome = _outcome_from_parts(parts)
    elif market == "asian_handicap":
        if selection not in ("home", "away"):
            raise ValueError("Hándicap asiático requiere local o visitante.")
        margin = (home-away) * (1 if selection == "home" else -1)
        outcome = _outcome_from_parts([_sign(margin+component) for component in split_line(line)])
    elif market == "european_handicap":
        # The handicap is always added to home before the three-way result.
        handicap = _number(line, "Hándicap europeo")
        if handicap != int(handicap) or selection not in ("home", "draw", "away"):
            raise ValueError("Hándicap europeo requiere línea entera y resultado 1/X/2.")
        margin = home + handicap - away
        won = (selection == "home" and margin > 0 or selection == "draw" and margin == 0
               or selection == "away" and margin < 0)
        outcome = "win" if won else "loss"
    elif market == "odd_even":
        if selection not in ("odd", "even"):
            raise ValueError("Par/impar requiere odd o even.")
        outcome = "win" if bool((home+away) % 2) == (selection == "odd") else "loss"
    elif market == "winning_margin":
        if selection not in ("home", "away", "draw"):
            raise ValueError("Margen requiere home, away o draw.")
        if selection == "draw":
            won = home == away
        else:
            margin = _score(line, "Margen exacto")
            if margin == 0:
                raise ValueError("El margen de victoria debe ser positivo.")
            won = ((home-away) if selection == "home" else (away-home)) == margin
        outcome = "win" if won else "loss"
    else:
        raise ValueError("Mercado no derivable de este marcador: " + market)
    win, loss, void = FRACTIONS[outcome]
    return {"outcome": outcome, "win_fraction": win, "loss_fraction": loss,
            "void_fraction": void, "market": market, "selection": selection}


def net_return(settlement: dict, odds: float) -> float:
    odds = _number(odds, "La cuota")
    if odds <= 1:
        raise ValueError("La cuota decimal debe ser mayor que 1.")
    return settlement["win_fraction"] * (odds - 1) - settlement["loss_fraction"]


def _grid_cells(grid: Iterable[Iterable[float]]):
    cells, width, total = [], None, 0.0
    for home, row in enumerate(grid):
        values = list(row)
        width = len(values) if width is None else width
        if width == 0 or len(values) != width:
            raise ValueError("La cuadrícula debe ser rectangular y no vacía.")
        for away, value in enumerate(values):
            p = _number(value, "La probabilidad")
            if p < 0 or p > 1:
                raise ValueError("La probabilidad debe estar entre 0 y 1.")
            cells.append((home, away, p)); total += p
    if not cells or abs(total - 1) > 1e-6:
        raise ValueError("La cuadrícula debe sumar 1; no se oculta masa de cola faltante.")
    return [(h, a, p/total) for h, a, p in cells], total


@lru_cache(maxsize=4096)
def _settlement_labels(height, width, market, selection, line, score, team):
    return tuple(settle_score(h, a, market, selection, line=line, score=score, team=team)["outcome"]
                 for h in range(height) for a in range(width))


def market_distribution(grid, market, selection, *, line=None, score=None, team=None) -> dict:
    cells, total = _grid_cells(grid)
    probabilities = dict.fromkeys(OUTCOMES, 0.0)
    line_key = _number(line, "La línea") if line is not None else None
    if isinstance(score, (list, tuple)):
        if len(score) != 2:
            raise ValueError("Marcador exacto inválido.")
        score_key = tuple(_score(value, "Marcador exacto") for value in score)
    else:
        score_key = str(score) if score is not None else None
    labels = _settlement_labels(cells[-1][0]+1, cells[-1][1]+1, str(market), str(selection),
                                line_key, score_key, str(team) if team is not None else None)
    for (_, _, p), outcome in zip(cells, labels):
        probabilities[outcome] += p
    return {"probabilities": probabilities, "input_probability_mass": total,
            "probability_win": probabilities["win"] + probabilities["half_win"],
            "probability_full_win": probabilities["win"],
            "probability_loss": probabilities["loss"] + probabilities["half_loss"],
            "probability_push": probabilities["push"], "actionable": False}


def expected_net_return(distribution, odds: float) -> float:
    """Includes voids and half settlements; p*odds-1 is only the binary case."""
    odds = _number(odds, "La cuota")
    if odds <= 1:
        raise ValueError("La cuota decimal debe ser mayor que 1.")
    p = distribution.get("probabilities", distribution)
    p = _validate_distribution(p)
    return sum(p[k] * (FRACTIONS[k][0] * (odds - 1) - FRACTIONS[k][1]) for k in OUTCOMES)


def _validate_distribution(p):
    if set(p) != set(OUTCOMES):
        raise ValueError("Faltan estados de liquidación.")
    values = [_number(p[k], "La probabilidad") for k in OUTCOMES]
    if any(v < 0 or v > 1 for v in values) or abs(sum(values)-1) > 1e-6:
        raise ValueError("Distribución de liquidación inválida.")
    return dict(zip(OUTCOMES, values))


def generalized_kelly(distribution, odds: float, *, scale=0.25, cap=0.01) -> dict:
    """Maximize expected log-wealth on [0,1], then scale and cap the fraction."""
    odds = _number(odds, "La cuota")
    scale, cap = _number(scale, "La fracción"), _number(cap, "El límite")
    if odds <= 1 or not 0 <= scale <= 1 or not 0 <= cap <= 1:
        raise ValueError("Cuota, fracción o límite inválidos.")
    p = distribution.get("probabilities", distribution)
    p = _validate_distribution(p)
    values = [(p[k], FRACTIONS[k][0] * (odds - 1) - FRACTIONS[k][1]) for k in OUTCOMES if p[k] > 0]
    def derivative(f):
        return sum(prob*r/(1+f*r) for prob, r in values)
    if derivative(0) <= 0:
        full = 0.0
    elif derivative(1-1e-12) >= 0:
        full = 1.0
    else:
        low, high = 0.0, 1-1e-12
        for _ in range(80):
            mid = (low+high)/2
            if derivative(mid) > 0: low = mid
            else: high = mid
        full = (low+high)/2
    return {"full_kelly": full, "fractional_kelly": full*scale,
            "kelly_fraction": min(cap, full*scale), "scale": scale, "cap": cap,
            "assumption": "Distribución de retornos estimada; no garantiza rentabilidad ni independencia."}


def evaluate_market(grid, market, selection, *, odds=None, line=None, score=None, team=None,
                    kelly_scale=0.25, kelly_cap=0.01) -> dict:
    result = market_distribution(grid, market, selection, line=line, score=score, team=team)
    p = result["probabilities"]
    weighted_win = p["win"] + .5*p["half_win"]
    weighted_loss = p["loss"] + .5*p["half_loss"]
    result.update({"market": market, "selection": selection, "line": line, "score": score, "team": team,
                   "fair_odds": 1+weighted_loss/weighted_win if weighted_win else None,
                   "weighted_win_mass": weighted_win, "weighted_loss_mass": weighted_loss,
                   "ev": None, "odds": odds, "kelly_fraction": 0.0,
                   "probability_source": "supplied_score_distribution",
                   "settlement_scope": "selected_period_pre_match",
                   "execution_enabled": False,
                   "limitations": ["La distribución debe corresponder al deporte, estadística y período del contrato.",
                                   "No incluye comisión, impuestos, límites ni probabilidad de anulación externa.",
                                   "Una probabilidad de ganar no reemplaza la distribución de retornos con reembolsos."]})
    if odds is not None:
        result["ev"] = expected_net_return(result, odds)
        result.update(generalized_kelly(result, odds, scale=kelly_scale, cap=kelly_cap))
    return result


def joint_event_probability(grid, selections: list[dict]) -> float:
    """Exact intersection on one joint score grid; never multiply marginals.

    Only binary win/loss legs are supported. A book's treatment of quarter
    lines, void legs and same-game products must be verified separately.
    """
    if not selections:
        raise ValueError("Indicar al menos una selección.")
    cells, _ = _grid_cells(grid)
    answer = 0.0
    for home, away, p in cells:
        outcomes = [settle_score(home, away, **leg)["outcome"] for leg in selections]
        if any(outcome not in ("win", "loss") for outcome in outcomes):
            raise ValueError("La intersección simple no admite reembolsos ni liquidaciones parciales.")
        if all(outcome == "win" for outcome in outcomes):
            answer += p
    return answer


def first_goal_team_probabilities(home_rate, away_rate) -> dict:
    """Exploratory competing homogeneous Poisson hazards, not player scoring."""
    home_rate, away_rate = _number(home_rate, "Tasa local"), _number(away_rate, "Tasa visitante")
    if min(home_rate, away_rate) < 0 or home_rate+away_rate <= 0:
        raise ValueError("Las tasas deben ser no negativas y su suma positiva.")
    total = home_rate+away_rate
    no_goal = math.exp(-total)
    return {"home": home_rate/total*(1-no_goal), "away": away_rate/total*(1-no_goal),
            "no_goal": no_goal, "status": "exploratory_unvalidated", "actionable": False,
            "assumptions": "Tasas de gol homogéneas e independientes durante todo el período.",
            "player_first_scorer_probability": None}
