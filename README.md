# Gnome Connection Manager (GCM) — v1.3.0

**Fork de [kuthulux/gnome-connection-manager](https://github.com/kuthulux/gnome-connection-manager)**
maintenu par [MathildeDec](https://github.com/MathildeDec/gnome-connection-manager).

Gnome Connection Manager (GCM) est un gestionnaire de connexions SSH avec onglets pour les environnements GTK+.  
À partir de la **version 1.3.0**, il supporte également les connexions **RDP** (via `xfreerdp`) et l'**import de VMs libvirt**.

> **Requires** : Python 3.x · GTK 3 · VTE 2.91

---

## Nouveautés v1.3.0

- **RDP intégré** : connexion RDP directement dans l'onglet GCM via XEmbed (`Gtk.Socket` + `xfreerdp /parent-window`)  
  — bascule automatique sur fenêtre externe si Wayland pur
- **Import libvirt** : importe les VMs d'un hyperviseur libvirt (SSH ou local) dans votre liste de connexions
- **GCMBase** : remplacement de `SimpleGladeApp` par un wrapper `Gtk.Builder` natif, sans dépendance tierce
- **Bugs upstream corrigés** : issues #64, #66, #67, #81, #82, #87, #88, #89
- **Docstrings Google** (#110) : 188 fonctions documentées
- Code Python 3.13 compatible, reformatté avec `black`

---

## Installation

### Depuis les sources

```bash
git clone https://github.com/MathildeDec/gnome-connection-manager
cd gnome-connection-manager
./gnome_connection_manager.py
```

### Dépendances (Debian/Ubuntu)

```bash
sudo apt install python3 python3-gi gir1.2-vte-2.91 gir1.2-gtk-3.0 expect
# Pour RDP :
sudo apt install freerdp2-x11   # ou freerdp3-x11
# Pour libvirt :
sudo apt install python3-libvirt
```

### Dépendances (Fedora/RHEL)

```bash
sudo dnf install python3 python3-gobject vte291 expect
# Pour RDP :
sudo dnf install freerdp
# Pour libvirt :
sudo dnf install python3-libvirt
```

---

## Langue

GCM utilise la langue par défaut de l'OS. Pour forcer une langue :

```bash
LANG=en_US.UTF-8 ./gnome_connection_manager.py
```

---

## Packaging (deb / rpm)

```bash
# Installer fpm
sudo apt install git ruby ruby-dev build-essential gettext
sudo gem install fpm

# Cloner et packager
git clone https://github.com/MathildeDec/gnome-connection-manager
cd gnome-connection-manager
make        # deb + rpm
make deb    # deb seulement
make rpm    # rpm seulement
```

---

## Contribuer

Les pull requests sont les bienvenues.  
Pour les changements importants, ouvrez d'abord une issue pour discuter de ce que vous souhaitez modifier.

## Licence

[GPLv3](https://www.gnu.org/licenses/gpl-3.0.html)

