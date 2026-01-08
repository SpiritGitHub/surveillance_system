"""
Script pour trouver tous les appels de logging problématiques
"""

import os
from pathlib import Path

def find_logging_issues(directory="src"):
    """Trouve tous les logger.info/debug/warning avec des f-strings ou format()"""
    
    issues = []
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if not file.endswith('.py'):
                continue
            
            filepath = Path(root) / file
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                
                for i, line in enumerate(lines, 1):
                    # Chercher logger.info/debug/warning/error avec f-strings
                    if 'logger.' in line and ('info' in line or 'debug' in line or 'warning' in line or 'error' in line):
                        if 'f"' in line or 'f\'' in line or '.format(' in line:
                            issues.append({
                                'file': str(filepath),
                                'line': i,
                                'content': line.strip()
                            })
            except Exception as e:
                print(f"Erreur lecture {filepath}: {e}")
    
    return issues


def main():
    print("🔍 Recherche des appels de logging problématiques...\n")
    
    issues = find_logging_issues()
    
    if not issues:
        print("✅ Aucun problème trouvé !")
    else:
        print(f"❌ {len(issues)} problème(s) trouvé(s) :\n")
        
        for issue in issues:
            print(f"📁 {issue['file']}")
            print(f"   Ligne {issue['line']}: {issue['content']}")
            print()
    
    print("\n" + "="*70)
    print("💡 SOLUTION:")
    print("="*70)
    print("Option 1: Remplacer logger.info(f'...') par print(f'...')")
    print("Option 2: Utiliser logger.info('...', var1, var2) avec %s")
    print("Option 3: Ajouter style='{' dans logging.basicConfig()")
    print("="*70)


if __name__ == "__main__":
    main()