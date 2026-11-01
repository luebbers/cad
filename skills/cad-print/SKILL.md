---
name: cad-print
description: >
  Konstruiert 3D-druckbare Funktionsteile (Halter, Clips, Adapter, Boxen, Abstandshalter,
  Ersatzteile) als Python-Code mit manifold3d + trimesh im cad-Repo, in dem dieser Skill
  liegt. Prüft sie automatisch (wasserdicht, Passung gegen das Gegenstück, Wandstärke,
  Überhänge in Druckausrichtung, Sperrzonen), rendert Ansichten mit OpenSCAD und exportiert
  STL/3MF für FDM-Drucker. Iteriert versioniert nach Druck-Feedback ("sitzt zu locker",
  "bricht", "scharfkantig"). Verwenden, wenn der Nutzer etwas drucken, konstruieren,
  modellieren oder ein STL/3MF haben will, auch ohne die Wörter CAD oder Skill: "kannst Du
  mir einen Halter für X bauen", "ich brauch einen Clip für ...", "druck mir ...", "mach v3,
  der Clip klemmt zu stark", Fotos mit Maßen eines Gegenstands, an den etwas angebaut
  werden soll.
---

# Druckteile in Python konstruieren

Das Teil entsteht als Python-Skript gegen eine kleine Bibliothek (`cadlib.py`) und wird
nach jeder Änderung automatisch geprüft und gerendert. Der Grund: Ein Druck kostet eine
Stunde und Material, ein Prüflauf 2 s. Fehler sollen im Check auffallen, nicht auf dem
Druckbett. Der Ansatz stammt aus einem Build-Log (BP-SCL6-Akkubox), dessen Teile auf
Anhieb passten, und wurde an einem Monitor-Kabelclip erprobt (2 Druckiterationen bis
passend).

## Ort und Setup

- **Repo** = das Verzeichnis zwei Ebenen über dieser SKILL.md (`<repo>/skills/cad-print/`;
  ist der Skill per Symlink installiert, den Link auflösen: `realpath`). Es ist ein
  uv-Projekt, `pyproject.toml` hat alle Abhängigkeiten. Einrichtung steht in `README.md`.
- **Bibliothek**: `cadlib.py` im Repo-Root. Vor dem ersten Teil einer Session die
  Funktionsliste lesen (`grep -n "^def \|^class " cadlib.py`), dann gezielt Docstrings.
  Verbesserungen, die mehr als ein Teil brauchen, gehören in `cadlib.py`, nicht ins Teil.
- **Lernlog**: `NOTES.md` im Repo. Vor dem Konstruieren lesen (Drucker, Material,
  Passungen, Fallstricke), nach jeder Druckrückmeldung ergänzen.
- Pro Teil: `parts/<name>/<name>.py`, Ausgaben in `parts/<name>/out/<version>/`.
- Ausführen: `cd <repo> && uv run python -I parts/<name>/<name>.py`
  (`-I` ist ok, weil das Skript cadlib per `sys.path.insert` findet).
- Referenzteil zum Abschauen: `parts/cable_clip/cable_clip.py` (Aufbau, Checks,
  Bilder, Export). Neue Teile nach demselben Muster gliedern.
- OpenSCAD wird nur zum Rendern benutzt, nicht zum Modellieren. `cadlib` findet es über
  die Umgebungsvariable `OPENSCAD`, den `PATH` oder den macOS-App-Pfad.
- Drucker und Material: aus `NOTES.md`; fehlt die Angabe, beim Messen mit erfragen.

## Ablauf

### 1. Messen, bevor modelliert wird
Konkrete Maße erfragen, keine Schätzungen. Fotos zeigen Kontext, aber keine Millimeter.
Typisch nötig: Dicke/Breite an mehreren Stellen (Teile sind selten parallel), Radien
von Kanten und Ecken, Sperrzonen (Bildschirmfläche, Tasten, Lüftungsschlitze, Stecker),
Durchmesser von Kabeln/Schrauben, wie oft das Teil montiert/bewegt wird, Material und
Drucker falls abweichend. Alles in einer Nachricht fragen, nicht häppchenweise.

### 2. Konzept abstimmen
Kurze Beschreibung plus ASCII-Skizze, wie das Teil hält und was es tut, inklusive der
Kraftrichtungen (woran zieht das Kabel, wohin rutscht das Teil). Erst nach Zustimmung
modellieren. Bei mehreren sinnvollen Varianten eine empfehlen.

### 3. Modellieren
- **Koordinatensystem am Gegenstück verankern** (z.B. Monitorecke = Ursprung) und im
  Docstring des Skripts beschreiben. Das Gegenstück wird als eigener Körper modelliert:
  um die Spielpassung vergrößert ist es der Subtrahend, unverändert die Referenz für
  Überlappungs- und Abstandschecks und das Kontextobjekt in den Renderings.
- **Druckausrichtung zuerst festlegen**, dann jede Form so wählen, dass sie als Wand
  oder als Flanke mit höchstens 45° aufsteigt: Bohrungen quer zum Bett als Tropfen,
  Unterseiten von Vorsprüngen als 45°-Fase, keine Rundung an Bettkanten. Die Bettseite
  einen Rundungsradius zu weit bauen und mit `trim_by_plane` plan schneiden.
- **Rundungen**: aus konvexen Stücken mit `cl.rounded_hull` (Hülle von Kugeln an
  `cl.inset_polygon`-Punkten) bauen und vereinigen. Kein nachträgliches Runden per
  Minkowski in manifold3d: dauerte 8 min und lieferte kaputte Netze. An spitzen
  Innenecken weicht das eingerückte Polygon weit zurück, dort ein Füllstück setzen und
  das Gegenstück wieder herausschneiden. Kanten r 0.8 mm reichten gegen "scharfkantig".
- **Parameter oben im Skript** als Konstanten, gruppiert: gemessen (mit Datum), Passung,
  Form. Jede Zahl, die aus Druck-Feedback stammt, bekommt einen Kommentar mit altem Wert.
- `VERSION = "vN"` und darunter ein Kommentar pro Version: was das Feedback war, was
  geändert wurde. Ausgaben landen in `out/vN/`, alte Versionen bleiben liegen.

### 4. Prüfen
Jeder Lauf schreibt einen Report (`cl.Report`, gespeichert als `checks.json`) und endet
mit Exit-Code 1, wenn ein Check fehlschlägt. Pflicht sind:

| Check | Funktion | Warum |
|---|---|---|
| wasserdicht, ein Körper, Volumen, Maße | `check_solid` | Slicer und Booleans brauchen ein sauberes Netz; zwei Körper heißt meist ein vergessener Steg |
| Spiel gegen das Gegenstück | `check_no_overlap`, `check_gap` | Die Passung ist der Zweck des Teils |
| gewollte Klemmung | Volumen von `(rippen ^ gegenstück)` in einem Sollbereich | Rippen, die nicht greifen, oder Klemmung, die das Gehäuse belastet |
| Sperrzonen frei | `check_keepout` | z.B. sichtbare Bildfläche |
| Funktionsmaße | eigene Checks (Kabel frei in Bohrung, Spalt < Kabel) | |
| Wandstärke | `check_wall_thickness(min_mm=1.6)` | Unter ~4 Perimetern bricht PETG |
| Überhänge in Druckausrichtung | `check_overhangs(max_angle=45)` | Stützmaterial vermeiden |

Verbleibende kleine Befunde (ein paar mm² Überhang an einer Rundung) nur im Teilskript
mit Kommentar erlauben, nie die Defaults in `cadlib.py` lockern. Wenn ein Check rot ist,
die Ursache verstehen und die Geometrie ändern, statt die Schwelle zu verschieben. Beim
Kabelclip zeigten die Checks echte Fehler (Messerkanten am Einführschlitz, 55° statt 45°
Flanke, Kerbe in der Innenecke), und beim rechten Clip ließ sich ein gewachsener
Überhang durch eine Tropfenbohrung halbieren, statt die Grenze anzuheben.

### 5. Ansehen
`cl.render_openscad` schreibt pro Ansicht eine `.scad` mit `color() import()` und
rendert per OpenSCAD, optional als Kachelblatt. Immer mindestens: Teil am Gegenstück
von vorn und hinten, Teil allein, Druckausrichtung. Dazu `cl.plot_sections` mit
Schnitten durch die Passungsstellen und Maßlinien. Die Bilder selbst ansehen (Read auf
die PNG), bevor sie dem Nutzer gezeigt werden, dann das Blatt öffnen (`open` auf macOS).
Kamera: `(tx,ty,tz,rx,ry,rz,dist)`; bei y = nach hinten schaut `rz=35` von vorn links,
`rz=215` von hinten links. Matplotlib-Vorschauen (`render_views`) sind zum Beurteilen
zu grob.

### 6. Exportieren und übergeben
`cl.export_parts({"name": teil_in_druckausrichtung}, OUT, f"<name>_{VERSION}")` schreibt
STL pro Teil und eine 3MF, liest die 3MF zur Kontrolle zurück und liefert sha256.
Teile schon in Druckausrichtung und auf z=0 exportieren (`cl.drop_to_bed`), damit im
Slicer nichts gedreht werden muss. Die Übergabe enthält:
- Dateipfade und Druckausrichtung in einem Satz,
- die ASCII-Skizze aus Schritt 2 (bei Folgeversionen nur, wenn sich das Konzept ändert),
- Tabelle der Änderungen gegenüber der Vorversion,
- Checks in Kurzform,
- offene Risiken jeweils mit dem Parameter und Wert, an dem man drehen würde
  ("zu stramm: RIB_INTERF 0.6 -> 0.45"), damit die Rückmeldung nach dem Druck direkt
  in eine Änderung übersetzt werden kann.

### 7. Nach dem Druck iterieren
Feedback in Parameter übersetzen, `VERSION` hochzählen, Grund in den Kopfkommentar,
neu prüfen und rendern. Lieber ein, zwei Stellschrauben deutlich bewegen als alles
ein wenig. Was sich am gedruckten Teil bestätigt oder als falsch erwiesen hat, in
`NOTES.md` eintragen (Werte, Material, Drucker, Datum), damit das nächste Teil davon
profitiert. Mit mindestens einer Iteration rechnen und das vorher sagen.

## Passungen (PETG, Bambu Lab P2S, gedruckt bestätigt)

| Fall | Wert | Quelle |
|---|---|---|
| Stift in Bohrung | 0.10 mm pro Seite | BP-SCL6-Box |
| Tasche um Bauteil | 0.25 mm pro Seite | BP-SCL6-Box |
| Gleitspiel um Gegenstück | 0.20 mm pro Seite | Kabelclip |
| Klemmrippen auf glattem Gehäuse | 5 Rippen r 1.5, 0.6 mm Netto-Überdeckung (0.3 war zu locker) | Kabelclip v2 |
| Kabel einschnappen | Spalt ca. 70 % vom Kabel, Bohrung ca. 1.33x Kabel (85 % / 1.55x rutschte raus) | Kabelclip v2 |

Auf anderen Druckern oder Materialien sind das Startwerte, keine Garantie. `cl.FDM_FIT`
enthält die Grundwerte. Neue bestätigte Werte hier und in `NOTES.md` nachtragen,
unbestätigte als Schätzung kennzeichnen.

## Was schiefgehen kann

- `trimesh.split()` braucht scipy/networkx, Raycasts brauchen rtree: steht alles in
  `pyproject.toml`, also immer über `uv run` starten.
- `Manifold.rotate((0,-90,0))` bildet x auf z ab; Drehrichtungen im Bild prüfen.
- Gegenstücke sind selten ideal: leicht gewölbte Rückseiten, schräge Kanten. Das
  lineare Modell im Skript dokumentieren und als Risiko nennen.
- Nicht committen, solange der Nutzer nicht darum bittet.
