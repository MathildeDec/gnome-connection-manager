# Conversation : GCM Import libvirt depuis inventaire libvirt

**Date :** 2026-06-08  
**Modèle :** Claude Sonnet 4.6

---

## Contexte

Mathilde dispose de deux éléments existants :
1. **`libvirt_inventory.py`** — script Python 3 autonome (uploadé depuis Google Drive) qui interroge des hyperviseurs libvirt via SSH/paramiko pour lister les VMs et résoudre leurs IPs (virsh domifaddr, leases DHCP, nmap, ARP).
2. **`gnome_connection_manager.py`** (GCM) — gestionnaire de connexions SSH/Telnet GTK3 (kuthulux/gnome-connection-manager, v1.2.1), structuré autour de la classe `Wmain`, d'un `treeModel` GTK, d'un dict `groups`, et d'objets `Host`.

## Objectif

Ajouter dans GCM une fonction **"Importer depuis libvirt"** qui :
- s'intègre dans le menu existant (menuServers)
- liste les hyperviseurs virt-manager depuis dconf
- se connecte en SSH pour inventorier les VMs
- résout les IPs
- crée les entrées Host dans un groupe GCM cible

---

## Artefacts produits

### `gcm_import_libvirt.py`
Patch d'intégration structuré en 4 blocs :

| Bloc | Contenu | Destination dans GCM |
|---|---|---|
| Imports | `subprocess`, `re`, `threading`, `urlparse`, `paramiko` | En tête de fichier |
| `LibvirtImportDialog` | Dialogue GTK3 : liste URIs (checkboxes), champ groupe cible, log TextView, ProgressBar, thread worker | Avant `class Wmain` |
| `_libvirt_*` fonctions | `_libvirt_get_uris_from_dconf()`, `_libvirt_ssh_run()`, `_libvirt_fetch_hosts()` | Avant `class Wmain` |
| `_HOOK_CREATE_MENU` | Création du `Gtk.MenuItem` "Importer depuis libvirt…" | Fin de `Wmain.createMenu()` |
| `_HOOK_HANDLER` | `on_mnu_import_libvirt_activate()` : callback on_done, création groupe, instanciation Host, `save_config()` | Dans `class Wmain` |

### Logique de résolution IP (ordre de priorité)
1. `virsh domifaddr --source agent` (qemu-guest-agent, VMs running)
2. `virsh domifaddr --source arp`
3. Leases DHCP libvirt (`virsh net-dhcp-leases`)
4. Table ARP noyau (`ip neigh show`)
5. Fallback : nom de la VM comme hostname

### Points d'intégration dans GCM
```
1. Imports → haut du fichier (avec les autres imports)
2. LibvirtImportDialog + _libvirt_* → avant class Wmain
3. _HOOK_CREATE_MENU → à la fin de Wmain.createMenu()
4. on_mnu_import_libvirt_activate() → dans class Wmain
```

**Dépendance :** `pip install paramiko`

---

## Décisions de conception

- **Pas de nmap** dans la version GCM (contrairement à `libvirt_inventory.py`) pour ne pas bloquer l'UI ; on utilise seulement ARP+DHCP+domifaddr
- **Thread worker** pour l'import SSH afin de ne pas geler GTK
- **Déduplication** par nom de VM dans le groupe cible
- **Fallback hostname** = nom de la VM si aucune IP résolue (utile si DNS/hosts configuré)
- URIs locales (`qemu:///system`) ignorées automatiquement

---

## Instruction de configuration Drive

À partir de cette conversation, tous les artefacts créés ou modifiés sont automatiquement enregistrés dans ce dossier Google Drive. Le fichier `claude.md` est mis à jour à chaque nouvel artefact.
