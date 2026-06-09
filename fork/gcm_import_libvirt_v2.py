#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
gcm_import_libvirt.py  v2
=========================
Patch à intégrer dans gnome_connection_manager.py.

NOUVEAUTÉS v2 :
  - Segmentation automatique du nom VM : le premier token (séparateur _, -, espace)
    devient le nom du groupe GCM en MAJUSCULES ; le reste est le nom affiché.
    Exemple : "prod-web-01" → groupe "PROD", nom "web-01"
    Sans séparateur : groupe "LIBVIRT", nom = nom complet.
  - User SSH par défaut : "root", configurable dans Édition > Préférences > Libvirt
    (clé config["libvirt_default_user"]), surchargeable dans la boîte d'import.
  - Authentification SSH par clé uniquement : tente Ed25519 puis RSA depuis ~/.ssh,
    puis agent SSH système. Jamais de mot de passe.

INTÉGRATION (6 points) :
  1. Imports → haut du fichier
  2. Constante LIBVIRT_DEFAULT_USER + fonctions _libvirt_* + classes → avant class Wmain
  3. Onglet LibvirtPrefsTab → dans la boîte de préférences GCM
  4. _HOOK_CREATE_MENU → fin de Wmain.createMenu()
  5. on_mnu_import_libvirt_activate() → dans class Wmain
  6. _HOOK_PREFS → dans Wmain.on_preferences_activate()
"""

import os
import subprocess
import re
import threading
from urllib.parse import urlparse

try:
    import paramiko
    _PARAMIKO_OK = True
except ImportError:
    _PARAMIKO_OK = False


# ─── CONFIG ───────────────────────────────────────────────────────────────────
LIBVIRT_DEFAULT_USER = "root"   # écrasé par config["libvirt_default_user"]


# ─── SEGMENTATION NOM VM → (GROUPE, nom_court) ───────────────────────────────

def _vm_name_split(vm_name: str) -> tuple:
    """
    Premier token (séparateur _, - ou espace) → groupe MAJUSCULES.
    Reste → nom court affiché dans GCM.
    Sans séparateur → groupe "LIBVIRT", nom = vm_name.

    Exemples :
        "prod-web-01"    → ("PROD",    "web-01")
        "prod_db_master" → ("PROD",    "db_master")
        "dev web front"  → ("DEV",     "web front")
        "standalone"     → ("LIBVIRT", "standalone")
        "INT-dns01"      → ("INT",     "dns01")
    """
    m = re.match(r'^([^_\-\s]+)[_\-\s](.*)', vm_name)
    if m:
        return m.group(1).upper(), m.group(2)
    return "LIBVIRT", vm_name


# ─── COLLECTE CLÉS SSH ───────────────────────────────────────────────────────

def _collect_ssh_keys() -> list:
    """
    Liste les clés privées de ~/.ssh, Ed25519 en premier, puis RSA.
    Exclut .pub, known_hosts, config, authorized_keys.
    """
    ssh_dir = os.path.expanduser("~/.ssh")
    if not os.path.isdir(ssh_dir):
        return []
    order = {"ed25519": 0, "rsa": 1}
    keys = []
    for fname in os.listdir(ssh_dir):
        if fname.endswith(".pub") or fname in (
                "known_hosts", "known_hosts.old", "config", "authorized_keys"):
            continue
        full = os.path.join(ssh_dir, fname)
        if not os.path.isfile(full):
            continue
        try:
            head = open(full, "rb").read(80).decode(errors="replace")
            if "PRIVATE KEY" not in head:
                continue
        except OSError:
            continue
        kt = "other"
        if "ed25519" in fname.lower() or "ED25519" in head:
            kt = "ed25519"
        elif "rsa" in fname.lower() or "RSA" in head:
            kt = "rsa"
        keys.append((order.get(kt, 2), full))
    keys.sort(key=lambda x: x[0])
    return [k for _, k in keys]


# ─── CONNEXION SSH PAR CLÉ ───────────────────────────────────────────────────

def _paramiko_connect(hostname, port, username, log_fn=None):
    """
    Tente Ed25519 → RSA → autres clés → agent système.
    Retourne un paramiko.SSHClient connecté, ou None.
    """
    keys = _collect_ssh_keys()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    for key_path in keys:
        pkey = None
        for cls in (paramiko.Ed25519Key, paramiko.RSAKey,
                    paramiko.ECDSAKey, paramiko.DSSKey):
            try:
                pkey = cls.from_private_key_file(key_path)
                break
            except Exception:
                continue
        if pkey is None:
            continue
        try:
            client.connect(hostname=hostname, port=port, username=username,
                           pkey=pkey, timeout=10,
                           look_for_keys=False, allow_agent=False)
            if log_fn:
                log_fn(f"  SSH OK → {username}@{hostname}:{port}"
                       f"  [{os.path.basename(key_path)}]")
            return client
        except paramiko.AuthenticationException:
            continue
        except Exception as e:
            if log_fn:
                log_fn(f"  Erreur clé {os.path.basename(key_path)} : {e}")

    # Fallback agent
    try:
        client.connect(hostname=hostname, port=port, username=username,
                       timeout=10, look_for_keys=False, allow_agent=True)
        if log_fn:
            log_fn(f"  SSH OK → {username}@{hostname}:{port}  [agent]")
        return client
    except Exception as e:
        if log_fn:
            log_fn(f"  ERREUR SSH (toutes clés échouées) : {e}")
        return None


# ─── DIALOGUE D'IMPORT ───────────────────────────────────────────────────────

class LibvirtImportDialog:
    """
    Dialogue GTK3 :
      - champ User SSH (pré-rempli depuis config, modifiable pour la session)
      - liste cochable des hyperviseurs URI (depuis dconf/virt-manager)
      - note explicative sur la segmentation des noms
      - log TextView + ProgressBar (thread worker)
    """

    def __init__(self, parent_window, on_done_callback, default_user="root"):
        self.parent       = parent_window
        self.on_done      = on_done_callback
        self.default_user = default_user
        self._build_ui()

    def _build_ui(self):
        dlg = Gtk.Dialog(title="Importer depuis libvirt",
                         transient_for=self.parent, modal=True)
        dlg.set_default_size(620, 500)
        dlg.add_button("_Annuler", Gtk.ResponseType.CANCEL)
        self._btn_import = dlg.add_button("_Importer", Gtk.ResponseType.OK)
        self._btn_import.get_style_context().add_class("suggested-action")

        box = dlg.get_content_area()
        box.set_spacing(8)
        for side in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{side}")(12)

        # User SSH
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hb.pack_start(Gtk.Label(label="User SSH pour les VMs :"), False, False, 0)
        self._entry_user = Gtk.Entry()
        self._entry_user.set_text(self.default_user)
        self._entry_user.set_tooltip_text(
            "Utilisateur SSH des VMs importées.\n"
            "Valeur par défaut : Édition > Préférences > Libvirt."
        )
        hb.pack_start(self._entry_user, False, False, 0)
        box.pack_start(hb, False, False, 0)

        # URIs hyperviseurs
        box.pack_start(
            Gtk.Label(label="Hyperviseurs (virt-manager / dconf) :"),
            False, False, 2
        )
        self._uri_store = Gtk.ListStore(bool, str)
        tv = Gtk.TreeView(model=self._uri_store)
        tv.set_headers_visible(True)
        cr = Gtk.CellRendererToggle()
        cr.connect("toggled", self._on_uri_toggled)
        tv.append_column(Gtk.TreeViewColumn("", cr, active=0))
        tv.append_column(Gtk.TreeViewColumn("URI libvirt",
                                             Gtk.CellRendererText(), text=1))
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(80)
        sw.add(tv)
        box.pack_start(sw, False, False, 0)

        # Note segmentation
        lbl = Gtk.Label()
        lbl.set_markup(
            '<i><small>'
            'Groupes automatiques : premier token du nom VM (_, -, espace) '
            '→ groupe en MAJUSCULES\n'
            '"prod-web-01" → PROD / "web-01"  ·  '
            '"standalone" → LIBVIRT / "standalone"'
            '</small></i>'
        )
        lbl.set_xalign(0)
        box.pack_start(lbl, False, False, 0)

        # Log
        self._log_buf = Gtk.TextBuffer()
        lv = Gtk.TextView(buffer=self._log_buf)
        lv.set_editable(False); lv.set_monospace(True)
        lv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw_log = Gtk.ScrolledWindow()
        sw_log.set_min_content_height(130)
        sw_log.add(lv)
        box.pack_start(sw_log, True, True, 0)
        self._log_view = lv

        # Progressbar
        self._progress = Gtk.ProgressBar()
        self._progress.set_show_text(True)
        self._progress.set_text("En attente…")
        box.pack_start(self._progress, False, False, 0)

        self._dlg = dlg
        dlg.show_all()
        self._populate_uris()
        dlg.connect("response", self._on_response)

    def _populate_uris(self):
        uris = _libvirt_get_uris_from_dconf()
        if not uris:
            self._log("Aucune URI trouvée dans dconf (virt-manager non configuré ?).")
            self._uri_store.append([True, "qemu+ssh://root@hyperviseur/system"])
            return
        for uri in uris:
            self._uri_store.append([bool(urlparse(uri).hostname), uri])

    def _on_uri_toggled(self, renderer, path):
        self._uri_store[path][0] = not self._uri_store[path][0]

    def _log(self, msg):
        def _do():
            self._log_buf.insert(self._log_buf.get_end_iter(), msg + "\n")
            adj = self._log_view.get_vadjustment()
            adj.set_value(adj.get_upper())
        GLib.idle_add(_do)

    def _set_progress(self, frac, text):
        GLib.idle_add(lambda: (
            self._progress.set_fraction(frac),
            self._progress.set_text(text)
        ))

    def _on_response(self, dlg, response_id):
        if response_id == Gtk.ResponseType.OK:
            self._run_import()
        else:
            dlg.destroy()

    def _run_import(self):
        self._btn_import.set_sensitive(False)
        uris = [row[1] for row in self._uri_store if row[0]]
        if not uris:
            self._log("Aucune URI sélectionnée.")
            self._btn_import.set_sensitive(True)
            return
        user = self._entry_user.get_text().strip() or "root"

        def worker():
            results = _libvirt_fetch_hosts(uris, user, self._log, self._set_progress)
            GLib.idle_add(self._finish, results)

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, host_dicts):
        self._set_progress(1.0, f"{len(host_dicts)} hôte(s) importé(s)")
        self._log(f"\nTerminé — {len(host_dicts)} hôte(s) prêts.")
        self.on_done(host_dicts)
        self._btn_import.set_label("Fermer")
        self._btn_import.set_sensitive(True)
        self._dlg.disconnect_by_func(self._on_response)
        self._dlg.connect("response", lambda d, r: d.destroy())


# ─── FONCTIONS UTILITAIRES ────────────────────────────────────────────────────

def _libvirt_get_uris_from_dconf():
    try:
        r = subprocess.run(
            ["dconf", "read", "/org/virt-manager/virt-manager/connections/uris"],
            capture_output=True, text=True, timeout=5,
        )
        raw = r.stdout.strip()
        if not raw or raw == "@as []":
            return []
        return re.findall(r"'([^']+)'", raw)
    except Exception:
        return []


def _libvirt_ssh_run(client, cmd, timeout=30):
    _, stdout, _ = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode(errors="replace").strip()


def _libvirt_fetch_hosts(uris, ssh_user, log_fn, progress_fn):
    """
    Pour chaque URI :
      1. Connexion SSH par clé (Ed25519 > RSA > agent) sur l'hyperviseur
      2. virsh list --all --name
      3. Résolution IP : domifaddr (agent/arp) → DHCP leases → ARP noyau
      4. Segmentation nom VM → groupe MAJUSCULES + nom court
    Retourne liste de dicts {"name", "host", "user", "port", "password",
                              "description", "group", "hypervisor"}.
    """
    if not _PARAMIKO_OK:
        log_fn("ERREUR : paramiko non installé  →  pip install paramiko")
        return []

    results = []
    total = len(uris)

    for idx, uri in enumerate(uris):
        log_fn(f"\n── Hyperviseur : {uri}")
        progress_fn(idx / total, f"Connexion à {uri}…")

        parsed    = urlparse(uri)
        scheme    = parsed.scheme
        transport = (scheme.split("+")[1] if "+" in scheme
                     else ("tcp" if parsed.hostname else "local"))
        hv_host   = parsed.hostname or "localhost"
        hv_port   = parsed.port or 22
        hv_user   = parsed.username or "root"   # user pour l'hyperviseur lui-même

        if transport == "local":
            log_fn("  → URI locale ignorée (qemu:///system).")
            continue

        client = _paramiko_connect(hv_host, hv_port, hv_user, log_fn)
        if client is None:
            continue

        try:
            vm_names = [
                n for n in
                _libvirt_ssh_run(client, "virsh list --all --name").splitlines()
                if n.strip()
            ]
            log_fn(f"  {len(vm_names)} VM(s) trouvée(s)")

            # Table ARP noyau
            arp = {}
            for line in _libvirt_ssh_run(
                    client, "ip neigh show 2>/dev/null || arp -n 2>/dev/null"
            ).splitlines():
                m = re.search(
                    r"(\d+\.\d+\.\d+\.\d+).*?([0-9a-f]{2}(?::[0-9a-f]{2}){5})",
                    line, re.I
                )
                if m:
                    arp[m.group(2).lower()] = m.group(1)

            # Leases DHCP libvirt
            dhcp = {}
            for net in _libvirt_ssh_run(client, "virsh net-list --name").splitlines():
                net = net.strip()
                if not net:
                    continue
                for line in _libvirt_ssh_run(
                        client, f"virsh net-dhcp-leases {net} 2>/dev/null"
                ).splitlines():
                    parts = line.split()
                    if len(parts) >= 4 and ":" in parts[1]:
                        ip_raw = parts[3].split("/")[0]
                        if re.match(r"\d+\.\d+\.\d+\.\d+", ip_raw):
                            dhcp[parts[1].lower()] = ip_raw

            for vm_name in vm_names:
                state = _libvirt_ssh_run(client, f"virsh domstate {vm_name}").strip()
                xml   = _libvirt_ssh_run(client, f"virsh dumpxml {vm_name}")

                ip_addr = ""
                for block in re.findall(r"<interface.*?</interface>", xml, re.DOTALL):
                    mac_m = re.search(r"<mac address=['\"]([^'\"]+)['\"]", block)
                    if not mac_m:
                        continue
                    mac = mac_m.group(1).lower()

                    if state == "running":
                        for src in ("agent", "arp"):
                            out = _libvirt_ssh_run(
                                client,
                                f"virsh domifaddr {vm_name} --source {src} 2>/dev/null"
                            )
                            for l in out.splitlines():
                                if mac in l.lower():
                                    m2 = re.search(r"(\d+\.\d+\.\d+\.\d+)", l)
                                    if m2:
                                        ip_addr = m2.group(1)
                                        break
                            if ip_addr:
                                break

                    if not ip_addr:
                        ip_addr = dhcp.get(mac) or arp.get(mac) or ""
                    if ip_addr:
                        break

                host_val = ip_addr if ip_addr else vm_name
                grp, short = _vm_name_split(vm_name)

                results.append({
                    "name":        short,
                    "host":        host_val,
                    "user":        ssh_user,
                    "port":        22,
                    "password":    "",
                    "description": f"[{state}] {vm_name} via {hv_host} (libvirt)",
                    "group":       grp,
                    "hypervisor":  hv_host,
                })
                log_fn(
                    f"  + [{grp}] {short:28s}"
                    f"  {host_val or '(IP inconnue)':16s}  [{state}]"
                )

        finally:
            client.close()

        progress_fn((idx + 1) / total, f"{idx+1}/{total} hyperviseurs traités")

    return results


# ─── ONGLET PRÉFÉRENCES ───────────────────────────────────────────────────────

class LibvirtPrefsTab:
    """
    Onglet "Libvirt" pour le Gtk.Notebook des préférences GCM.

    Instanciation (dans la méthode qui construit les prefs) :
        self._lv_prefs = LibvirtPrefsTab(notebook, config)

    Validation (dans le handler OK des prefs) :
        self._lv_prefs.apply(config)
        self.save_config()
    """

    def __init__(self, notebook, config):
        self._config = config
        self._build(notebook)

    def _build(self, notebook):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for side in ("start", "end", "top", "bottom"):
            getattr(box, f"set_margin_{side}")(14)

        # User par défaut
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        hb.pack_start(
            Gtk.Label(label="Utilisateur SSH par défaut (VMs) :"),
            False, False, 0
        )
        self._entry_user = Gtk.Entry()
        self._entry_user.set_text(
            self._config.get("libvirt_default_user", LIBVIRT_DEFAULT_USER)
        )
        self._entry_user.set_width_chars(22)
        self._entry_user.set_tooltip_text(
            "Appliqué à toutes les VMs importées.\n"
            "Peut être surchargé dans la fenêtre d'import."
        )
        hb.pack_start(self._entry_user, False, False, 0)
        box.pack_start(hb, False, False, 0)

        # Notes
        lbl = Gtk.Label()
        lbl.set_markup(
            "<b>Authentification SSH</b>\n"
            "<i>Clés testées dans l'ordre : Ed25519 → RSA → autres → agent système\n"
            "Répertoire : ~/.ssh   —   Aucun mot de passe demandé</i>\n\n"
            "<b>Groupes automatiques</b>\n"
            "<i>Premier token du nom VM (séparateur _, -, espace) → groupe MAJUSCULES\n"
            "Sans séparateur → groupe LIBVIRT\n"
            "Exemples :\n"
            "  prod-web-01    →  PROD  /  web-01\n"
            "  int_dns01      →  INT   /  dns01\n"
            "  standalone     →  LIBVIRT  /  standalone</i>"
        )
        lbl.set_xalign(0)
        box.pack_start(lbl, False, False, 0)

        box.show_all()
        notebook.append_page(box, Gtk.Label(label="Libvirt"))

    def apply(self, config):
        user = self._entry_user.get_text().strip() or "root"
        config["libvirt_default_user"] = user
        global LIBVIRT_DEFAULT_USER
        LIBVIRT_DEFAULT_USER = user


# ─── HOOKS À COPIER DANS gnome_connection_manager.py ─────────────────────────

# ── 1. Fin de Wmain.createMenu() ─────────────────────────────────────────────
_HOOK_CREATE_MENU = """
    # Import libvirt
    mnu_import_lv = Gtk.MenuItem(label=_("Importer depuis libvirt…"))
    mnu_import_lv.connect("activate", self.on_mnu_import_libvirt_activate)
    mnu_import_lv.show()
    if hasattr(self, 'menuServers') and self.menuServers is not None:
        self.menuServers.append(mnu_import_lv)
    else:
        self.menuHosts.append(mnu_import_lv)
"""

# ── 2. Handler dans class Wmain ───────────────────────────────────────────────
_HOOK_HANDLER = """
    def on_mnu_import_libvirt_activate(self, widget):
        default_user = config.get("libvirt_default_user", "root")

        def on_done(host_dicts):
            if not host_dicts:
                msgbox(_("Aucun hôte importé."))
                return
            added_by_group = {}
            for d in host_dicts:
                gname = d["group"]
                if gname not in groups:
                    groups[gname] = []
                    self.treeModel.append(None, [gname, None])
                group_iter = None
                for i in range(self.treeModel.iter_n_children(None)):
                    it = self.treeModel.iter_nth_child(None, i)
                    if self.treeModel.get_value(it, 0) == gname:
                        group_iter = it
                        break
                if d["name"] in [h.name for h in groups[gname]]:
                    continue
                h = Host()
                h.name = d["name"]; h.host = d["host"]; h.user = d["user"]
                h.port = d["port"]; h.password = ""; h.description = d["description"]
                h.log = False; h.tunnel = ""; h.options = ""
                h.X11 = False; h.agent = True; h.compression = False
                h.compressionLevel = 6; h.term = ""; h.keepAlive = 0
                h.tabColor = ""; h.fontColor = ""; h.backColor = ""
                h.font = ""; h.lineColor = ""
                groups[gname].append(h)
                if group_iter is not None:
                    self.treeModel.append(group_iter, [h.name, h])
                added_by_group[gname] = added_by_group.get(gname, 0) + 1
            self.save_config()
            if added_by_group:
                summary = ", ".join(
                    f"{n} dans {g}" for g, n in sorted(added_by_group.items())
                )
                msgbox(_(f"Import terminé : {summary}."))
            else:
                msgbox(_("Aucun nouvel hôte (doublons ignorés)."))

        LibvirtImportDialog(self.window, on_done, default_user)
"""

# ── 3. Dans Wmain.on_preferences_activate() ──────────────────────────────────
_HOOK_PREFS = """
    # Après création du Gtk.Notebook 'notebook' :
    self._lv_prefs = LibvirtPrefsTab(notebook, config)
    # Dans le handler OK :
    self._lv_prefs.apply(config)
    self.save_config()
"""


# ─── TESTS ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    cases = [
        ("prod-web-01",    ("PROD",    "web-01")),
        ("prod_db_master", ("PROD",    "db_master")),
        ("dev web front",  ("DEV",     "web front")),
        ("standalone",     ("LIBVIRT", "standalone")),
        ("INT-dns01",      ("INT",     "dns01")),
        ("A-b-c",          ("A",       "b-c")),
    ]
    print("_vm_name_split :")
    all_ok = True
    for name, expected in cases:
        got = _vm_name_split(name)
        ok = got == expected
        all_ok = all_ok and ok
        print(f"  {'✓' if ok else '✗'}  {name!r:25s} → {got}")
    print(f"{'Tous OK' if all_ok else 'ÉCHECS'}\n")
    print("Clés SSH dans ~/.ssh :")
    for k in _collect_ssh_keys():
        print(f"  {k}")
