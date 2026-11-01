# cad

Parametrische 3D-Druckteile in Python (manifold3d + trimesh), mit automatischen Checks,
OpenSCAD-Renders und STL/3MF-Export. Dazu ein Claude-Code-Skill, der den Workflow führt.

## Einrichtung

1. [uv](https://docs.astral.sh/uv/) installieren, dann im Repo `uv sync`.
2. OpenSCAD installieren (nur für Renders). `cadlib` sucht es über die Umgebungsvariable
   `OPENSCAD`, dann im `PATH`, dann unter `/Applications/OpenSCAD.app`.
3. Skill für Claude Code verlinken:
   `ln -s "$PWD/skills/cad-print" ~/.claude/skills/cad-print`
4. `NOTES.md` lesen und den eigenen Drucker und das Material eintragen. Die Passungswerte
   dort sind auf einem Bambu Lab P2S mit PETG bestätigt, auf anderen Druckern sind es
   Startwerte.

## Aufbau

- `cadlib.py` - Primitive, gerundete Hüllen, Checks (Netz, Passung, Wandstärke,
  Überhänge, Sperrzonen), Export, Renders, Schnittzeichnungen
- `parts/<name>/<name>.py` - ein Skript pro Teil, Ausgaben in `out/<version>/`
- `parts/cable_clip/` - Referenzteil: Kabelclip für eine Monitorecke
- `NOTES.md` - gesammelte Erfahrungen aus gedruckten Iterationen
- `skills/cad-print/` - der Skill (SKILL.md, Test-Prompts unter `evals/`)

Ein Teil bauen: `uv run python -I parts/cable_clip/cable_clip.py`

## Lizenz

MIT, siehe `LICENSE`.
