'''
Docstring for main
'''
from pathlib import Path
import time
import logging
import sys
import argparse

from src.pipeline.process_video import VideoProcessor
from src.pipeline.global_matching import run_global_matching
from src.utils.trajectory_validator import TrajectoryValidator
from src.utils.logger import setup_logging
from src.utils.run_report import write_run_report
from src.utils.event_enricher import enrich_events_with_global_ids
from src.utils.embeddings_exporter import export_embeddings_from_trajectories
from src.zones.intrusion_reanalyzer import reanalyze_intrusions_from_trajectories
from src.database.exporter import export_database


logger = logging.getLogger(__name__)


def _configure_external_loggers(quiet: bool) -> None:
    """Reduce noise from external libs without silencing our own logs."""
    if not quiet:
        return
    for name in [
        "ultralytics",
        "googleapiclient",
        "google_auth_oauthlib",
        "google.auth",
        "urllib3",
    ]:
        try:
            logging.getLogger(name).setLevel(logging.WARNING)
        except Exception:
            pass


def main(force_reprocess: bool = False, log_level: str = "INFO", quiet_external: bool = True):
    """
    Traitement intelligent de toutes les vidéos
    
    Args:
        force_reprocess: Forcer le retraitement même si déjà fait
    """
    # Logging: file + console, configurable via CLI.
    setup_logging(log_name="run")
    try:
        logging.getLogger().setLevel(getattr(logging, str(log_level).upper(), logging.INFO))
    except Exception:
        logging.getLogger().setLevel(logging.INFO)
    _configure_external_loggers(quiet=quiet_external)

    from tqdm import tqdm
    
    # 1. VÉRIFICATION PRÉALABLE
    validator = TrajectoryValidator()
    
    print("\n🔍 Vérification des trajectoires existantes...")
    scan = validator.print_scan_report()
    
    # Run/session artifacts (always created so downstream steps can run end-to-end)
    run_id = time.strftime("%Y%m%d_%H%M%S")
    events_dir = Path("outputs/events")
    reports_dir = Path("outputs/reports")
    events_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)

    events_file = events_dir / f"events_{run_id}.jsonl"
    report_file = reports_dir / f"run_report_{run_id}.json"
    latest_report = reports_dir / "latest.json"

    # Ensure events file exists (exporters/reporting expect a path)
    try:
        events_file.touch(exist_ok=True)
    except Exception:
        logger.warning("Impossible de créer %s", events_file)

    # 2. DÉTERMINER QUOI TRAITER
    if force_reprocess:
        print("\n⚠️  MODE FORCE: Toutes les vidéos seront retraitées")
        video_dir = Path("data/videos")
        candidates = [p for p in video_dir.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"]

        # Dédupliquer par stem (nom sans extension, en minuscules)
        seen_stems = {}
        for p in candidates:
            stem = p.stem.lower()
            if stem not in seen_stems:
                seen_stems[stem] = p

        videos_to_process = sorted(seen_stems.values())
    else:
        videos_to_process = validator.get_videos_to_process()
    
    if not videos_to_process:
        print("\n" + "=" * 70)
        print("🎉 TOUT EST À JOUR !")
        print("=" * 70)
        print("Toutes les vidéos ont déjà été traitées.")
        print("Utilisez --force pour retraiter quand même.")
        print("=" * 70)
        
        # End-to-end mode: even if everything is already processed, we still:
        # - run global matching
        # - enrich events (if any)
        # - generate a report
        # - export database CSVs
        videos_to_process = []
    
    print("\n" + "=" * 70)
    print(f"🎬 {len(videos_to_process)} vidéo(s) à traiter")
    print("=" * 70)
    
    # 3. CONFIRMATION
    if (
        not force_reprocess
        and len(videos_to_process) > 0
        and len(videos_to_process) < scan["summary"]["total"]
    ):
        print(f"\nℹ️  {scan['summary']['complete']} vidéo(s) déjà traitée(s) seront ignorées")
        response = input("\n▶️  Continuer ? (o/n) [o]: ").lower()
        if response and response not in ['o', 'oui', 'y', 'yes']:
            print("Annulé.")
            return
    
    print()
    
    # 4. TRAITEMENT
    success = 0
    errors = 0
    total_time = 0
    per_video_stats = {}
    
    # Reuse a single processor across videos to avoid reloading YOLO/ReID each time.
    processor = VideoProcessor(show_video=False, event_output_file=str(events_file))

    for video_path in tqdm(videos_to_process, desc="Traitement global", unit="vidéo", ncols=100):
        print(f"\n{'='*70}")
        print(f"📹 {video_path.name}")
        print('='*70)
        
        start = time.time()
        
        try:
            stats = processor.process(str(video_path))
            
            elapsed = time.time() - start
            total_time += elapsed
            
            if stats:
                print(f"\n✓ Succès en {elapsed:.1f}s - {stats['unique_persons']} personne(s)")
                per_video_stats[video_path.stem] = stats
                success += 1
            
        except KeyboardInterrupt:
            print("\n⏸️  Interruption utilisateur")
            break
        except Exception as e:
            logger.exception("Erreur traitement vidéo: %s", video_path)
            print(f"\n❌ Erreur: {str(e)[:200]} (détails dans les logs)")
            errors += 1
    
    # 5. RÉSUMÉ FINAL
    print("\n" + "=" * 70)
    print("📊 RÉSUMÉ FINAL")
    print("=" * 70)
    print(f"✅ Succès: {success}/{len(videos_to_process)}")
    print(f"❌ Erreurs: {errors}/{len(videos_to_process)}")
    print(f"⏱️  Temps total: {total_time/60:.1f} min")
    if success > 0:
        print(f"⚡ Temps moyen: {total_time/success:.1f}s par vidéo")
    print(f"📁 Trajectoires: data/trajectories/")
    print("=" * 70)
    
    # 6. VÉRIFICATION FINALE (always)
    print("\n🔍 Vérification finale...")
    final_scan = validator.scan_all_videos()
    print(f"✅ {final_scan['summary']['complete']}/{final_scan['summary']['total']} vidéos complètes")

    trajectories_dir = Path("data/trajectories")
    has_trajectories = trajectories_dir.exists() and any(trajectories_dir.glob("*.json"))
    if not has_trajectories:
        print("\n⚠️  Aucune trajectoire trouvée dans data/trajectories/.")
        print("   Lancez un traitement (--force) pour générer les trajectoires.")

    # 7. GLOBAL MATCHING (always if trajectories exist)
    gm_info = None
    if has_trajectories:
        gm_info = run_global_matching()

    # 7a. EXPORT EMBEDDINGS to data/embeddings (best effort)
    try:
        if has_trajectories:
            emb_info = export_embeddings_from_trajectories(
                trajectories_dir="data/trajectories",
                out_dir="data/embeddings",
                run_id=run_id,
                class_filter="person",
                mode="mean",
                max_embeddings_per_track=5,
            )
        else:
            emb_info = None
    except Exception:
        emb_info = None

    # 7b. ENRICH EVENTS with global_id + prev/next camera (best effort)
    try:
        reanalysis_info = None

        # If zones exist and no events were produced during processing, recreate events from trajectories.
        zones_file = Path("data/zones_interdites.json")
        events_empty = (not events_file.exists()) or (events_file.stat().st_size == 0)
        if has_trajectories and zones_file.exists() and events_empty:
            reanalysis_info = reanalyze_intrusions_from_trajectories(
                trajectories_dir="data/trajectories",
                zones_file=str(zones_file),
                output_events_file=str(events_file),
                class_name="person",
            )

        if has_trajectories:
            enrich_info = enrich_events_with_global_ids(
                events_file,
                trajectories_dir="data/trajectories",
                in_place=True,
            )
        else:
            enrich_info = None
    except Exception:
        enrich_info = None
        reanalysis_info = None

    # 8. RAPPORT JSON (pour examinateur) (always)
    run_info = {
        "run_id": run_id,
        "force_reprocess": bool(force_reprocess),
        "videos_total": len(videos_to_process),
        "videos_success": success,
        "videos_errors": errors,
        "total_time_sec": float(total_time),
        "avg_time_sec": float(total_time / success) if success else None,
        "trajectories_dir": "data/trajectories",
        "events_file": str(events_file),
    }

    report = write_run_report(
        output_path=report_file,
        run_info=run_info,
        per_video_stats=per_video_stats,
        events_path=events_file,
        global_matching_info=gm_info,
        trajectories_dir="data/trajectories",
    )

    if emb_info is not None:
        report["embeddings_export"] = emb_info

    if enrich_info is not None:
        report["events_enrichment"] = enrich_info
    if reanalysis_info is not None:
        report["events_reanalysis"] = reanalysis_info
        try:
            report_file.write_text(
                __import__("json").dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    # 9. EXPORT DATABASE (CSV) for examiners (always; events may be empty)
    try:
        db_info = export_database(
            trajectories_dir="data/trajectories",
            events_jsonl=events_file,
            per_video_stats=per_video_stats,
            run_id=run_id,
            out_dir="database",
        )
    except Exception as e:
        logger.exception("Erreur export database")
        db_info = {"error": str(e)}

    try:
        report["database_export"] = db_info
        report_file.write_text(
            __import__("json").dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass

    # Update latest report pointer
    try:
        latest_report.write_text(report_file.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        pass

    # Print quick intrusion summary
    try:
        ev_total = report.get("events", {}).get("summary", {}).get("total", 0)
        by_type = report.get("events", {}).get("summary", {}).get("by_type", {})
        print("\n" + "=" * 70)
        print("🚨 INTRUSIONS (résumé)")
        print("=" * 70)
        print(f"Events: {ev_total} | Fichier: {events_file}")
        if by_type:
            print(f"Par type: {by_type}")
        print("=" * 70)
    except Exception:
        pass

    print(f"\n📄 Rapport complet: {report_file}")
    if isinstance(db_info, dict) and "error" not in db_info:
        print("📦 Database CSV mis à jour: database/personnes.csv, database/evenements.csv, database/classes.csv")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Surveillance System - Pipeline principal")
    parser.add_argument("--force", "-f", action="store_true", help="Forcer le retraitement des vidéos")
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Niveau de logs (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )
    parser.add_argument(
        "--no-quiet-external",
        action="store_true",
        help="Ne pas réduire les logs des librairies externes",
    )

    args = parser.parse_args()

    try:
        main(
            force_reprocess=bool(args.force),
            log_level=str(args.log_level),
            quiet_external=not bool(args.no_quiet_external),
        )
    except KeyboardInterrupt:
        print("\n\n⏹️  Arrêt demandé")