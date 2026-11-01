"""Expected value and repeated-bet growth, conditional on stated probabilities.

Individual losses are allowed. None of these functions estimates true event
probabilities from a past winning streak or turns model scores into certainty.
"""
import math


def validate(p, odds):
    if not math.isfinite(p) or not 0 <= p <= 1 or not math.isfinite(odds) or odds <= 1:
        raise ValueError('Expected probability in [0,1] and finite decimal odds >1')


def expected_unit_profit(p, odds, cost_per_unit=0.):
    validate(p, odds)
    if not math.isfinite(cost_per_unit) or cost_per_unit < 0:
        raise ValueError('Invalid cost')
    return p*odds-1-cost_per_unit


def expected_profit_repeated(p, odds, stake, repetitions):
    if not math.isfinite(stake) or stake < 0 or not isinstance(repetitions, int) or repetitions < 0:
        raise ValueError('Invalid stake or repetition count')
    return stake*repetitions*expected_unit_profit(p, odds)


def expected_log_growth(p, odds, bankroll_fraction):
    validate(p, odds)
    if not math.isfinite(bankroll_fraction) or not 0 <= bankroll_fraction < 1:
        raise ValueError('Bankroll fraction must be in [0,1)')
    return p*math.log1p(bankroll_fraction*(odds-1))+(1-p)*math.log1p(-bankroll_fraction)


def kelly_fraction(p, odds):
    validate(p, odds)
    return max(0.,min(1.,expected_unit_profit(p,odds)/(odds-1)))


def expected_portfolio_profit(probabilities, gross_payoffs, stakes):
    """Joint scenarios settle all correlated legs together; expectation is linear."""
    if (len(probabilities)!=len(gross_payoffs) or not probabilities
            or any(not math.isfinite(p) or p<0 for p in probabilities)
            or not math.isclose(sum(probabilities),1.,abs_tol=1e-10)
            or any(not math.isfinite(w) or w<0 for w in stakes)):
        raise ValueError('Invalid joint scenario distribution or stakes')
    if any(len(row)!=len(stakes) or any(not math.isfinite(v) or v<0 for v in row) for row in gross_payoffs):
        raise ValueError('Invalid payoff matrix')
    budget=sum(stakes)
    return sum(p*(sum(w*r for w,r in zip(stakes,row))-budget) for p,row in zip(probabilities,gross_payoffs))
