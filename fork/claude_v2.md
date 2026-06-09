# Conversation : GCM Import libvirt depuis inventaire libvirt

**Date :** 2026-06-08 / 2026-06-09
**Modèle :** Claude Sonnet 4.6

---

## Contexte

Mathilde dispose de deux éléments existants :
1. **`libvirt_inventory.py`** — script Python 3 autonome (uploadé depuis Google Drive) qui interroge des hyperviseurs libvirt via SSH/paramiko pour lister les VMs et résoudre leurs IPs (virsh domifaddr, leases DHCP, nmap, ARP).
2. **`gnome_connection_manager.py`** (GCM) — gestionnaire de connexions SSH/Telnet GTK3 (kuthulux/gnome-connection-manager), structuré autour de la classe `Wmain`, d'un `treeModel` GTK, d'un dict `groups`, et d'objets `Host`.

## Objectif

Ajouter dans GCM une fonction **"Importer depuis libvirt"** dans le menu Serveurs.

---

## Artefacts produits

### `gcm_import_libvirt.py` (v1 — ID Drive: 1d_LD1NVPeE4fV55ui__C3ylPAsf4wusq)
Version initiale : dialogue GTK3, URIs dconf, thread worker, résolution IP.
Groupe cible unique saisi manuellement dans le dialogue.

### `gcm_import_libvirt_v2.py` (v2 — ID Drive: 1ppbbsIOeo_6g_4teCUQbUdawhYZJqQ5v)
Version finale avec les nouvelles fonctionnalités :

| Composant | Description |
|---|---|
| `_vm_name_split(vm_name)` | Segmentation nom VM → (GROUPE, nom_court) |
| `_collect_ssh_keys()` | Collecte clés privées ~/.ssh, Ed25519 d'abord puis RSA |
| `_paramiko_connect()` | Auth SSH par clé (Ed25519 → RSA → ECDSa → agent), jamais de mot de passe |
| `LibvirtImportDialog` | Dialogue GTK3 : champ user SSH, liste URIs cochables, note segmentation, log, progressbar |
| `_libvirt_fetch_hosts()` | Inventaire VMs + résolution IP + segmentation nom |
| `LibvirtPrefsTab` | Onglet "Libvirt" dans les préférences GCM : user par défaut, notes |
| `_HOOK_CREATE_MENU` | Item menu "Importer depuis libvirt…" dans menuServers |
| `_HOOK_HANDLER` | `on_mnu_import_libvirt_activate()` : crée groupes multiples + hosts |
| `_HOOK_PREFS` | Intégration onglet prefs dans `on_preferences_activate()` |

---

## Règles de segmentation des noms VM

```
Séparateurs reconnus : _ (underscore), - (tiret), espace
Premier token → groupe en MAJUSCULES
Reste         → nom affiché dans GCM

Exemples :
  prod-web-01     →  PROD    /  web-01
  prod_db_master  →  PROD    /  db_master
  dev web front   →  DEV     /  web front
  INT-dns01       →  INT     /  dns01
  standalone      →  LIBVIRT /  standalone  (pas de séparateur)
```

Tests : 6/6 ✓ (vérifiés à l'exécution)

---

## Auth SSH

Ordre de tentative pour chaque hyperviseur et chaque VM :
1. Clés Ed25519 de `~/.ssh` (détection par header PEM + nom de fichier)
2. Clés RSA de `~/.ssh`
3. Autres clés (ECDSA, DSS)
4. Agent SSH système (fallback)
5. Jamais de mot de passe

---

## Résolution IP (ordre de priorité)

1. `virsh domifaddr --source agent` (qemu-guest-agent, VMs running)
2. `virsh domifaddr --source arp`
3. Leases DHCP libvirt (`virsh net-dhcp-leases`)
4. Table ARP noyau (`ip neigh show`)
5. Fallback : nom de la VM comme hostname (si DNS/hosts configuré)

---

## Points d'intégration dans GCM (6 points)

```
1. Imports (os, subprocess, re, threading, urlparse, paramiko)
   → haut du fichier

2. LIBVIRT_DEFAULT_USER + fonctions _vm_name_split, _collect_ssh_keys,
   _paramiko_connect, _libvirt_get_uris_from_dconf, _libvirt_ssh_run,
   _libvirt_fetch_hosts + classes LibvirtImportDialog, LibvirtPrefsTab
   → avant class Wmain

3. _HOOK_CREATE_MENU
   → fin de Wmain.createMenu()

4. on_mnu_import_libvirt_activate()  [contenu dans _HOOK_HANDLER]
   → dans class Wmain

5. LibvirtPrefsTab instanciation + apply()  [contenu dans _HOOK_PREFS]
   → dans Wmain.on_preferences_activate()

6. config["libvirt_default_user"] chargé/sauvé dans load_config/save_config
```

**Dépendance :** `pip install paramiko`

---

## Décisions de conception

- **Pas de nmap** (contrairement à libvirt_inventory.py) pour ne pas bloquer l'UI GTK
- **Thread worker** pour l'import SSH → UI non gelée
- **Déduplication** par nom dans chaque groupe
- **h.agent = True** sur les hosts créés (transmission agent SSH)
- **User hyperviseur** (URI) ≠ **user VM** (champ séparé dans le dialogue)
- URIs locales `qemu:///system` ignorées automatiquement

---

## Fichiers Drive

| Fichier | ID | Description |
|---|---|---|
| `gcm_import_libvirt.py` | 1d_LD1NVPeE4fV55ui__C3ylPAsf4wusq | v1 |
| `gcm_import_libvirt_v2.py` | 1ppbbsIOeo_6g_4teCUQbUdawhYZJqQ5v | v2 (final) |
| `claude.md` | 1gF40A6trFq49s4amVqRSJFc7WBUY0HRO | ce fichier (v1) |
| `claude.md` (v2) | ce fichier | mis à jour |

Dossier : `GCM Import libvirt depuis inventaire libvirt` (ID: 1xTELFR_L7GsQFyPl1pT3DcDKk7tX13XV)
