from collections import Counter

import pytest
from pydantic import ValidationError

from game_agent.griddle import CardDeck, FlatLetterGrid, ForwardModelGriddle, GriddleState, TrieDict
from game_agent.griddle.benchmark import BenchmarkConfig, run_benchmark
from game_agent.griddle.griddle_agents import MCSAgent


def config(**updates):
    values = {
        "size": 2, "seeds": [7, 9], "agent_seed": 123,
        "agents": [
            {"name": "random", "kind": "random"},
            {"name": "mcs", "kind": "mcs", "params": {"rollouts_per_square": 2}},
        ],
    }
    values.update(updates)
    return BenchmarkConfig.model_validate(values)


def stable_results(report):
    return {(r["agent"], r["game_seed"]): {k: v for k, v in r.items() if k != "elapsed_seconds"}
            for r in report["results"]}


def test_agents_share_exact_deals_and_result_traces_replay():
    report = run_benchmark(config())
    assert len(report["results"]) == 4
    for seed in [7, 9]:
        records = [r for r in report["results"] if r["game_seed"] == seed]
        assert len({r["deal"] for r in records}) == 1
        for record in records:
            model = ForwardModelGriddle.new_game(2, seed=seed)
            for move in record["moves"]:
                assert model.state.current_letter == move["letter"]
                assert model.state.grid.get_free_indices()[move["action"]] == move["index"]
                model.act(move["action"])
            assert model.is_terminal()
            assert "".join(model.state.grid.letters) == record["final_grid"]
            assert model.score() == record["score"]
    assert all(row["games"] == 2 for row in report["summary"])
    assert report["config"]["agents"][1]["params"] == {"rollouts_per_square": 2}
    assert len(report["dictionary_sha256"]) == 64


def test_results_are_reproducible_and_independent_of_run_order():
    original = config()
    reordered = config(seeds=list(reversed(original.seeds)),
                       agents=[s.model_dump() for s in reversed(original.agents)])
    assert stable_results(run_benchmark(original)) == stable_results(run_benchmark(reordered))


def test_custom_factory_receives_params_and_fresh_seeded_instance_each_game():
    created = []

    class CustomPlayer:
        def __init__(self):
            self.turns = 0

        def get_action(self, observation):
            assert observation.state.grid.n_free() == 4 - self.turns
            self.turns += 1
            observation.act(0)  # Even a mutating agent cannot place in the live game.
            return 0

    def factory(params, seed):
        assert params == {"model": "example/model", "options": {"temperature": 0}}
        params["options"]["temperature"] = 0.9
        player = CustomPlayer()
        created.append((player, seed))
        return player

    settings = config(agents=[{"name": "custom", "kind": "custom", "params": {
        "model": "example/model", "options": {"temperature": 0}}}])
    report = run_benchmark(settings, factories={"custom": factory})
    assert len(created) == 2
    assert created[0][0] is not created[1][0]
    assert created[0][1] != created[1][1]
    assert all(player.turns == 4 for player, _ in created)
    assert len(report["results"]) == 2
    assert report["config"]["agents"][0]["params"]["options"]["temperature"] == 0


@pytest.mark.parametrize("updates", [
    {"seeds": []}, {"seeds": [1, 1]}, {"seeds": [True]}, {"agents": []},
    {"agents": [{"name": "same", "kind": "random"}, {"name": "same", "kind": "mcs"}]},
    {"size": 7}, {"typo": 1},
])
def test_invalid_configs_rejected(updates):
    with pytest.raises(ValidationError):
        config(**updates)


@pytest.mark.parametrize("kind,params", [
    ("missing", {}), ("random", {"ignored": True}), ("greedy", {"seed": 5}),
    ("mcs", {"rollouts_per_square": 0}), ("mcs", {"rollouts_per_square": True}),
    ("mcs", {"n_rolls": 10}),
])
def test_invalid_agents_fail_before_games_start(kind, params):
    progress = []
    with pytest.raises(ValueError):
        run_benchmark(config(agents=[{"name": "bad", "kind": kind, "params": params}]),
                      progress=progress.append)
    assert progress == []


def test_agent_errors_are_not_silently_scored_as_zero():
    class BadPlayer:
        def get_action(self, model):
            return -1

    with pytest.raises(ValueError, match="bad returned invalid action"):
        run_benchmark(config(agents=[{"name": "bad", "kind": "bad"}]),
                      factories={"bad": lambda params, seed: BadPlayer()})


@pytest.mark.parametrize("budget", [0, -1, True, 1.5, "10"])
def test_mcs_budget_validation(budget):
    with pytest.raises(ValueError):
        MCSAgent(budget)


def test_mcs_evaluates_budget_per_square_and_selects_best_mean(monkeypatch):
    model = ForwardModelGriddle.new_game(2, seed=7, trie_dict=TrieDict())
    calls = []

    def rollout(model, action, deal_seed, action_seed):
        calls.append((action, deal_seed, action_seed))
        return [1, 9, 3, 2][action]

    monkeypatch.setattr(MCSAgent, "_rollout", staticmethod(rollout))
    assert MCSAgent(3, seed=5).get_action(model) == 1
    assert Counter(action for action, _, _ in calls) == {0: 3, 1: 3, 2: 3, 3: 3}
    # Common random numbers across candidates, distinct rollouts within a candidate.
    assert calls[:3] == [(0, deal, action) for _, deal, action in calls[3:6]]
    assert len({(deal, action) for _, deal, action in calls}) == 3


def test_mcs_does_not_peek_at_live_future_or_mutate_it():
    model = ForwardModelGriddle.new_game(2, seed=7, trie_dict=TrieDict(["AT", "IT"]))
    control = model.copy_state()
    other_future = model.sample_future(999)
    assert model.state == other_future.state
    assert MCSAgent(5, seed=9).get_action(model) == MCSAgent(5, seed=9).get_action(other_future)
    while not model.is_terminal():
        assert model.state == control.state
        model.act(0)
        control.act(0)


def test_mcs_terminal_rejection_and_immediate_scoring():
    state = GriddleState(FlatLetterGrid(2, tuple("A XY")), CardDeck(()), "T")
    model = ForwardModelGriddle(state, TrieDict(["AT"]))
    assert MCSAgent._rollout(model, 0, 1, 2) == 1
    model.act(0)
    with pytest.raises(ValueError, match="finished"):
        MCSAgent(2).get_action(model)


def test_completed_games_and_failed_agent_metrics_are_checkpointed():
    import copy

    class FailedPlayer:
        def get_action(self, model):
            raise RuntimeError("service unavailable")

        def get_metrics(self):
            return {"model_calls": 1}

    updates = []
    settings = config(seeds=[7], agents=[
        {"name": "random", "kind": "random"}, {"name": "failed", "kind": "failed"}])
    with pytest.raises(RuntimeError, match="service unavailable"):
        run_benchmark(settings, factories={"failed": lambda params, seed: FailedPlayer()},
                      on_update=lambda report: updates.append(copy.deepcopy(report)))
    assert updates[-1]["complete"] is False
    assert len(updates[-1]["results"]) == 1
    assert updates[-1]["failure"]["agent"] == "failed"
    assert updates[-1]["failure"]["agent_metrics"]["model_calls"] == 1


def test_successful_report_includes_metrics_and_completion_flag():
    class MeteredPlayer:
        def get_action(self, model):
            return 0

        def get_metrics(self):
            return {"model_calls": 4, "tool_calls": 0}

    report = run_benchmark(config(seeds=[7], agents=[{"name": "metered", "kind": "metered"}]),
                           factories={"metered": lambda params, seed: MeteredPlayer()})
    assert report["complete"] is True
    assert report["results"][0]["agent_metrics"] == {"model_calls": 4, "tool_calls": 0}
    assert report["summary"][0]["total_model_calls"] == 4
    assert report["summary"][0]["total_reported_cost_usd"] is None


@pytest.mark.parametrize("fail", [False, True])
def test_harness_owns_one_async_session_per_game_and_closes_on_failure(fail):
    from contextlib import asynccontextmanager
    events = []

    class PersistentPlayer:
        @asynccontextmanager
        async def game_session(self):
            events.append("open")
            try:
                yield self
            finally:
                events.append("close")

        def get_action(self, model):
            pytest.fail("harness must use the asynchronous interface")

        async def get_action_async(self, model):
            events.append("move")
            if fail:
                raise RuntimeError("failed move")
            return 0

    settings = config(seeds=[7], agents=[{"name": "persistent", "kind": "persistent"}])
    if fail:
        with pytest.raises(RuntimeError, match="failed move"):
            run_benchmark(settings, factories={"persistent": lambda params, seed: PersistentPlayer()})
        assert events == ["open", "move", "close"]
    else:
        run_benchmark(settings, factories={"persistent": lambda params, seed: PersistentPlayer()})
        assert events == ["open", "move", "move", "move", "move", "close"]
