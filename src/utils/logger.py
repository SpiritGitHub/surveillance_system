"""
Configuration du logging
"""

import logging
from pathlib import Path
from datetime import datetime


def setup_logging(log_name: str = "yolo"):
    """
    Configure le système de logging
    
    Args:
        log_name: Nom du fichier de log
    
    Returns:
        Path: Chemin du fichier de log
    """
    log_dir = Path("outputs/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = log_dir / f"{log_name}_{timestamp}.log"

    # CORRECTION : Utiliser style='{' pour supporter les accolades
    logging.basicConfig(
        level=logging.INFO,
        format="{asctime} | {levelname} | {name} | {message}",
        style='{',  # <-- CLÉ : utiliser le style avec accolades
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler()
        ],
        force=True
    )

    # Logger initial - Utiliser print() pour éviter problème de formatage
    print("=" * 44)
    print("Logging initialisé")
    print(f"Fichier log : {log_file}")
    print("=" * 44)

    return log_file