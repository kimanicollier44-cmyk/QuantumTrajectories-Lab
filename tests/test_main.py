"""Tests for QuantumTrajectories-Lab.

Every stochastic test runs on the lab's own seeded splitmix64
stream, so the suite is deterministic: the same numbers land on
every machine, and the tolerances are the ones stated in main.py
(standard errors computed from the data, never widened silently).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as lab


# ---------------------------------------------------------------- PRNG
def test_prng_reproducible():
    a = lab.SplitMix64(42)
    b = lab.SplitMix64(42)
    assert [a.random() for _ in range(500)] == [b.random() for _ in range(500)]


def test_prng_range_and_mean():
    rng = lab.SplitMix64(lab.SEED)
    draws = [rng.random() for _ in range(20000)]
    assert all(0.0 <= u < 1.0 for u in draws)
    assert 0.485 < sum(draws) / len(draws) < 0.515


def test_prng_seed_changes_stream():
    assert lab.SplitMix64(1).random() != lab.SplitMix64(2).random()


# ---------------------------------------------------------------- master equation
def test_ss_formula_third():
    assert abs(lab.rhoee_steady(1.0, 0.0) - 1.0 / 3.0) < 1e-15


def test_ss_formula_resonance_omega2():
    assert abs(lab.rhoee_steady(2.0, 0.0) - 4.0 / 9.0) < 1e-12


def test_ss_saturation_below_half():
    assert 0.4999 < lab.rhoee_steady(100.0, 0.0) < 0.5


def test_ss_detuning_symmetric():
    assert lab.rhoee_steady(1.5, 2.0) == lab.rhoee_steady(1.5, -2.0)


def test_ss_coherence_value():
    assert abs(abs(lab.rhoeg_steady(1.0, 0.0)) - 1.0 / 3.0) < 1e-12


def test_trace_preserved():
    states = lab.master_samples(1.0, 0.0, [10.0, 20.0], dt=0.01)
    for st in states.values():
        assert abs(st[0] + st[3] - 1.0) < 1e-12


def test_integrated_steady_state_matches_closed_form():
    rep = lab.master_report(1.0, 0.0)
    assert rep["rhoee_steady_abs_error"] < 1e-6
    assert rep["rhoeg_steady_abs_error"] < 1e-6


def test_integrated_steady_state_detuned():
    rep = lab.master_report(2.0, 1.5)
    assert rep["rhoee_steady_abs_error"] < 1e-6
    assert rep["rhoeg_steady_abs_error"] < 1e-6


def test_pure_decay_exact():
    st = lab.master_samples(0.0, 0.0, [2.0], dt=0.005,
                            y0=(1.0, 0.0, 0.0, 0.0))[2.0]
    assert abs(st[0] - math.exp(-2.0)) < 1e-6


def test_coherence_decay_exact():
    st = lab.master_samples(0.0, 0.0, [3.0], dt=0.005,
                            y0=(0.5, 0.5, 0.0, 0.5))[3.0]
    assert abs(st[1] - 0.5 * math.exp(-1.5)) < 1e-6


def test_rabi_envelope_ratio():
    rabi = lab.master_report(1.0, 0.0)["rabi"]
    ratio = rabi["envelope_ratio_measured"] / rabi["envelope_ratio_theory"]
    assert abs(ratio - 1.0) < 0.02


def test_weak_drive_overdamped_no_overshoot():
    states = lab.master_samples(0.2, 0.0, [float(t) for t in range(0, 31)],
                                dt=0.01)
    ss = lab.rhoee_steady(0.2, 0.0)
    assert all(st[0] <= ss * (1.0 + 1e-9) + 1e-12 for st in states.values())


# ---------------------------------------------------------------- trajectories
def test_propagator_unitary_without_decay():
    U = lab.heff_propagator(1.3, 0.7, 0.02, gamma=0.0)
    psi = (0.6 + 0.1j, 0.5 - 0.62j)
    out = (U[0] * psi[0] + U[1] * psi[1], U[2] * psi[0] + U[3] * psi[1])
    n_in = abs(psi[0]) ** 2 + abs(psi[1]) ** 2
    assert abs((abs(out[0]) ** 2 + abs(out[1]) ** 2) - n_in) < 1e-12


def test_post_jump_ground_and_g2_zero():
    ground = lab.jump_reset()
    assert ground[0] == 0.0j and ground[1] == 1.0 + 0.0j
    # after a jump rho_ee = 0 exactly, so the instantaneous rate -
    # and with it the probability of an immediate second jump - is 0
    assert lab.instantaneous_jump_rate(ground) == 0.0
    assert lab.instantaneous_jump_rate((1.0 + 0.0j, 0.0j)) == lab.GAMMA


def test_trajectory_reproducible_same_seed():
    a = lab.run_trajectory(1.0, 0.0, 20.0, 0.02, lab.SEED + 5)
    b = lab.run_trajectory(1.0, 0.0, 20.0, 0.02, lab.SEED + 5)
    assert a["jump_times"] == b["jump_times"]


def test_trajectory_differs_other_seed():
    a = lab.run_trajectory(1.0, 0.0, 20.0, 0.02, lab.SEED + 5)
    b = lab.run_trajectory(1.0, 0.0, 20.0, 0.02, lab.SEED + 6)
    assert a["jump_times"] != b["jump_times"]


def test_trajectory_jumps_strictly_increasing():
    tr = lab.run_trajectory(1.0, 0.0, 20.0, 0.02, lab.SEED + 5)
    js = tr["jump_times"]
    assert all(b > a for a, b in zip(js, js[1:]))


# ---------------------------------------------------------------- ensemble + records (reduced budgets)
def test_ensemble_deviation_shrinks_and_scales():
    ens = lab.ensemble_report(m_values=(10, 100, 400),
                              seed_base=lab.SEED + 7)
    devs = ens["deviations"]
    assert devs["10"] > devs["100"] > devs["400"]
    assert -0.8 < ens["fitted_exponent"] < -0.2
    assert devs["400"] < 4.0 * ens["sigma_bound_largest_m"]


def test_waiting_mean_matches_inverse_rate():
    w = lab.waiting_report(n_traj=150, seed_base=lab.SEED + 11)
    assert abs(w["mean_wait"] - w["theory_mean_wait"]) < 4.0 * w["sem_wait"]


def test_waiting_short_waits_suppressed():
    w = lab.waiting_report(n_traj=150, seed_base=lab.SEED + 11)
    assert w["short_wait_fraction"] < (
        w["short_wait_fraction_exponential"] - 0.03)
    assert w["short_wait_fraction"] > 0.02
    assert w["min_wait"] >= 0.06


def test_records_mean_and_variance():
    w = lab.waiting_report(n_traj=150, seed_base=lab.SEED + 11)
    assert abs(w["mean_counts"] - w["theory_counts"]) < 4.0 * w["sem_counts"]
    assert 0.3 * w["mean_counts"] < w["var_counts"] < 1.6 * w["mean_counts"]


# ---------------------------------------------------------------- classifier
def test_classifier_scenarios():
    rep = lab.classifier_report()
    assert rep["textbook_rabi_drive_O1_D0"]["label"] == "rabi-transient"
    assert rep["saturated_resonant_drive_O3_D0"]["label"] == "emissive-steady"
    assert rep["gentle_drive_O0.3_D0"]["label"] == "weak-drive"
    assert rep["far_detuned_shelf_O0.5_D4"]["label"] == "shelved-dark"
    assert rep["strong_detuned_drive_O2_D2"]["label"] == "rabi-transient"
    assert rep["no_drive_O0_D0"]["label"] == "shelved-dark"


def test_classifier_matches_policy_on_grid():
    for feats, label in lab.TRAINING_GRID:
        assert lab.classify_regime(*feats) == label


# ---------------------------------------------------------------- gates + seats + CLI
def test_hold_gates_14_all_hold():
    assert len(lab.HOLD_GATES) == 14
    assert all(v.startswith("HOLD") for v in lab.HOLD_GATES.values())
    assert lab.gate("real_single_photon_source_claim") == "HOLD"
    assert lab.gate("detector_efficiency_claim") == "HOLD"
    assert lab.gate("quantum_network_deployment") == "HOLD"
    assert lab.gate("experimental_data_substitution") == "HOLD"
    assert lab.gate("run_simulation") == "PROCEED"


def test_seats_never_override_hold():
    brains = lab.brains_report()
    assert brains["decider"]["can_override_hold"] is False
    assert brains["decider"]["seat"] == "Gemini Argon 4 Extended Thinking"
    assert brains["decider"]["model"] == "gemini-argon-4"
    assert brains["advisor"]["can_override_hold"] is False
    assert brains["flow"]["rendered"] is False
    assert brains["flow"]["live"] == 0


def test_hold_demo_exits_2():
    assert lab.main(["hold-demo"]) == 2
    assert lab.main(["hold-demo", "quantum_network_deployment"]) == 2
    assert lab.main(["hold-demo", "run_simulation"]) == 0


def test_checks_all_pass():
    checks = lab.run_checks()
    assert all(ok for _, ok in checks), [n for n, ok in checks if not ok]
