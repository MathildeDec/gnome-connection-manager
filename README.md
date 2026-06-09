# Gnome Connection Manager (GCM) — v1.3.1

> **Le gestionnaire de connexions multi-protocoles le plus complet pour GNOME / GTK3.**

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://python.org)
[![GTK 3](https://img.shields.io/badge/GTK-3.24-green.svg)](https://gtk.org)
[![License: GPLv3](https://img.shields.io/badge/license-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0.html)
[![Tests](https://img.shields.io/badge/tests-379%20passés-brightgreen.svg)](tests/)

**Fork de [kuthulux/gnome-connection-manager](https://github.com/kuthulux/gnome-connection-manager)**  
maintenu par [MathildeDec](https://github.com/MathildeDec/gnome-connection-manager).

---

## Pourquoi GCM ?

GCM regroupe dans une seule fenêtre à onglets **tous vos accès distants** :
terminal SSH, bureau RDP embarqué, console série RS-232/485, VNC, SPICE,
telnet et session locale. Plus besoin de jongler entre dix outils différents.

| Protocole | Implémentation | Description |
|-----------|---------------|-------------|
| **SSH** | VTE intégré | Terminal complet avec agent, tunnels, cluster mode |
| **RDP** | XEmbed + xfreerdp | Bureau Windows **directement dans l'onglet** GCM (XEmbed X11) ou fenêtre externe (Wayland) |
| **VNC** | vncviewer / vinagre / remmina | Connexion VNC avec authentification |
| **SPICE** | remote-viewer / virt-viewer | Console VM SPICE haute performance |
| **Série** | picocom / minicom / screen | Port série RS-232/RS-485 avec **11 templates constructeurs** |
| **Telnet** | telnet / expect | Sessions Telnet classiques |
| **Local** | shell | Terminal local |

---

## Fonctionnalités clés

### 🖥️ Multi-protocoles dans un seul outil
- Ouvrez un onglet SSH, un onglet RDP et une console série côte à côte
- Chaque connexion conserve ses propres paramètres (police, couleurs, tunnel…)
- Sauvegarde chiffrée des mots de passe (AES)

### 🔷 RDP intégré via XEmbed
- La session Windows s'affiche **dans l'onglet GCM** (pas une fenêtre séparée)
- Bascule automatique sur fenêtre externe si Wayland pur est détecté
- Support `xfreerdp2` et `xfreerdp3`, `/cert:ignore`, `/dynamic-resolution`
- Domaine `CORP\user` géré automatiquement (`/d:` + `/u:`)

### 🔌 Console Série RS-232 / RS-485
- Terminal VTE **embarqué** (pas de fenêtre externe)
- Contrôles dédiés : débit, bits de données, parité, bits de stop, contrôle de flux
- **11 templates constructeurs** pré-configurés :

  | Template | Débit | Format |
  |----------|-------|--------|
  | Cisco IOS / IOS-XE / NX-OS | 9600 | 8N1 |
  | HP Comware (H3C) | 9600 | 8N1 |
  | Aruba AOS-S / AOS-CX | 9600 | 8N1 |
  | Juniper JunOS | 9600 | 8N1 |
  | Fortinet FortiOS | 9600 | 8N1 |
  | Palo Alto PAN-OS | 9600 | 8N1 |
  | F5 TMOS | **19200** | 8N1 |
  | Linux / Raspberry Pi | **115200** | 8N1 |
  | Arduino / ESP32 | **115200** | 8N1 |
  | RS-485 Modbus RTU | 9600 | 8N1 |
  | Libre (manuel) | configurable | configurable |

### 📦 Import libvirt
- Importe automatiquement les VMs d’un hyperviseur KVM/QEMU (via SSH ou URI locale)
- Ségmentation des noms en groupes GCM (`prod-web-01` → groupe **PROD**)
- Détection automatique Windows → protocole RDP
- Résolution IP : domifaddr → leases DHCP → ARP noyau

### 🌐 16 langues supportées
ar · cs · de · en · fr · it · ja · ko · nb · nl · pl · pt · ru · sv · tr · uk

### 🧪 379 tests unitaires
Suite `pytest` couvrant chiffrement, `Host`, `HostUtils`, Serial, RDP, VNC, SPICE, i18n.

---

## Installation

### Depuis les sources

```bash
git clone https://github.com/MathildeDec/gnome-connection-manager
cd gnome-connection-manager
./gnome_connection_manager.py
```

### Dépendances (Debian / Ubuntu)

```bash
# Obligatoires
sudo apt install python3 python3-gi gir1.2-vte-2.91 gir1.2-gtk-3.0 expect

# RDP
sudo apt install freerdp2-x11          # ou freerdp3-x11

# VNC
sudo apt install tigervnc-viewer       # ou vinagre, remmina

# SPICE
sudo apt install virt-viewer           # fournit remote-viewer

# Console série
sudo apt install picocom               # ou minicom

# Import libvirt
sudo apt install python3-libvirt
pip3 install paramiko
```

### Dépendances (Fedora / RHEL)

```bash
sudo dnf install python3 python3-gobject vte291 expect freerdp \
                 tigervnc virt-viewer picocom python3-libvirt
pip3 install paramiko
```

---

## Utilisation rapide

### Ajouter une connexion SSH
1. Clic droit sur un groupe → **Nouveau hôte**
2. Remplir : nom, adresse, utilisateur, port (22)
3. Protocole : `ssh` (défaut)
4. Double-clic sur le host pour ouvrir l’onglet terminal

### Ajouter une connexion RDP
1. **Nouveau hôte** → protocole `rdp`, port `3389`
2. Renseigner `Utilisateur` et optionnellement `Mot de passe`
3. Le bureau Windows s'ouvre directement dans l'onglet

### Ajouter une connexion série
1. **Nouveau hôte** → protocole `serial`
2. Host = chemin du port (`/dev/ttyUSB0`), Port = débit initial (`9600`)
3. À l'ouverture : sélectionnez un **template** pour pré-remplir tous les paramètres

### Importer des VMs libvirt
1. Menu **Serveurs → Importer depuis libvirt…**
2. Saisir l’URI (ex. `qemu+ssh://root@192.168.1.1/system`)
3. Cliquer **Importer** — les VMs apparaissent groupées dans l’arbre

---

## Langue

GCM détecte automatiquement la langue du système. Pour forcer :

```bash
LANG=en_US.UTF-8 ./gnome_connection_manager.py
LANG=de_DE.UTF-8 ./gnome_connection_manager.py
```

---

## Packaging (deb / rpm)

```bash
# Installer fpm
sudo apt install git ruby ruby-dev build-essential gettext
sudo gem install fpm

# Packager
git clone https://github.com/MathildeDec/gnome-connection-manager
cd gnome-connection-manager
make        # deb + rpm
make deb    # deb seulement
make rpm    # rpm seulement
```

---

## Nouveautés

### v1.3.1
- **SerialTab** : console série RS-232/RS-485 embarquée dans VTE — picocom / minicom / screen
  - 11 templates constructeurs (Cisco, HP, Aruba, Juniper, Fortinet, Palo Alto, F5, Linux, Arduino, Modbus, Libre)
  - Combos dédiés : débit, bits de données, parité, bits de stop, contrôle de flux
- **VncTab** : connexion VNC native (vncviewer / vinagre / remmina)
- **SpiceTab** : connexion SPICE (remote-viewer / virt-viewer)
- **16 langues** : ajout uk / ja / ar / tr / nl / cs / sv / nb
- **379 tests unitaires** (pytest)
- Fix `save_host_to_ini` TypeError Python 3 (champs non-str)
- Fix `encrypt_old`/`decrypt_old` Python 3 bytes/str

### v1.3.0
- **RDP XEmbed** : bureau Windows directement dans l’onglet (GtkSocket + `xfreerdp /parent-window`)
- **Import libvirt** : inventaire VMs KVM/QEMU avec détection Windows
- **GCMBase** : remplacement de `SimpleGladeApp` par `Gtk.Builder` natif
- 8 bugs upstream corrigés (#64 #66 #67 #81 #82 #87 #88 #89)
- 188 docstrings Google (#110)
- Compatibilité Python 3.13 / GTK 3.24+

---

## Contribuer

Les pull requests sont les bienvenues.  
Consultez [fork/ROADMAP-GCM-v1.3.md](fork/ROADMAP-GCM-v1.3.md) pour les fonctionnalités planifiées.  
Pour les changements importants, ouvrez d’abord une issue.

## Licence

[GPLv3](https://www.gnu.org/licenses/gpl-3.0.html)

