"""Run the full engineering-simulation evaluation and print a report.

Usage: python run_evaluation.py
"""

from eng_sim_evaluator.beam import Beam
from eng_sim_evaluator.benchmark import (
    Requirements,
    compare_solver_designs,
    evaluate_design,
    rank_designs,
)
from eng_sim_evaluator.calibration import (
    calibrate_youngs_modulus,
    calibration_error_pct,
    synthetic_measurements,
)
from eng_sim_evaluator.thermal import WallLayer, composite_heat_flux


def main() -> None:
    print("=== 1. Beam benchmark: candidate designs vs requirements ===")
    req = Requirements(max_tip_deflection=0.02, max_stress=200e6, max_mass=200.0)
    candidates = {
        "slim-50mm": Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=200e9),
        "chunky-100mm": Beam(length=2.0, width=0.1, height=0.10, youngs_modulus=200e9),
        "aluminium-80mm": Beam(
            length=2.0, width=0.1, height=0.08, youngs_modulus=70e9, density=2700.0
        ),
    }
    results = rank_designs(
        [evaluate_design(name, beam, 1000.0, req) for name, beam in candidates.items()]
    )
    for r in results:
        print(r.as_dict())

    print("\n=== 2. Calibration: recover E from synthetic lab measurements ===")
    true_beam = Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=200e9)
    meas = synthetic_measurements(
        true_beam, 1000.0, [0.5, 1.0, 1.5, 2.0], noise_std=1e-6, seed=7
    )
    template = Beam(length=2.0, width=0.1, height=0.05, youngs_modulus=1.0)
    recovered, sse = calibrate_youngs_modulus(
        template, 1000.0, meas, [150e9, 180e9, 200e9, 220e9, 250e9]
    )
    print(f"true E = 200 GPa; recovered E = {recovered / 1e9:.0f} GPa; "
          f"error = {calibration_error_pct(recovered, 200e9):.2f}%; SSE = {sse:.3e}")

    print("\n=== 3. Thermal check: composite wall heat flux ===")
    layers = [WallLayer(0.1, 0.5), WallLayer(0.1, 1.0)]
    print(f"heat flux = {composite_heat_flux(100.0, 20.0, layers):.1f} W/m^2")

    print("\n=== 4. Solver comparison: AI-proposed vs reference deflections ===")
    ref = [0.00120, 0.00240, 0.00310, 0.00405]
    proposed = [0.00125, 0.00238, 0.00320, 0.00400]
    print(compare_solver_designs(proposed, ref, tolerance_m=0.0002))


if __name__ == "__main__":
    main()
