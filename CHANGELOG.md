# Changelog — Gnome Connection Manager

## [1.3.0] — 2026-06-09 (MathildeDec fork)

### Added
- **RDP support** (étape 5) : connexion RDP via `xfreerdp` ou `xfreerdp3`, détection automatique du binaire disponible, onglet dédié avec log de session et boutons Connecter/Déconnecter
- **RDP XEmbed** (étape 6) : session xfreerdp embarquée directement dans l'onglet GCM via `Gtk.Socket` (X11 / XWayland) ; bascule automatique sur fenêtre externe si Wayland pur
- **Import libvirt** (étape 4) : dialogue d'import de VMs depuis `libvirt` (SSH ou local), ajout dans les groupes existants ou dans un nouveau groupe
- **GCMBase** (étape 3) : remplacement de `SimpleGladeApp` par un wrapper natif `Gtk.Builder` sans dépendance tierce
- **Docstrings Google** (issue #110) : 188 fonctions/méthodes documentées au format Google-style
- **Support du protocole dans `Host`** : champ `protocol` (ssh/telnet/rdp/local) dans la classe `Host`, le formulaire hôte et la sérialisation INI

### Fixed
- Python 3.13 : suppression de `from __future__ import print_function`, remplacement de `xrange` → `range`
- GTK3 : suppression de `Gtk.ImageMenuItem`, `Gtk.STOCK_*`, APIs dépréciées ; migration vers `Gtk.MenuItem` + `Gtk.Box`
- Issue #81 : crash au démarrage si `style.css` manquant → `try/except` non-bloquant
- Issue #82 : clone d'onglet avec mot de passe → logique `sendPassword` corrigée
- Issue #87 : freeze SSH sur équipements MikroTik → debounce 200 ms sur `on_terminal_size_allocate`
- Issue #88 : logging VTE cassé sur GTK 3.24+ → migration `output-written` / fallback `contents-changed`
- Issue #89 : passphrase SSH redemandée à chaque onglet → injection `SSH_AUTH_SOCK` dans l'environnement VTE
- Issue #64 : double-clic dans Midnight Commander ouvre un onglet → vérification `posY < tab_bar_height`
- Issue #66 : port du tunnel SSH perdu à la sauvegarde → sérialisation `tunnel_host:port` corrigée
- Issue #67 : surligage jaune cluster ne disparaît pas → `queue_draw()` forcé sur changement de cluster
- VTE dual-path : `output-written` (≥ VTE 0.60) avec fallback `contents-changed`

### Changed
- `app_web` : pointe désormais vers `https://github.com/MathildeDec/gnome-connection-manager`
- Version bumped : `1.2.1` → `1.3.0`
- Code reformatté avec `black` (max-line-length 120) — 0 erreur `flake8`

---

## [1.2.1] — upstream kuthulux

Dernière version upstream de référence.  
Voir : https://github.com/kuthulux/gnome-connection-manager
