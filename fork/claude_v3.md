# Conversation : GCM Import libvirt depuis inventaire libvirt

**Date :** 2026-06-08 / 2026-06-09
**Modèle :** Claude Sonnet 4.6

---

## Contexte

Mathilde travaille sur un patch pour **gnome_connection_manager.py** (kuthulux/GCM v1.2.1), gestionnaire de connexions SSH/Telnet GTK3. Deux extensions sont développées :

1. **Import libvirt** : importer automatiquement les VMs d'hyperviseurs libvirt distants
2. **Support RDP** : ajouter xfreerdp comme protocole de connexion dans GCM

---

## Fichiers Drive

| Fichier | ID Drive | Description |
|---|---|---|
| `gcm_import_libvirt.py` | 1d_LD1NVPeE4fV55ui__C3ylPAsf4wusq | Import libvirt v1 |
| `gcm_import_libvirt_v2.py` | 1ppbbsIOeo_6g_4teCUQbUdawhYZJqQ5v | Import libvirt v2 (final) |
| `gcm_rdp.py` | 16XGlzCFTeLuA7LRGAPmg61wNsEd8jCQn | Patch RDP (final) |
| `claude.md` (v1) | 1gF40A6trFq49s4amVqRSJFc7WBUY0HRO | historique |
| `claude_v2.md` | 1L8buoN3vfcu8Tjw6w2e7j6A_hANxuUzG | historique |

Dossier Drive : `GCM Import libvirt depuis inventaire libvirt` (ID: `1xTELFR_L7GsQFyPl1pT3DcDKk7tX13XV`)

---

## Patch 1 — Import libvirt v2 (`gcm_import_libvirt_v2.py`)

### Fonctionnalités
- Dialogue GTK3 : liste URIs dconf/virt-manager, champ user SSH, log, progressbar
- **Segmentation automatique** du nom VM : premier token (_, -, espace) → groupe MAJUSCULES
- **Auth SSH par clé** : Ed25519 → RSA → agent, jamais de mot de passe
- **User configurable** : `root` par défaut, modifiable dans Préférences > onglet Libvirt
- Résolution IP : domifaddr (agent/arp) → DHCP leases → ARP noyau → fallback hostname

### Règles de segmentation
```
prod-web-01     →  PROD    /  web-01
prod_db_master  →  PROD    /  db_master
INT-dns01       →  INT     /  dns01
standalone      →  LIBVIRT /  standalone
```

### Points d'intégration (6)
1. Imports + `LIBVIRT_DEFAULT_USER` → haut du fichier
2. `_vm_name_split`, `_collect_ssh_keys`, `_paramiko_connect`, `_libvirt_*` + classes → avant `class Wmain`
3. `_HOOK_CREATE_MENU` → fin de `Wmain.createMenu()`
4. `on_mnu_import_libvirt_activate()` → dans `class Wmain`
5. `LibvirtPrefsTab` instanciation + `.apply()` → dans `on_preferences_activate()`
6. `config["libvirt_default_user"]` → `load_config`/`save_config`

---

## Patch 2 — Support RDP (`gcm_rdp.py`)

### Principe
GCM utilise VTE (terminal émulateur) pour SSH/Telnet. RDP ne pouvant pas s'exécuter dans VTE, l'approche est :
- Nouveau champ `protocol` sur la classe `Host` : `"ssh"` | `"telnet"` | `"rdp"` | `"local"`
- `addTab()` détecte `protocol=="rdp"` → appelle `_open_rdp_tab()` au lieu du chemin VTE
- L'onglet GCM affiche un widget `RdpTab` (GTK Box) avec statut + log + boutons
- `xfreerdp` est lancé en **processus externe** via `subprocess.Popen`
- La fenêtre RDP est indépendante de GCM (comportement normal de xfreerdp)

### Classe RdpTab
- Affiche : titre (host/user/port), description, statut, boutons Connecter/Déconnecter
- Champ "Options xfreerdp" modifiable à la volée (ex: `/drive:home,/home/user /sound:sys:alsa /multimon`)
- Log des sorties xfreerdp (thread reader)
- Masquage du mot de passe dans le log (`/p:****`)
- Reconnexion possible sans fermer l'onglet

### Commande xfreerdp construite
```
xfreerdp /v:HOST:PORT /u:USER [/d:DOMAIN] [/p:PASS]
         /cert:ignore /dynamic-resolution [OPTIONS]
```
Domaine séparé si `user` contient `\` (format `DOMAIN\user`).

### Points d'intégration (6)
1. `import shutil` + `RDP_BIN = shutil.which("xfreerdp") or "xfreerdp"` → globales
2. Champ `Host.protocol = "ssh"` + `clone()` + sérialisation config → classe Host
3. `class RdpTab` → avant `class Wmain`
4. `_HOOK_ADDTAB` → début de `addTab()` (détection protocol)
5. `_open_rdp_tab()` → dans `class Wmain`
6. ComboBox Protocol (ssh/telnet/rdp/local) + port auto → dialogue d'édition host

### Intégration avec l'import libvirt
Dans `_libvirt_fetch_hosts()`, détection heuristique des VMs Windows par nom :
- Pattern `win|w2019|w2022|wdc|wsrv` → `protocol="rdp"`, `port=3389`, `user="Administrator"`
- Autres → `protocol="ssh"`, `port=22`, `user=ssh_user`

### Dépendance
```
sudo apt install freerdp2-x11   # ou freerdp3-x11
```

---

## Décisions de conception communes

| Décision | Raison |
|---|---|
| Pas de nmap dans import libvirt | Eviter les blocages UI GTK |
| Thread worker pour imports SSH | UI non gelée pendant l'inventaire |
| xfreerdp externe (pas embarqué) | Embarquer xfreerdp dans GTK est complexe et fragile |
| `h.agent = True` sur hosts SSH importés | Transmission de l'agent SSH |
| Masquage `/p:****` dans log RDP | Sécurité — pas de mot de passe en clair dans l'UI |
| Détection Windows par nom VM | `virsh dumpxml` ne fournit pas toujours l'OS type de façon fiable |
