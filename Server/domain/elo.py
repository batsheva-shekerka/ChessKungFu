"""ELO rating rules (pure domain logic)."""

from __future__ import annotations


def calc_elo(winner_elo: int, loser_elo: int, k: int = 32) -> tuple[int, int]:
    expected_winner = 1 / (1 + 10 ** ((loser_elo - winner_elo) / 400))
    expected_loser = 1 - expected_winner
    new_winner = round(winner_elo + k * (1 - expected_winner))
    new_loser = round(loser_elo + k * (0 - expected_loser))
    return new_winner, new_loser
