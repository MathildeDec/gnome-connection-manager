#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
gcm_import_libvirt.py
=====================
Patch à intégrer dans gnome_connection_manager.py pour ajouter
une fonction "Importer depuis libvirt" dans le menu Fichier/Serveurs.

INTÉGRATION :
  1. Copier les imports (section "IMPORTS SUPPLÉMENTAIRES") en haut du fichier,
     avec les autres imports.
  2. Copier la classe LibvirtImportDialog et la fonction import_from_libvirt()
     quelque part AVANT la classe Wmain.
  3. Copier les deux morceaux "HOOK Wmain" dans la classe Wmain :
       a. L'appel dans createMenu()  →  après la création du menu existant
       b. Le handler on_mnu_import_libvirt_activate()  →  parmi les autres handlers

"""

# ─── IMPORTS SUPPLÉMENTAIRES ─────────────────────────────────────────────────
# À ajouter avec les imports existants en haut du fichier

import subprocess
import re
import threading
from urllib.parse import urlparse

try:
    import paramiko
    _PARAMIKO_OK = True
except ImportError:
    _PARAMIKO_OK = False


# ─── DIALOGUE + LOGIQUE D'IMPORT ─────────────────────────────────────────────
# À coller AVANT la classe Wmain

class LibvirtImportDialog:
    """
    Boîte de dialogue qui :
      - liste les hyperviseurs connus de virt-manager (via dconf)
      - lance l'import en arrière-plan
      - affiche une progressbar + log
    """

    def __init__(self, parent_window, on_done_callback):
        self.parent = parent_window
        self.on_done = on_done_callback
        self._build_ui()

    def _build_ui(self):
        dlg = Gtk.Dialog(title="Importer depuis libvirt", transient_for=self.parent, modal=True)
        dlg.set_default_size(560, 420)
        dlg.add_button("_Annuler", Gtk.ResponseType.CANCEL)
        self._btn_import = dlg.add_button("_Importer", Gtk.ResponseType.OK)
        self._btn_import.get_style_context().add_class("suggested-action")

        box = dlg.get_content_area()
        box.set_spacing(6)
        box.set_margin_start(12); box.set_margin_end(12)
        box.set_margin_top(12);   box.set_margin_bottom(12)

        hbox_grp = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hbox_grp.pack_start(Gtk.Label(label="Groupe cible :"), False, False, 0)
        self._entry_group = Gtk.Entry()
        self._entry_group.set_text("libvirt")
        self._entry_group.set_tooltip_text("Nom du groupe GCM dans lequel les hôtes seront créés")
        hbox_grp.pack_start(self._entry_group, True, True, 0)
        box.pack_start(hbox_grp, False, False, 0)

        box.pack_start(Gtk.Label(label="Hyperviseurs détectés (virt-manager) :"), False, False, 4)

        self._uri_store = Gtk.ListStore(bool, str)
        tv = Gtk.TreeView(model=self._uri_store)
        tv.set_headers_visible(True)
        cr_toggle = Gtk.CellRendererToggle()
        cr_toggle.connect("toggled", self._on_uri_toggled)
        tv.append_column(Gtk.TreeViewColumn("", cr_toggle, active=0))
        tv.append_column(Gtk.TreeViewColumn("URI libvirt", Gtk.CellRendererText(), text=1))

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.set_min_content_height(100)
        sw.add(tv)
        box.pack_start(sw, True, True, 0)

        self._log_buf = Gtk.TextBuffer()
        log_view = Gtk.TextView(buffer=self._log_buf)
        log_view.set_editable(False); log_view.set_monospace(True)
        log_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw_log = Gtk.ScrolledWindow()
        sw_log.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw_log.set_min_content_height(80)
        sw_log.add(log_view)
        box.pack_start(sw_log, True, True, 0)
        self._log_view = log_view

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
        for uri in uris:
            parsed = urlparse(uri)
            self._uri_store.append([bool(parsed.hostname), uri])
        if not uris:
            self._uri_store.append([True, "qemu+ssh://root@hyperviseur/system"])

    def _on_uri_toggled(self, renderer, path):
        self._uri_store[path][0] = not self._uri_store[path][0]

    def _log(self, msg: str):
        def _do():
            self._log_buf.insert(self._log_buf.get_end_iter(), msg + "\n")
            adj = self._log_view.get_vadjustment()
            adj.set_value(adj.get_upper())
        GLib.idle_add(_do)

    def _set_progress(self, fraction: float, text: str):
        GLib.idle_add(lambda: (self._progress.set_fraction(fraction), self._progress.set_text(text)))

    def _on_response(self, dlg, response_id):
        if response_id == Gtk.ResponseType.OK:
            self._run_import()
        else:
            dlg.destroy()

    def _run_import(self):
        self._btn_import.set_sensitive(False)
        selected_uris = [row[1] for row in self._uri_store if row[0]]
        if not selected_uris:
            self._log("Aucune URI sélectionnée.")
            self._btn_import.set_sensitive(True)
            return
        group_name = self._entry_group.get_text().strip() or "libvirt"
        def worker():
            results = _libvirt_fetch_hosts(selected_uris, self._log, self._set_progress)
            GLib.idle_add(self._finish, group_name, results)
        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, group_name: str, host_dicts: list):
        self._set_progress(1.0, f"{len(host_dicts)} hôte(s) importé(s)")
        self._log(f"\nTerminé. {len(host_dicts)} hôte(s) à ajouter dans le groupe '{group_name}'.")
        self.on_done(group_name, host_dicts)
        self._btn_import.set_label("Fermer")
        self._btn_import.set_sensitive(True)
        self._dlg.disconnect_by_func(self._on_response)
        self._dlg.connect("response", lambda d, r: d.destroy())


# ─── FONCTIONS UTILITAIRES LIBVIRT ───────────────────────────────────────────

def _libvirt_get_uris_from_dconf() -> list:
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


def _libvirt_ssh_run(client, cmd: str, timeout: int = 30) -> str:
    _, stdout, _ = client.exec_command(cmd, timeout=timeout)
    return stdout.read().decode(errors="replace").strip()


def _libvirt_fetch_hosts(uris: list, log_fn, progress_fn) -> list:
    if not _PARAMIKO_OK:
        log_fn("ERREUR : paramiko non installé (pip install paramiko)")
        return []

    results = []
    total = len(uris)

    for idx, uri in enumerate(uris):
        log_fn(f"\n── Hyperviseur : {uri}")
        progress_fn(idx / total, f"Connexion à {uri}…")

        parsed = urlparse(uri)
        scheme = parsed.scheme
        transport = scheme.split("+")[1] if "+" in scheme else ("tcp" if parsed.hostname else "local")
        hv_host = parsed.hostname or "localhost"
        hv_port = parsed.port or 22
        hv_user = parsed.username or ""

        if transport == "local":
            log_fn("  → Connexion locale ignorée.")
            continue

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            kw = dict(hostname=hv_host, port=hv_port, timeout=10, look_for_keys=True, allow_agent=True)
            if hv_user:
                kw["username"] = hv_user
            client.connect(**kw)
            log_fn(f"  SSH OK → {hv_user+'@' if hv_user else ''}{hv_host}:{hv_port}")
        except Exception as e:
            log_fn(f"  ERREUR SSH : {e}")
            continue

        try:
            raw_names = _libvirt_ssh_run(client, "virsh list --all --name")
            vm_names = [n for n in raw_names.splitlines() if n.strip()]
            log_fn(f"  {len(vm_names)} VM(s) trouvée(s)")

            arp: dict = {}
            for line in _libvirt_ssh_run(client, "ip neigh show 2>/dev/null || arp -n 2>/dev/null").splitlines():
                m = re.search(r"(\d+\.\d+\.\d+\.\d+).*?([0-9a-f]{2}(?::[0-9a-f]{2}){5})", line, re.I)
                if m:
                    arp[m.group(2).lower()] = m.group(1)

            dhcp: dict = {}
            for net in _libvirt_ssh_run(client, "virsh net-list --name").splitlines():
                net = net.strip()
                if not net:
                    continue
                for line in _libvirt_ssh_run(client, f"virsh net-dhcp-leases {net} 2>/dev/null").splitlines():
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
                            out = _libvirt_ssh_run(client, f"virsh domifaddr {vm_name} --source {src} 2>/dev/null")
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
                results.append({
                    "name": vm_name, "host": host_val, "user": "", "port": 22,
                    "password": "", "description": f"[{state}] via {hv_host} (libvirt import)",
                    "hypervisor": hv_host,
                })
                log_fn(f"  + {vm_name:30s}  {host_val or '(IP inconnue)':16s}  [{state}]")
        finally:
            client.close()

        progress_fn((idx + 1) / total, f"{idx+1}/{total} hyperviseurs traités")

    return results


# ─── HOOK Wmain ── À intégrer dans gnome_connection_manager.py ───────────────

# 1. Fin de createMenu() :
_HOOK_CREATE_MENU = """
    mnu_import_lv = Gtk.MenuItem(label=_("Importer depuis libvirt…"))
    mnu_import_lv.connect("activate", self.on_mnu_import_libvirt_activate)
    mnu_import_lv.show()
    if hasattr(self, 'menuServers') and self.menuServers is not None:
        self.menuServers.append(mnu_import_lv)
    else:
        self.menuHosts.append(mnu_import_lv)
"""

# 2. Handler dans class Wmain :
_HOOK_HANDLER = """
    def on_mnu_import_libvirt_activate(self, widget):
        def on_done(group_name, host_dicts):
            if not host_dicts:
                msgbox(_("Aucun hôte importé."))
                return
            if group_name not in groups:
                groups[group_name] = []
                self.treeModel.append(None, [group_name, None])
            group_iter = None
            for i in range(self.treeModel.iter_n_children(None)):
                it = self.treeModel.iter_nth_child(None, i)
                if self.treeModel.get_value(it, 0) == group_name:
                    group_iter = it
                    break
            added = 0
            for d in host_dicts:
                if d["name"] in [h.name for h in groups[group_name]]:
                    continue
                h = Host()
                h.name = d["name"]; h.host = d["host"]; h.user = d["user"]
                h.port = d["port"]; h.password = ""; h.description = d["description"]
                h.log = False; h.tunnel = ""; h.options = ""; h.X11 = False
                h.agent = False; h.compression = False; h.compressionLevel = 6
                h.term = ""; h.keepAlive = 0; h.tabColor = ""; h.fontColor = ""
                h.backColor = ""; h.font = ""; h.lineColor = ""
                groups[group_name].append(h)
                if group_iter is not None:
                    self.treeModel.append(group_iter, [h.name, h])
                added += 1
            self.save_config()
            msgbox(_(f"{added} hôte(s) ajouté(s) dans le groupe '{group_name}'."))
        LibvirtImportDialog(self.window, on_done)
"""
