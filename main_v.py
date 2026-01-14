import sys
from pathlib import Path
import argparse


# Ensure project root is on sys.path (so `import src...` and `import main` work reliably)
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run_full_pipeline(force: bool) -> None:
    """Run the same end-to-end pipeline as `main.py`.

    This includes (when trajectories exist):
    - global matching (Re-ID)
    - events reanalysis if needed
    - event enrichment (global_id + prev/next camera)
    - run report JSON
    - database CSV exports
    """

    from main import main as run_main

    run_main(force_reprocess=force)


def _run_dashboard(data_dir: str = "data") -> None:
    from src.interface.dashboard_v import DashboardV

    print("\n" + "=" * 70)
    print("Lancement du Dashboard V")
    print("=" * 70)
    print("Chargement de l'interface synchronisée...")

    dashboard = DashboardV(data_dir=data_dir)
    dashboard.load_resources()
    dashboard.run()


def main_v(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Surveillance System - Version Avancée (V)")
    parser.add_argument("--force", "-f", action="store_true", help="Forcer le retraitement complet des vidéos")
    parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="Exécuter le pipeline complet mais ne pas lancer le dashboard",
    )
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Lancer seulement le dashboard (sans retraitement, sans matching, sans exports)",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Dossier data/ (défaut: data)",
    )

    args = parser.parse_args(argv)

    print("\n" + "=" * 70)
    print("SURVEILLANCE SYSTEM - VERSION AVANCÉE (V)")
    print("=" * 70)

    if not args.dashboard_only:
        _run_full_pipeline(force=bool(args.force))

    if not args.no_dashboard:
        try:
            _run_dashboard(data_dir=args.data_dir)
        except Exception as e:
            print(f"Erreur Dashboard: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    main_v()
