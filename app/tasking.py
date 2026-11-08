"""Lecture seule des plans Markdown et de l'état Git local."""
from pathlib import Path
import re
import subprocess
import unicodedata

ROOT = Path(__file__).resolve().parent.parent


def status_tone(state: str) -> str:
    """Choisir une couleur prudente tout en conservant le libellé documentaire."""
    normalized = ''.join(char for char in unicodedata.normalize('NFKD', state.lower()) if not unicodedata.combining(char))
    if any(word in normalized for word in ('bloque', 'echec')):
        return 'blocked'
    if any(word in normalized for word in ('partiel', 'inachev', 'non livre', 'ouverte', 'ouverts', 'ouvert', 'a completer', 'a requalifier', 'a revalider', 'a reproduire', 'en cours', 'quelques criteres')):
        return 'partial'
    if any(word in normalized for word in ('conditionnel', 'conception', 'experience')):
        return 'conditional'
    if any(word in normalized for word in ('a realiser', 'absent', 'non commence')):
        return 'todo'
    if any(word in normalized for word in ('realise', 'valide', 'teste', 'acquis')):
        return 'done'
    return 'neutral'


def extract_dependencies(lines: list[str]) -> list[dict[str, str]]:
    """Relever les dépendances explicites, sans interpréter les conditions ou plages."""
    dependencies: list[dict[str, str]] = []
    heading = ''
    dependency_column = -1
    task_column = 0
    for line in lines:
        match = re.match(r'^#{2,6}\s+(.+)', line)
        if match:
            heading = match.group(1).strip()
        if line.startswith('|'):
            cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
            normalized = [cell.lower().strip('* ') for cell in cells]
            if 'dépendances' in normalized or 'dépendance' in normalized:
                dependency_column = next(i for i, cell in enumerate(normalized) if cell in ('dépendances', 'dépendance'))
                task_column = next((i for i, cell in enumerate(normalized) if cell in ('lot', 'tâche', 'tache')), 0)
                continue
            if dependency_column >= 0 and len(cells) > max(dependency_column, task_column):
                if re.fullmatch(r'[-: ]+', cells[task_column]):
                    continue
                task, dependency = cells[task_column], cells[dependency_column]
                if re.match(r'^T\d', task) and dependency:
                    dependencies.append({'task': task, 'dependency': dependency, 'source': 'Tableau des dépendances'})
                continue
        else:
            dependency_column = -1
        match = re.match(r'^\*\*Dépendances?\s*:\*\*\s*(.+?)\s*$', line, re.IGNORECASE)
        if match and re.match(r'^T\d', heading):
            dependencies.append({'task': heading, 'dependency': match.group(1), 'source': 'Dépendance indiquée dans la tâche'})
    return dependencies


def consolidated_tables(path: Path) -> dict[str, list[dict[str, str]]]:
    """Lire les deux tableaux de synthèse du suivi consolidé, sans interpréter leurs états."""
    result: dict[str, list[dict[str, str]]] = {'projects': [], 'identification': []}
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return result
    section = ''
    for line in lines:
        if line.startswith('## '):
            if re.match(r'^## 2\.', line):
                section = 'projects'
            elif re.match(r'^## 3\.', line):
                section = 'identification'
            else:
                section = ''
        if not section or not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
        if len(cells) < (4 if section == 'projects' else 3):
            continue
        if cells[0].startswith(('Chantier', 'Lots')) or re.fullmatch(r'[-: ]+', cells[0]):
            continue
        def plain(value: str) -> str:
            value = re.sub(r'\[([^]]+)\]\([^)]+\)', r'\1', value)
            return value.replace('`', '').replace('**', '')
        if section == 'projects':
            row = dict(zip(('name', 'state', 'achievements', 'next'), map(plain, cells[:4])))
            row['tone'] = status_tone(row['state'])
            result[section].append(row)
        else:
            row = dict(zip(('name', 'state', 'next'), map(plain, cells[:3])))
            row['tone'] = status_tone(row['state'])
            result[section].append(row)
    return result


def tasking_data(root: Path = ROOT) -> dict:
    """Construire un instantané sans déduire la validation des cases cochées."""
    documents = []
    for path in sorted(set(root.glob('TASKING_*.md')) | set(root.glob('PLAN_*.md'))):
        try:
            content = path.read_text(encoding='utf-8')
        except OSError:
            continue
        lines = content.splitlines()
        title = next((line.lstrip('# ').strip() for line in lines if line.startswith('# ')), path.stem)
        sections = []
        current = None
        for line in lines:
            heading = re.match(r'^#{2,6}\s+(.+)', line)
            if heading:
                current = {'title': heading.group(1), 'items': []}
                sections.append(current)
            match = re.match(r'^\s*[-*] \[([ xX])\]\s+(.+)', line)
            if match:
                if current is None:
                    current = {'title': 'Tâches', 'items': []}
                    sections.append(current)
                current['items'].append({'done': match.group(1).lower() == 'x', 'text': match.group(2)})
        sections = [section for section in sections if section['items']]
        items = [item for section in sections for item in section['items']]
        documents.append({'name': path.name, 'title': title, 'sections': sections,
                          'dependencies': extract_dependencies(lines),
                          'done': sum(item['done'] for item in items), 'total': len(items)})
    incidents = []
    tracker = root / 'tracker.md'
    try:
        for line in tracker.read_text(encoding='utf-8').splitlines():
            if re.match(r'^\|\s*TRK-\d+\s*\|', line):
                cells = [cell.strip() for cell in line.strip('|').split('|')]
                if len(cells) >= 5:
                    incident = dict(zip(('id', 'priority', 'state', 'scope', 'description'), cells[:5]))
                    incident['tone'] = status_tone(incident['state'])
                    incidents.append(incident)
    except OSError:
        pass
    git = {'available': False, 'branches': [], 'worktrees': [], 'message': ''}
    try:
        def run(*args: str) -> str:
            return subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True,
                                  check=True, timeout=5).stdout
        branches = run('branch', '--format=%(refname:short)|%(objectname:short)|%(HEAD)').splitlines()
        worktree_output = run('worktree', 'list', '--porcelain')
        for branch in branches:
            parts = branch.split('|')
            if len(parts) == 3:
                git['branches'].append({'name': parts[0], 'commit': parts[1], 'current': parts[2] == '*'})
        for block in worktree_output.strip().split('\n\n'):
            fields = dict(line.split(' ', 1) for line in block.splitlines() if ' ' in line)
            if 'worktree' in fields:
                git['worktrees'].append({'path': fields['worktree'], 'branch': fields.get('branch', '').removeprefix('refs/heads/'), 'commit': fields.get('HEAD', '')[:8]})
        git['available'] = True
    except (OSError, subprocess.SubprocessError):
        # L'image Docker ne contient pas Git ; ses métadonnées restent lisibles
        # dans le montage du dépôt, y compris pour les worktrees externes.
        metadata = root / '.git'
        try:
            if not metadata.is_dir():
                raise OSError('Métadonnées Git absentes')
            refs = {}
            packed = metadata / 'packed-refs'
            if packed.exists():
                for line in packed.read_text(encoding='utf-8').splitlines():
                    if line and not line.startswith(('#', '^')):
                        commit, ref = line.split(' ', 1)
                        if ref.startswith('refs/heads/'):
                            refs[ref.removeprefix('refs/heads/')] = commit
            heads = metadata / 'refs' / 'heads'
            if heads.exists():
                for ref in heads.rglob('*'):
                    if ref.is_file():
                        refs[ref.relative_to(heads).as_posix()] = ref.read_text().strip()
            head = (metadata / 'HEAD').read_text().strip()
            current = head.removeprefix('ref: refs/heads/') if head.startswith('ref: refs/heads/') else ''
            git['branches'] = [{'name': name, 'commit': commit[:8], 'current': name == current}
                               for name, commit in sorted(refs.items())]
            git['worktrees'] = [{'path': str(root), 'branch': current, 'commit': refs.get(current, head)[:8]}]
            worktrees = metadata / 'worktrees'
            if worktrees.exists():
                for entry in sorted(worktrees.iterdir()):
                    try:
                        work_head = (entry / 'HEAD').read_text().strip()
                        branch = work_head.removeprefix('ref: refs/heads/') if work_head.startswith('ref: refs/heads/') else ''
                        path = str(Path((entry / 'gitdir').read_text().strip()).parent)
                        git['worktrees'].append({'path': path, 'branch': branch, 'commit': refs.get(branch, work_head)[:8]})
                    except OSError:
                        continue
            git['available'] = True
            git['message'] = 'Lecture des métadonnées Git ; les chemins enregistrés et les worktrees ne sont pas vérifiés depuis ce conteneur.'
        except (OSError, ValueError):
            git['message'] = 'État Git indisponible dans cet environnement : dépôt ou commande Git non accessible.'
    return {'documents': documents, 'incidents': incidents, 'git': git,
            'consolidated': consolidated_tables(root / 'TASKING_PROJET.md'),
            'done': sum(doc['done'] for doc in documents), 'total': sum(doc['total'] for doc in documents)}
