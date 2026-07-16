from __future__ import annotations

import unittest

from src.stats import compute_stats, compute_team_stats


class StatsTests(unittest.TestCase):
    def test_same_match_from_two_players_is_counted_once(self) -> None:
        match_a = {
            "match_key": "same-match",
            "placement": 1,
            "kills": 2,
            "damage": 200,
            "dbnos": 1,
            "map": "Rondo",
            "weapon": "M416",
            "teammates": ["Alpha", "Bravo"],
        }
        match_b = {
            "match_key": "same-match",
            "placement": 1,
            "kills": 3,
            "damage": 300,
            "dbnos": 2,
            "map": "Rondo",
            "weapon": "AKM",
            "teammates": ["Alpha", "Bravo"],
        }
        players = {
            "a": {"alias": "Alpha", "matches": [match_a]},
            "b": {"alias": "Bravo", "matches": [match_b]},
        }
        stats, all_matches = compute_stats(players)
        team_stats = compute_team_stats(all_matches, players)

        self.assertEqual(stats["a"]["estimated_kd"], 2)
        self.assertEqual(team_stats["unique_match_count"], 1)
        self.assertEqual(team_stats["unique_chicken_count"], 1)
        self.assertEqual(team_stats["team_games_count"], 1)
        self.assertEqual(team_stats["combos"][0]["games"], 1)
        self.assertEqual(team_stats["combos"][0]["chickens"], 1)

    def test_kda_compatibility_key_matches_estimated_kd(self) -> None:
        players = {
            "a": {
                "alias": "Alpha",
                "matches": [
                    {
                        "match_key": "one",
                        "placement": 2,
                        "kills": 3,
                        "damage": 100,
                        "dbnos": 0,
                        "teammates": [],
                    }
                ],
            }
        }
        stats, _ = compute_stats(players)
        self.assertEqual(stats["a"]["kda"], stats["a"]["estimated_kd"])


if __name__ == "__main__":
    unittest.main()
