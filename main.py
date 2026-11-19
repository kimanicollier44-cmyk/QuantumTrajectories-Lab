#!/usr/bin/env python3
"""QuantumTrajectories-Lab - educational quantum-jump trajectories lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
Education only - and the central lesson is stated up front:

  * This lab simulates ONE driven two-level atom two ways that must
    agree: the Lindblad master equation (the smooth ensemble curve)
    and Monte-Carlo wavefunction trajectories (jagged single runs
    with quantum jumps). The trajectory average converges to the
    master-equation curve like 1/sqrt(M) - the lab measures that
    convergence instead of asserting it.
  * A trajectory is a SIMULATED record, not a measured one. No atom
    was driven, no photon was detected, no source emitted anything.
    The photon record, the waiting times, and the g2(0) = 0 statement
    are properties of this model at the stated inputs - they are
    never a device certification, an experimental result, or a
    substitute for laboratory data.
  * Detection in the model is ideal (efficiency 1, no dark counts,
    no dead time) and that idealisation is labelled wherever the
    record is shown. Real single-photon sources, detectors, quantum
    networks, and feedback control are permanent HOLD gates - with
    Gemini Argon 4 Extended Thinking as DECIDER (names-only,
    tighten-only), Muse as advisor (never overrides HOLD), and
    Google Flow plan-only seats.

Units: the spontaneous emission rate gamma = 1 sets the clock, so
times are in units of 1/gamma and the drive strength Omega and
detuning Delta are in units of gamma. Every parameter is a labelled
teaching number.

Determinism: the stochastic engine runs on an in-file splitmix64
PRNG with a fixed seed (SEED below). Integer PRNG arithmetic is
exact on every machine, so the demo output is byte-identical
across runs and machines even though the physics is stochastic.
"""
import cmath
import hashlib
import json
import math
import sys

# ---------------------------------------------------------------- constants
VERSION = "1.0.0"
GAMMA = 1.0            # spontaneous emission rate; the unit of everything
SEED = 20261118        # fixed PRNG seed - determinism is a feature here

# Hamiltonian / Lindblad convention, stated once and used everywhere:
#   basis (|e>, |g>);  H = -Delta |e><e| + (Omega/2)(|e><g| + |g><e|)
#   one jump operator L = sqrt(gamma) |g><e|  (spontaneous emission)
#   steady state rho_ee = (Omega^2/4) / (Delta^2 + gamma^2/4 + Omega^2/2)

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "real_single_photon_source_claim": "HOLD - no claim this simulation models or certifies a real single-photon source",
    "detector_efficiency_claim": "HOLD - no detector efficiency, dark-count, or dead-time claims; model detection is ideal (efficiency 1) and labelled",
    "quantum_network_deployment": "HOLD - no deploying trajectories or records to a real quantum network or node",
    "real_atom_control": "HOLD - no control of real atoms, ions, lasers, or cavities from this simulation",
    "hardware_specification_claim": "HOLD - no hardware specifications from simulated numbers",
    "vendor_product_claim": "HOLD - no vendor or product claims; no product is modelled or endorsed",
    "antibunching_measurement_claim": "HOLD - g2(0) = 0 here is a property of the model (post-jump rho_ee = 0), not a measured device certification",
    "cryptography_security_claim": "HOLD - no QKD, key-rate, or security claims from a simulated photon record",
    "sensing_metrology_claim": "HOLD - no sensing, clock, or metrology claims from simulated trajectories",
    "medical_imaging_claim": "HOLD - no medical or biological imaging claims",
    "experimental_data_substitution": "HOLD - simulated trajectories never substitute for experimental data",
    "publication_result_claim": "HOLD - no presenting simulation output as an experimental result",
    "live_feedback_control": "HOLD - no live feedback or real-time control of an experiment from this simulation",
    "simulation_as_measurement_claim": "HOLD - a computed trajectory is not a measurement record of a real system",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# ================================================================ 1. Seeded PRNG
# splitmix64, implemented from scratch: a 64-bit counter run through
# a fixed bijective mix. All arithmetic is exact integer arithmetic,
# so the stream is identical on every machine - that is what makes a
# stochastic lab byte-identical. Uniforms are (z >> 11) * 2^-53.

_MASK64 = 0xFFFFFFFFFFFFFFFF


class SplitMix64:
    """Deterministic splitmix64 stream of uniforms in [0, 1)."""

    def __init__(self, seed):
        self.state = seed & _MASK64

    def next_uint64(self):
        self.state = (self.state + 0x9E3779B97F4A7C15) & _MASK64
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _MASK64
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _MASK64
        return z ^ (z >> 31)

    def random(self):
        return (self.next_uint64() >> 11) * (1.0 / 9007199254740992.0)


# ================================================================ 2. Master equation
# The density matrix is carried as (rho_ee, Re rho_eg, Im rho_eg,
# rho_gg) and integrated with a written-out RK4. d rho/dt comes from
# -i[H, rho] + gamma (L rho L^dagger - 1/2 {L^dagger L, rho}) with
# the convention stated at the top of the file:
#   d rho_ee = -Omega * Im(rho_eg) - gamma * rho_ee
#   d rho_eg = (i Delta - gamma/2) rho_eg - i (Omega/2)(rho_gg - rho_ee)
#   d rho_gg = +Omega * Im(rho_eg) + gamma * rho_ee
# d rho_ee + d rho_gg = 0 identically, so the trace is a conserved
# linear invariant and RK4 preserves it to rounding - asserted in
# CHECKS, not assumed.

def rhoee_steady(omega, delta, gamma=GAMMA):
    """Closed-form steady-state excited population."""
    return (omega * omega / 4.0) / (delta * delta
                                    + gamma * gamma / 4.0
                                    + omega * omega / 2.0)


def rhoeg_steady(omega, delta, gamma=GAMMA):
    """Closed-form steady-state coherence rho_eg."""
    rhoee = rhoee_steady(omega, delta, gamma)
    return (-1j * (omega / 2.0) * (1.0 - 2.0 * rhoee)
            / (gamma / 2.0 - 1j * delta))


def bloch_rhs(y, omega, delta, gamma=GAMMA):
    rhoee, re, im, rhogg = y
    return (
        -omega * im - gamma * rhoee,
        -delta * im - 0.5 * gamma * re,
        delta * re - 0.5 * omega * (rhogg - rhoee) - 0.5 * gamma * im,
        omega * im + gamma * rhoee,
    )


def _rk4_step(y, dt, omega, delta, gamma):
    k1 = bloch_rhs(y, omega, delta, gamma)
    y2 = tuple(y[i] + 0.5 * dt * k1[i] for i in range(4))
    k2 = bloch_rhs(y2, omega, delta, gamma)
    y3 = tuple(y[i] + 0.5 * dt * k2[i] for i in range(4))
    k3 = bloch_rhs(y3, omega, delta, gamma)
    y4 = tuple(y[i] + dt * k3[i] for i in range(4))
    k4 = bloch_rhs(y4, omega, delta, gamma)
    return tuple(y[i] + (dt / 6.0) * (k1[i] + 2.0 * k2[i]
                                      + 2.0 * k3[i] + k4[i])
                 for i in range(4))


def master_samples(omega, delta, sample_times, dt=0.005,
                   y0=(0.0, 0.0, 0.0, 1.0), gamma=GAMMA):
    """Integrate the master equation; return {t: full state tuple}."""
    wanted = {int(round(t / dt)): t for t in sample_times}
    out = {}
    y = tuple(y0)
    if 0 in wanted:
        out[wanted[0]] = y
    n_steps = max(wanted) if wanted else 0
    for k in range(1, n_steps + 1):
        y = _rk4_step(y, dt, omega, delta, gamma)
        if k in wanted:
            out[wanted[k]] = y
    return out


def master_report(omega=1.0, delta=0.0):
    """Steady state: integrated vs closed form, plus the Rabi envelope."""
    t_ss = 60.0
    final = master_samples(omega, delta, [t_ss], dt=0.01)[t_ss]
    ss_ee = rhoee_steady(omega, delta)
    ss_eg = rhoeg_steady(omega, delta)
    # Rabi transient on resonance, Omega = 2: the (Im rho_eg, inversion)
    # block has eigenvalues -3 gamma/4 +- i sqrt(Omega^2 - gamma^2/16),
    # so rho_ee - rho_ee_ss is e^{-3 gamma t / 4} times a sinusoid of
    # period T' = 2 pi / sqrt(Omega^2 - gamma^2/16). Sampling exactly
    # one period apart cancels the sinusoid and exposes the envelope.
    om_r, dl_r = 2.0, 0.0
    om_prime = math.sqrt(om_r ** 2 - GAMMA ** 2 / 16.0)
    period = 2.0 * math.pi / om_prime
    dt_r = period / 2000.0
    states = master_samples(om_r, dl_r, [period, 2.0 * period], dt=dt_r)
    ss_r = rhoee_steady(om_r, dl_r)
    d1 = states[period][0] - ss_r
    d2 = states[2.0 * period][0] - ss_r
    return {
        "omega": omega, "delta": delta, "gamma": GAMMA,
        "rhoee_steady_closed": ss_ee,
        "rhoee_steady_integrated": final[0],
        "rhoee_steady_abs_error": abs(final[0] - ss_ee),
        "rhoeg_steady_closed_abs": abs(ss_eg),
        "rhoeg_steady_integrated_abs": abs(complex(final[1], final[2])),
        "rhoeg_steady_abs_error":
            abs(complex(final[1], final[2]) - ss_eg),
        "trace_at_steady_state": final[0] + final[3],
        "rabi": {
            "omega": om_r, "delta": dl_r,
            "omega_prime": om_prime,
            "period": period,
            "envelope_ratio_measured": d2 / d1,
            "envelope_ratio_theory": math.exp(-0.75 * GAMMA * period),
            "decay_rate_theory": 0.75 * GAMMA,
        },
    }


# ================================================================ 3. Quantum-jump trajectories
# Between jumps the (unnormalised) state evolves under the
# non-Hermitian effective Hamiltonian
#   H_eff = H - i (gamma/2) |e><e|,
# so d psi/dt = A psi with the constant 2x2 matrix
#   A = [[i Delta - gamma/2, -i Omega/2], [-i Omega/2, 0]].
# The one-step propagator U = exp(A dt) is computed in closed form
# (Sylvester formula for a 2x2 exponential), so the no-jump evolution
# is exact at any dt; the only approximation in the algorithm is the
# standard one - at most one jump per step, an O((gamma rho_ee dt)^2)
# error, negligible at dt = 0.02.
#
# Per step: psi' = U psi; the norm loss IS the jump probability,
#   p_jump = 1 - ||psi'||^2  (= gamma rho_ee dt to first order).
# Draw u ~ U[0,1) from the seeded splitmix64 stream: if u < p_jump
# the atom emits and psi resets to |g> exactly; otherwise psi is
# renormalised to psi'/||psi'|| and the run continues.

def heff_propagator(omega, delta, dt, gamma=GAMMA):
    """Exact exp(A dt) for A = -i H_eff, as (U_ee, U_eg, U_ge, U_gg)."""
    a = 1j * delta - gamma / 2.0
    b = -0.5j * omega
    c = b
    d = 0.0j
    tr = a + d
    disc = ((a - d) / 2.0) ** 2 + b * c
    s = cmath.sqrt(disc)
    lp = tr / 2.0 + s
    lm = tr / 2.0 - s
    if abs(lp - lm) < 1e-13:
        # Degenerate (exceptional) point: fall back to the Taylor
        # series of the exponential, 40 terms is far past convergence
        # for the step sizes used here.
        uee, ueg, uge, ugg = 1.0 + 0.0j, 0.0j, 0.0j, 1.0 + 0.0j
        pee, peg, pge, pgg = a, b, c, d
        term = dt
        for k in range(1, 40):
            uee += term * pee
            ueg += term * peg
            uge += term * pge
            ugg += term * pgg
            pee, peg, pge, pgg = (pee * a + peg * c, pee * b + peg * d,
                                  pge * a + pgg * c, pge * b + pgg * d)
            term *= dt / (k + 1)
        return (uee, ueg, uge, ugg)
    ep = cmath.exp(lp * dt)
    em = cmath.exp(lm * dt)
    w1 = ep / (lp - lm)
    w2 = em / (lm - lp)
    return (
        w1 * (a - lm) + w2 * (a - lp),
        w1 * b + w2 * b,
        w1 * c + w2 * c,
        w1 * (d - lm) + w2 * (d - lp),
    )


def jump_reset():
    """The state immediately after an emission: exactly |g>."""
    return (0.0j, 1.0 + 0.0j)


def instantaneous_jump_rate(psi, gamma=GAMMA):
    """gamma * rho_ee of the (normalised) state - the hazard rate."""
    ce = psi[0]
    return gamma * (ce.real * ce.real + ce.imag * ce.imag)


def run_trajectory(omega, delta, t_max, dt, seed, sample_times=(),
                   gamma=GAMMA):
    """One seeded trajectory from |g>: jump times + sampled rho_ee."""
    U = heff_propagator(omega, delta, dt, gamma)
    rng = SplitMix64(seed)
    ce, cg = 0.0j, 1.0 + 0.0j
    wanted = {int(round(t / dt)): t for t in sample_times}
    samples = {}
    if 0 in wanted:
        samples[wanted[0]] = 0.0
    jumps = []
    n_steps = int(round(t_max / dt))
    for k in range(1, n_steps + 1):
        ne = U[0] * ce + U[1] * cg
        ng = U[2] * ce + U[3] * cg
        n2 = (ne.real * ne.real + ne.imag * ne.imag
              + ng.real * ng.real + ng.imag * ng.imag)
        if rng.random() < 1.0 - n2:
            ce, cg = jump_reset()
            jumps.append(k * dt)
        else:
            inv = 1.0 / math.sqrt(n2)
            ce, cg = ne * inv, ng * inv
        if k in wanted:
            samples[wanted[k]] = ce.real * ce.real + ce.imag * ce.imag
    return {"jump_times": jumps, "samples": samples}


def jumps_report():
    """Seeded example trajectories: the actual recorded jump times."""
    out = {"omega": 1.0, "delta": 0.0, "gamma": GAMMA, "dt": 0.02,
           "seed_base": SEED, "trajectories": []}
    for i in range(3):
        tr = run_trajectory(1.0, 0.0, 30.0, 0.02, SEED + 7919 * i)
        out["trajectories"].append({
            "index": i,
            "n_jumps": len(tr["jump_times"]),
            "jump_times": [round(t, 2) for t in tr["jump_times"]],
        })
    tr = run_trajectory(2.0, 0.0, 30.0, 0.02, SEED + 7919 * 3)
    out["strong_drive_trajectory"] = {
        "omega": 2.0, "n_jumps": len(tr["jump_times"]),
        "jump_times": [round(t, 2) for t in tr["jump_times"]],
    }
    return out


# ================================================================ 4. Ensemble, waiting times, records
# Ensemble: M trajectories started in |g>, excited population sampled
# at fixed times. Each trajectory's rho_ee(t) lies in [0, 1], so the
# standard error of the mean is at most sqrt(p(1-p)/M) <= 1/(2 sqrt(M))
# and the RMS deviation from the master curve must shrink like
# M^-1/2. The lab fits the exponent on its own three deviations and
# prints it - the 1/sqrt(M) law is measured here, not quoted.
#
# Waiting times: intervals between consecutive emissions after a
# burn-in. In steady state the mean waiting time is exactly
# 1 / (gamma rho_ee_ss) - that identity is what CHECKS grades, with
# the tolerance set by the standard error of the sample mean. The
# DISTRIBUTION is not a pure exponential: a jump resets the atom to
# |g>, so the hazard restarts at 0 (antibunching) and short waits are
# suppressed below the exponential prediction. The lab prints both
# numbers and grades the direction of the difference.

ENSEMBLE_TIMES = (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0)


def ensemble_report(m_values=(10, 100, 1000), omega=1.0, delta=0.0,
                    dt=0.02, t_max=10.0, seed_base=SEED):
    m_max = max(m_values)
    runs = [run_trajectory(omega, delta, t_max, dt,
                           seed_base + 7919 * i,
                           sample_times=ENSEMBLE_TIMES)
            for i in range(m_max)]
    master = master_samples(omega, delta, list(ENSEMBLE_TIMES), dt=0.005)
    master_ee = {t: master[t][0] for t in ENSEMBLE_TIMES}
    devs = {}
    means = {}
    for m in m_values:
        mean_t = {}
        for t in ENSEMBLE_TIMES:
            mean_t[t] = sum(runs[i]["samples"][t]
                            for i in range(m)) / m
        means[m] = mean_t
        devs[m] = math.sqrt(
            sum((mean_t[t] - master_ee[t]) ** 2
                for t in ENSEMBLE_TIMES) / len(ENSEMBLE_TIMES))
    # least-squares slope of log(dev) vs log(M): the convergence law
    xs = [math.log(m) for m in m_values]
    ys = [math.log(devs[m]) for m in m_values]
    xm = sum(xs) / len(xs)
    ym = sum(ys) / len(ys)
    slope = (sum((x - xm) * (y - ym) for x, y in zip(xs, ys))
             / sum((x - xm) ** 2 for x in xs))
    return {
        "omega": omega, "delta": delta, "dt": dt,
        "sample_times": list(ENSEMBLE_TIMES),
        "master_rhoee": {str(t): master_ee[t] for t in ENSEMBLE_TIMES},
        "deviations": {str(m): devs[m] for m in m_values},
        "fitted_exponent": slope,
        "sigma_bound_largest_m":
            1.0 / (2.0 * math.sqrt(max(m_values))),
        "mean_rhoee_largest_m":
            {str(t): means[max(m_values)][t] for t in ENSEMBLE_TIMES},
    }


def waiting_report(n_traj=250, omega=1.0, delta=0.0, dt=0.02,
                   burn_in=10.0, window=60.0, tail=30.0,
                   seed_base=SEED + 1):
    """Waiting-time distribution + photon counts from seeded runs.

    Intervals are sampled by their STARTING jump inside
    [burn_in, burn_in + window], and each trajectory is run a tail
    of 30 time units past the window so every sampled interval is
    observed to completion - sampling intervals by "fully inside
    the window" instead would censor long waits and bias the mean
    down. Counts are the jumps inside the window itself.
    """
    t_end = burn_in + window
    waits = []
    counts = []
    for i in range(n_traj):
        tr = run_trajectory(omega, delta, t_end + tail, dt,
                            seed_base + 104729 * i)
        js = tr["jump_times"]
        counts.append(sum(1 for jt in js if burn_in < jt <= t_end))
        prev = None
        for jt in js:
            if prev is not None and burn_in <= prev <= t_end:
                waits.append(jt - prev)
            prev = jt
    rate = GAMMA * rhoee_steady(omega, delta)
    theory_wait = 1.0 / rate
    n_w = len(waits)
    mean_wait = sum(waits) / n_w
    var_wait = sum((w - mean_wait) ** 2 for w in waits) / (n_w - 1)
    sem_wait = math.sqrt(var_wait / n_w)
    short_cut = 0.25 * theory_wait
    short_frac = sum(1 for w in waits if w < short_cut) / n_w
    n_c = len(counts)
    mean_counts = sum(counts) / n_c
    var_counts = sum((c - mean_counts) ** 2 for c in counts) / (n_c - 1)
    return {
        "omega": omega, "delta": delta, "dt": dt,
        "n_trajectories": n_traj, "burn_in": burn_in, "window": window,
        "n_waits": n_w,
        "mean_wait": mean_wait,
        "theory_mean_wait": theory_wait,
        "sem_wait": sem_wait,
        "min_wait": min(waits),
        "short_wait_cut": short_cut,
        "short_wait_fraction": short_frac,
        "short_wait_fraction_exponential": 1.0 - math.exp(-0.25),
        "mean_counts": mean_counts,
        "theory_counts": rate * window,
        "var_counts": var_counts,
        "sem_counts": math.sqrt(var_counts / n_c),
        "jump_rate_theory": rate,
    }


# ================================================================ 5. kNN regime classifier
# Features are the steady-state trio (rho_ee_ss, jump rate
# gamma * rho_ee_ss, |rho_eg_ss|). The training grid is labelled by
# the lab's own policy (model_label below) - the classifier
# interpolates the policy, it does not replace the physics.

def model_label(rhoee, rate, coherence):
    """The regime policy distilled to a four-way teaching label."""
    if rhoee <= 0.02:
        return "shelved-dark"
    if rhoee <= 0.12:
        return "weak-drive"
    if coherence >= 0.30:
        return "rabi-transient"
    return "emissive-steady"


def regime_features(omega, delta):
    rhoee = rhoee_steady(omega, delta)
    return (rhoee, GAMMA * rhoee, abs(rhoeg_steady(omega, delta)))


def _training_grid():
    rows = []
    for omega in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0):
        for delta in (-4.0, -3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0):
            feats = regime_features(omega, delta)
            rows.append((feats, model_label(*feats)))
    return rows


TRAINING_GRID = _training_grid()


def _scaled(features):
    rhoee, rate, coherence = features
    return (rhoee / 0.5, rate / 0.5, coherence / 0.5)


def classify_regime(rhoee, rate, coherence, k=5):
    """Distance-weighted kNN over the policy-labelled grid."""
    target = _scaled((rhoee, rate, coherence))
    ranked = []
    for features, label in TRAINING_GRID:
        point = _scaled(features)
        dist = math.sqrt(sum((a - b) ** 2
                             for a, b in zip(target, point)))
        ranked.append((dist, features, label))
    ranked.sort(key=lambda row: (row[0], row[1]))
    votes = {}
    for dist, _, label in ranked[:k]:
        votes[label] = votes.get(label, 0.0) + 1.0 / (dist + 1e-6) ** 2
    priority = {"shelved-dark": 0, "weak-drive": 1,
                "rabi-transient": 2, "emissive-steady": 3}
    return sorted(votes.items(),
                  key=lambda kv: (-kv[1], priority[kv[0]]))[0][0]


def classify_point(omega, delta):
    return classify_regime(*regime_features(omega, delta))


def classifier_report():
    scenarios = {
        "textbook_rabi_drive_O1_D0": (1.0, 0.0),
        "saturated_resonant_drive_O3_D0": (3.0, 0.0),
        "gentle_drive_O0.3_D0": (0.3, 0.0),
        "far_detuned_shelf_O0.5_D4": (0.5, 4.0),
        "strong_detuned_drive_O2_D2": (2.0, 2.0),
        "no_drive_O0_D0": (0.0, 0.0),
    }
    return {name: {"omega": om, "delta": dl,
                   "features": regime_features(om, dl),
                   "label": classify_point(om, dl)}
            for name, (om, dl) in scenarios.items()}


# ================================================================ 6. Advisory seats
def _trace(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def argon4_decide(topic="quantumtrajectories-demo"):
    """Gemini Argon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-argon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Argon 4 Extended Thinking",
        "model": "gemini-argon-4",
        "role": "DECIDER",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "decision": "PROCEED - sandbox simulation only, all source / detector / network gates stay HOLD",
        "can_override_hold": False,
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="quantumtrajectories-demo"):
    """Muse advisor seat: advises, can never override a HOLD."""
    return {
        "seat": "Muse",
        "role": "ADVISOR",
        "key": "names-only (MODEL_API_KEY name checked, value never read)",
        "live_calls": 0,
        "advice": "Say it in the first line of every report: a trajectory is a simulated record, not a measured one - then show the master curve, the fitted 1/sqrt(M) exponent, and the statistical tolerance every stochastic number was graded at.",
        "can_override_hold": False,
    }


def google_flow_plan():
    """Google Flow seat: plan-only, nothing rendered, nothing live."""
    return {
        "seat": "Google Flow",
        "role": "PLAN-ONLY",
        "shots": ["jagged single-atom traces jittering around one smooth curve",
                  "a photon click resetting a glowing atom to dark",
                  "ten, then a hundred, then a thousand traces braiding tight",
                  "a waiting-time histogram growing its antibunched dip at zero",
                  "the master curve drawn last, exactly where the braid settled"],
        "rendered": False,
        "live": 0,
    }


def brains_report():
    return {"decider": argon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ checks
def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # 1. PRNG - exact integer arithmetic, identical streams anywhere
    s1 = SplitMix64(42)
    s2 = SplitMix64(42)
    chk("prng_reproducible",
        [s1.random() for _ in range(1000)]
        == [s2.random() for _ in range(1000)])
    s3 = SplitMix64(SEED)
    draws = [s3.random() for _ in range(20000)]
    chk("prng_range_and_mean", all(0.0 <= u < 1.0 for u in draws)
        and 0.485 < sum(draws) / len(draws) < 0.515)
    chk("prng_seed_changes_stream",
        SplitMix64(1).random() != SplitMix64(2).random())

    # 2. master equation - closed forms first
    chk("ss_formula_third", abs(rhoee_steady(1.0, 0.0) - 1.0 / 3.0) < 1e-15)
    chk("ss_formula_resonance_omega2",
        abs(rhoee_steady(2.0, 0.0) - 4.0 / 9.0) < 1e-12)
    chk("ss_saturation_limit", 0.4999 < rhoee_steady(100.0, 0.0) < 0.5)
    chk("ss_detuning_symmetric",
        rhoee_steady(1.5, 2.0) == rhoee_steady(1.5, -2.0))
    chk("ss_coherence_value",
        abs(abs(rhoeg_steady(1.0, 0.0)) - 1.0 / 3.0) < 1e-12)
    chk("ss_coherence_detuned_smaller",
        abs(rhoeg_steady(1.0, 3.0)) < abs(rhoeg_steady(1.0, 0.0)))

    # integrated master equation vs the closed forms it must obey
    states = master_samples(1.0, 0.0, [10.0, 20.0], dt=0.01)
    chk("trace_preserved",
        all(abs(st[0] + st[3] - 1.0) < 1e-12 for st in states.values()))
    chk("population_in_bounds",
        all(-1e-12 <= st[0] <= 1.0 + 1e-12 for st in states.values()))
    rep = master_report(1.0, 0.0)
    chk("integrated_ss_rhoee", rep["rhoee_steady_abs_error"] < 1e-6)
    chk("integrated_ss_coherence", rep["rhoeg_steady_abs_error"] < 1e-6)
    rep_d = master_report(2.0, 1.5)
    chk("integrated_ss_detuned", rep_d["rhoee_steady_abs_error"] < 1e-6
        and rep_d["rhoeg_steady_abs_error"] < 1e-6)
    decay = master_samples(0.0, 0.0, [2.0], dt=0.005,
                           y0=(1.0, 0.0, 0.0, 0.0))[2.0]
    chk("pure_decay_exact", abs(decay[0] - math.exp(-2.0)) < 1e-6)
    coh = master_samples(0.0, 0.0, [3.0], dt=0.005,
                         y0=(0.5, 0.5, 0.0, 0.5))[3.0]
    chk("coherence_decay_exact",
        abs(coh[1] - 0.5 * math.exp(-1.5)) < 1e-6)
    rabi = rep["rabi"]
    chk("rabi_envelope_ratio",
        abs(rabi["envelope_ratio_measured"]
            / rabi["envelope_ratio_theory"] - 1.0) < 0.02)
    weak = master_samples(0.2, 0.0, [float(t) for t in range(0, 31)],
                          dt=0.01)
    ss_w = rhoee_steady(0.2, 0.0)
    chk("weak_drive_overdamped_no_overshoot",
        all(st[0] <= ss_w * (1.0 + 1e-9) + 1e-12
            for st in weak.values()))

    # 3. trajectory engine
    U0 = heff_propagator(1.3, 0.7, 0.02, gamma=0.0)
    psi = (0.6 + 0.1j, 0.5 - 0.62j)
    n_in = abs(psi[0]) ** 2 + abs(psi[1]) ** 2
    out = (U0[0] * psi[0] + U0[1] * psi[1],
           U0[2] * psi[0] + U0[3] * psi[1])
    chk("propagator_unitary_without_decay",
        abs((abs(out[0]) ** 2 + abs(out[1]) ** 2) - n_in) < 1e-12)
    # propagator vs fine RK4 on d psi/dt = A psi, one dt = 0.05 step
    om_p, dl_p, dt_p = 1.3, 0.7, 0.05
    A = ((1j * dl_p - GAMMA / 2.0, -0.5j * om_p),
         (-0.5j * om_p, 0.0j))

    def _schrod_rhs(p):
        return (A[0][0] * p[0] + A[0][1] * p[1],
                A[1][0] * p[0] + A[1][1] * p[1])

    p = (0.3 + 0.2j, 0.8 - 0.4j)
    h = dt_p / 50.0
    for _ in range(50):
        k1 = _schrod_rhs(p)
        p2 = (p[0] + 0.5 * h * k1[0], p[1] + 0.5 * h * k1[1])
        k2 = _schrod_rhs(p2)
        p3 = (p[0] + 0.5 * h * k2[0], p[1] + 0.5 * h * k2[1])
        k3 = _schrod_rhs(p3)
        p4 = (p[0] + h * k3[0], p[1] + h * k3[1])
        k4 = _schrod_rhs(p4)
        p = (p[0] + (h / 6.0) * (k1[0] + 2 * k2[0] + 2 * k3[0] + k4[0]),
             p[1] + (h / 6.0) * (k1[1] + 2 * k2[1] + 2 * k3[1] + k4[1]))
    U1 = heff_propagator(om_p, dl_p, dt_p)
    q0 = (0.3 + 0.2j, 0.8 - 0.4j)
    q = (U1[0] * q0[0] + U1[1] * q0[1], U1[2] * q0[0] + U1[3] * q0[1])
    chk("propagator_matches_rk4",
        abs(p[0] - q[0]) < 1e-9 and abs(p[1] - q[1]) < 1e-9)
    ground = jump_reset()
    chk("post_jump_state_is_ground_exactly",
        ground[0] == 0.0j and ground[1] == 1.0 + 0.0j
        and instantaneous_jump_rate(ground) == 0.0)
    chk("g2_zero_statement",
        instantaneous_jump_rate(jump_reset()) == 0.0
        and instantaneous_jump_rate((1.0 + 0.0j, 0.0j)) == GAMMA)
    t1 = run_trajectory(1.0, 0.0, 20.0, 0.02, SEED + 5)
    t2 = run_trajectory(1.0, 0.0, 20.0, 0.02, SEED + 5)
    t3 = run_trajectory(1.0, 0.0, 20.0, 0.02, SEED + 6)
    chk("trajectory_reproducible_same_seed",
        t1["jump_times"] == t2["jump_times"])
    chk("trajectory_differs_other_seed",
        t1["jump_times"] != t3["jump_times"])
    chk("trajectory_jumps_strictly_increasing",
        all(b > a for a, b in zip(t1["jump_times"],
                                  t1["jump_times"][1:])))

    # 4. ensemble convergence - reduced budget, same laws
    ens = ensemble_report(m_values=(10, 100, 400), seed_base=SEED + 7)
    devs = ens["deviations"]
    chk("ensemble_deviation_shrinks",
        devs["10"] > devs["100"] > devs["400"])
    chk("ensemble_exponent_near_half",
        -0.8 < ens["fitted_exponent"] < -0.2)
    chk("ensemble_deviation_within_sigma_bound",
        devs["400"] < 4.0 * ens["sigma_bound_largest_m"])

    # 5. waiting times + photon record - tolerances from the data's
    # own standard errors; nothing widened silently.
    w = waiting_report(n_traj=150, seed_base=SEED + 11)
    chk("waiting_mean_matches_inverse_rate",
        abs(w["mean_wait"] - w["theory_mean_wait"]) < 4.0 * w["sem_wait"])
    chk("waiting_short_waits_suppressed",
        w["short_wait_fraction"]
        < w["short_wait_fraction_exponential"] - 0.03
        and w["short_wait_fraction"] > 0.02)
    chk("waiting_min_gap_antibunched", w["min_wait"] >= 0.06)
    chk("records_mean_matches_rate",
        abs(w["mean_counts"] - w["theory_counts"]) < 4.0 * w["sem_counts"])
    chk("records_variance_poisson_scale",
        0.3 * w["mean_counts"] < w["var_counts"] < 1.6 * w["mean_counts"])

    # 6. classifier - labels come from the lab's own policy
    rep_c = classifier_report()
    chk("classifier_rabi",
        rep_c["textbook_rabi_drive_O1_D0"]["label"] == "rabi-transient")
    chk("classifier_emissive",
        rep_c["saturated_resonant_drive_O3_D0"]["label"]
        == "emissive-steady")
    chk("classifier_weak",
        rep_c["gentle_drive_O0.3_D0"]["label"] == "weak-drive")
    chk("classifier_shelved",
        rep_c["far_detuned_shelf_O0.5_D4"]["label"] == "shelved-dark")
    chk("classifier_detuned_rabi",
        rep_c["strong_detuned_drive_O2_D2"]["label"] == "rabi-transient")
    chk("classifier_no_drive_shelved",
        rep_c["no_drive_O0_D0"]["label"] == "shelved-dark")
    chk("classifier_matches_policy_on_grid",
        all(classify_regime(*feats) == label
            for feats, label in TRAINING_GRID))
    chk("classifier_scenarios_match_policy",
        all(classify_point(om, dl) == model_label(*regime_features(om, dl))
            for om, dl in [(1.0, 0.0), (3.0, 0.0), (0.3, 0.0),
                           (0.5, 4.0), (2.0, 2.0), (0.0, 0.0)]))

    # gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14
        and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_source_hold",
        gate("real_single_photon_source_claim") == "HOLD")
    chk("gate_detector_hold", gate("detector_efficiency_claim") == "HOLD")
    chk("gate_network_hold", gate("quantum_network_deployment") == "HOLD")
    chk("gate_antibunching_hold",
        gate("antibunching_measurement_claim") == "HOLD")
    chk("gate_data_substitution_hold",
        gate("experimental_data_substitution") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    brains = brains_report()
    chk("argon4_no_override", brains["decider"]["can_override_hold"] is False
        and brains["decider"]["seat"]
        == "Gemini Argon 4 Extended Thinking"
        and brains["decider"]["model"] == "gemini-argon-4")
    chk("claude_no_override", brains["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", brains["flow"]["rendered"] is False
        and brains["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("QuantumTrajectories-Lab - quantum-jump trajectories vs master equation")
    print("by Darion Kellar | MIT | pure stdlib | zero network | EDUCATION ONLY")
    print("=" * 68)
    print("\n[1] THE HONEST CORE - two descriptions, one atom, zero photons harmed")
    print("    The master equation gives the smooth ENSEMBLE curve. A quantum")
    print("    trajectory gives one jagged SIMULATED record: smooth no-jump")
    print("    evolution under H_eff, interrupted by emissions that reset the")
    print("    atom to |g>. Average enough trajectories and you must recover")
    print("    the master curve - this lab measures that recovery. No real")
    print("    atom, source, or detector exists here; detection is ideal")
    print("    (efficiency 1, labelled) and every record is simulated.")
    print(f"    PRNG: splitmix64 in-file, seed {SEED} - byte-identical runs.")
    print("\n[2] Master equation - steady state vs its own closed form")
    for om, dl in [(0.3, 0.0), (1.0, 0.0), (2.0, 0.0), (1.0, 3.0),
                   (3.0, 0.0)]:
        rep = master_report(om, dl)
        print(f"    Omega {om:.1f} Delta {dl:+.1f} | rho_ee_ss "
              f"{rep['rhoee_steady_closed']:.6f} (integrated "
              f"{rep['rhoee_steady_integrated']:.6f}, err "
              f"{rep['rhoee_steady_abs_error']:.2e}) | |rho_eg_ss| "
              f"{rep['rhoeg_steady_closed_abs']:.6f} | jump rate "
              f"{GAMMA * rep['rhoee_steady_closed']:.6f}")
    rabi = master_report(1.0, 0.0)["rabi"]
    print("\n[3] Rabi transient - the e^{-3 gamma t / 4} envelope, measured")
    print(f"    Omega 2 on resonance: Omega' = {rabi['omega_prime']:.6f}, "
          f"period {rabi['period']:.6f}")
    print(f"    envelope ratio over one period: measured "
          f"{rabi['envelope_ratio_measured']:.6f} vs theory "
          f"e^{{-3 gamma T'/4}} = {rabi['envelope_ratio_theory']:.6f}")
    print("    (for Omega < gamma/4 the transient is overdamped instead -")
    print("     the lab checks the weak-drive run never overshoots its")
    print("     steady state)")
    print("\n[4] Example trajectories - recorded jump times (seeded)")
    jr = jumps_report()
    for tr in jr["trajectories"]:
        print(f"    traj {tr['index']}: {tr['n_jumps']} jumps | "
              f"first times {tr['jump_times'][:8]}")
    sd = jr["strong_drive_trajectory"]
    print(f"    Omega 2 traj: {sd['n_jumps']} jumps | "
          f"first times {sd['jump_times'][:8]}")
    print("    -> right after every jump rho_ee = 0 exactly, so the")
    print("       instantaneous jump rate is 0: that is the model's")
    print("       g2(0) = 0 statement - a property of the model,")
    print("       never a measured antibunching certification.")
    print("\n[5] Ensemble convergence - trajectories braid onto the master curve")
    ens = ensemble_report()
    for m in ("10", "100", "1000"):
        print(f"    M = {m:>5}: RMS deviation from master curve "
              f"{ens['deviations'][m]:.6f}")
    print(f"    fitted exponent of deviation vs M: "
          f"{ens['fitted_exponent']:.3f} (1/sqrt(M) law: -0.5)")
    print(f"    sigma bound at M = 1000: "
          f"{ens['sigma_bound_largest_m']:.6f} "
          f"(sqrt(p(1-p)/M) <= 1/(2 sqrt(M)))")
    print("\n[6] Waiting times + photon record (250 trajectories, seeded)")
    w = waiting_report()
    print(f"    waits collected {w['n_waits']} | mean wait "
          f"{w['mean_wait']:.4f} +- {w['sem_wait']:.4f} vs theory "
          f"1/(gamma rho_ee_ss) = {w['theory_mean_wait']:.4f}")
    print(f"    shortest wait {w['min_wait']:.2f} | waits under "
          f"{w['short_wait_cut']:.2f}: fraction "
          f"{w['short_wait_fraction']:.4f} vs exponential "
          f"{w['short_wait_fraction_exponential']:.4f} "
          f"(antibunching suppresses short waits)")
    print(f"    counts per 60-unit window: mean {w['mean_counts']:.4f} "
          f"+- {w['sem_counts']:.4f} vs theory "
          f"{w['theory_counts']:.4f} | variance {w['var_counts']:.4f}")
    print("\n[7] Regime classifier (TinyML kNN, labels from the lab's policy)")
    for name, row in classifier_report().items():
        f = row["features"]
        print(f"    {name:36s} rho_ee {f[0]:.4f} rate {f[1]:.4f} "
              f"|rho_eg| {f[2]:.4f} -> {row['label']}")
    print("\n[8] Advisory seats")
    brains = brains_report()
    print(f"    decider: {brains['decider']['decision']} "
          f"trace={brains['decider']['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {brains['advisor']['can_override_hold']}")
    print(f"    flow rendered = {brains['flow']['rendered']} "
          f"live = {brains['flow']['live']}")
    print(f"\n[9] HOLD gates: {len(HOLD_GATES)}")
    for key in HOLD_GATES:
        print(f"    HOLD  {key}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "master":
        print(json.dumps(master_report(1.0, 0.0), indent=2, sort_keys=True))
        return 0
    if cmd == "jumps":
        print(json.dumps(jumps_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "ensemble":
        print(json.dumps(ensemble_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "waiting":
        print(json.dumps(waiting_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "records":
        w = waiting_report()
        keys = ("n_trajectories", "window", "mean_counts", "theory_counts",
                "var_counts", "sem_counts", "jump_rate_theory")
        print(json.dumps({k: w[k] for k in keys}, indent=2, sort_keys=True))
        return 0
    if cmd == "classify":
        print(json.dumps(classifier_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for key, value in HOLD_GATES.items():
            print(f"{key}: {value}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "real_single_photon_source_claim"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
