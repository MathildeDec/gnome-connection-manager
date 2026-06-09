#!/usr/bin/env python3
# -*- coding: UTF-8 -*-
"""
gcm_rdp.py
==========
Patch RDP pour gnome_connection_manager.py (kuthulux/gnome-connection-manager).

PRINCIPE :
  GCM utilise VTE (terminal) pour SSH/Telnet. RDP ne peut pas s'exécuter
  dans un terminal VTE. Ce patch adopte l'approche suivante :
    - Un hôte avec protocol="rdp" ouvre xfreerdp dans une fenêtre externe
      via subprocess.Popen (pas de VTE, pas de expect).
    - L'onglet GCM reste présent et affiche un panneau de statut
      (connecté / déconnecté / reconnecter).
    - Le champ `options` de Host stocke les paramètres xfreerdp
      supplémentaires (ex: /drive:home,/home/user /sound:sys:alsa).

CHAMPS Host utilisés :
  host        → IP / hostname
  user        → utilisateur RDP (domaine\\utilisateur ou juste utilisateur)
  password    → mot de passe RDP (chiffré comme SSH dans GCM)
  port        → port RDP (défaut 3389)
  options     → paramètres xfreerdp additionnels (chaîne libre)
  description → description affichée
  protocol    → "rdp"  (nouveau champ à ajouter à la classe Host)

INTÉGRATION (6 points) :
  1. Constante RDP_BIN + import shutil → dans les définitions globales
  2. Champ protocol sur la classe Host (+ clone + sérialisation)
  3. Classe RdpTab → avant class Wmain
  4. Modifier addTab() → détecter protocol=="rdp" → _open_rdp_tab()
  5. Méthode _open_rdp_tab() → dans class Wmain
  6. ComboBox Protocol dans le dialogue d'édition host

DÉPENDANCE : xfreerdp  (paquet freerdp2-x11 ou freerdp3-x11)
  sudo apt install freerdp2-x11
"""

import os
import subprocess
import shutil

# ─── CONSTANTE GLOBALE ────────────────────────────────────────────────────────
# À ajouter avec SSH_BIN / TEL_BIN dans les globales de GCM

RDP_BIN = shutil.which("xfreerdp") or shutil.which("xfreerdp3") or "xfreerdp"


# ─── CHAMP protocol SUR Host ─────────────────────────────────────────────────
_HOST_PROTOCOL_FIELD = """
    # Dans __init__ de Host (ou après instanciation) :
    self.protocol = "ssh"   # "ssh" | "telnet" | "rdp" | "local"

    # Dans clone() :
    newhost.protocol = self.protocol

    # Dans writeConfig, dans la boucle de sérialisation des hosts :
    config.set(section, 'protocol', host.protocol if hasattr(host, 'protocol') else 'ssh')

    # Dans readConfig :
    host.protocol = config.get(section, 'protocol') if config.has_option(section, 'protocol') else 'ssh'
"""


# ─── ONGLET RDP ───────────────────────────────────────────────────────────────

class RdpTab(Gtk.Box):
    """
    Widget affiché dans le Gtk.Notebook de GCM à la place du VTE terminal
    pour les connexions RDP.

    Affiche :
      - Infos de connexion (host, user, port)
      - Bouton Connecter / Déconnecter
      - Statut (En attente / Connexion en cours / Connecté / Déconnecté)
      - Sortie stderr de xfreerdp (log)
      - Champ options xfreerdp modifiable à la volée

    La fenêtre xfreerdp est externe (non embarquée dans GCM).
    """

    def __init__(self, host, get_password_fn):
        """
        host            : objet Host GCM
        get_password_fn : callable() → str  (déchiffrement du mot de passe)
        """
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.host          = host
        self._get_password = get_password_fn
        self._proc         = None

        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_margin_top(16)
        self.set_margin_bottom(16)

        self._build_ui()

    def _build_ui(self):
        h    = self.host
        port = getattr(h, 'port', 3389) or 3389

        # Titre
        title = Gtk.Label()
        title.set_markup(
            f"<b>RDP — {h.name}</b>"
            f"<small>   {h.user}@{h.host}:{port}</small>"
        )
        title.set_xalign(0)
        self.pack_start(title, False, False, 0)

        if h.description:
            d = Gtk.Label(label=h.description)
            d.set_xalign(0)
            d.get_style_context().add_class("dim-label")
            self.pack_start(d, False, False, 0)

        self.pack_start(Gtk.Separator(), False, False, 4)

        # Statut
        self._lbl_status = Gtk.Label(label="⏳ En attente")
        self._lbl_status.set_xalign(0)
        self.pack_start(self._lbl_status, False, False, 0)

        # Boutons
        hb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self._btn_connect = Gtk.Button(label="🖥  Connecter")
        self._btn_connect.get_style_context().add_class("suggested-action")
        self._btn_connect.connect("clicked", self._on_connect)
        hb.pack_start(self._btn_connect, False, False, 0)

        self._btn_disconnect = Gtk.Button(label="✖  Déconnecter")
        self._btn_disconnect.set_sensitive(False)
        self._btn_disconnect.connect("clicked", self._on_disconnect)
        hb.pack_start(self._btn_disconnect, False, False, 0)
        self.pack_start(hb, False, False, 0)

        self.pack_start(Gtk.Separator(), False, False, 4)

        # Options xfreerdp
        hb2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        hb2.pack_start(Gtk.Label(label="Options xfreerdp :"), False, False, 0)
        self._entry_opts = Gtk.Entry()
        self._entry_opts.set_text(getattr(h, 'options', '') or '')
        self._entry_opts.set_tooltip_text(
            "Paramètres additionnels xfreerdp\n"
            "Ex : /drive:home,/home/user  /sound:sys:alsa  /multimon  +clipboard"
        )
        hb2.pack_start(self._entry_opts, True, True, 0)
        self.pack_start(hb2, False, False, 0)

        # Log
        self.pack_start(Gtk.Label(label="Journal xfreerdp :"), False, False, 2)
        self._log_buf = Gtk.TextBuffer()
        lv = Gtk.TextView(buffer=self._log_buf)
        lv.set_editable(False)
        lv.set_monospace(True)
        lv.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        sw = Gtk.ScrolledWindow()
        sw.set_min_content_height(160)
        sw.add(lv)
        self.pack_start(sw, True, True, 0)
        self._log_view = lv

        self.show_all()

    # ── Connexion ─────────────────────────────────────────────────────────────

    def _build_cmd(self) -> list:
        h    = self.host
        port = getattr(h, 'port', 3389) or 3389
        pwd  = self._get_password() or ""
        opts = self._entry_opts.get_text().strip()
        user = h.user

        # Décomposer DOMAIN\\user si présent
        if "\\" in user:
            domain, uname = user.split("\\", 1)
            cmd = [RDP_BIN, f"/v:{h.host}:{port}", f"/d:{domain}", f"/u:{uname}"]
        else:
            cmd = [RDP_BIN, f"/v:{h.host}:{port}", f"/u:{user}"]

        if pwd:
            cmd.append(f"/p:{pwd}")

        cmd += [
            "/cert:ignore",        # ne pas bloquer sur erreur cert
            "/dynamic-resolution", # adapter à la taille de fenêtre
        ]

        if opts:
            import shlex
            cmd += shlex.split(opts)

        return cmd

    def _on_connect(self, widget):
        if self._proc is not None and self._proc.poll() is None:
            return  # déjà en cours
        cmd = self._build_cmd()
        # Masquer le mot de passe dans le log
        cmd_display = [
            "****" if a.startswith("/p:") else a for a in cmd
        ]
        self._log(f"$ {' '.join(cmd_display)}\n")

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
        except FileNotFoundError:
            self._log(
                f"ERREUR : xfreerdp introuvable ({RDP_BIN})\n"
                "  sudo apt install freerdp2-x11\n"
            )
            self._set_status("❌ xfreerdp introuvable")
            return

        self._set_status("🔄 Connexion en cours…")
        self._btn_connect.set_sensitive(False)
        self._btn_disconnect.set_sensitive(True)

        import threading
        threading.Thread(target=self._read_output, daemon=True).start()

    def _on_disconnect(self, widget):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
        self._set_status("🔌 Déconnecté")
        self._btn_connect.set_sensitive(True)
        self._btn_disconnect.set_sensitive(False)

    def _read_output(self):
        try:
            for line in self._proc.stdout:
                GLib.idle_add(self._log, line)
        except Exception:
            pass
        rc = self._proc.wait()
        if rc == 0:
            GLib.idle_add(self._set_status, "✅ Session terminée")
        else:
            GLib.idle_add(self._set_status, f"❌ Terminé avec code {rc}")
        GLib.idle_add(self._btn_connect.set_sensitive, True)
        GLib.idle_add(self._btn_disconnect.set_sensitive, False)

    def _log(self, text):
        self._log_buf.insert(self._log_buf.get_end_iter(), text)
        adj = self._log_view.get_vadjustment()
        adj.set_value(adj.get_upper())

    def _set_status(self, text):
        self._lbl_status.set_text(text)

    def connect_rdp(self):
        """Lancer la connexion automatiquement depuis addTab()."""
        self._on_connect(None)


# ─── HOOKS À COPIER DANS gnome_connection_manager.py ─────────────────────────

# 1. Début de Wmain.addTab(), avant tout traitement SSH/VTE :
_HOOK_ADDTAB = """
    # ── RDP ──────────────────────────────────────────────────────────────────
    if isinstance(host, Host) and getattr(host, 'protocol', 'ssh') == 'rdp':
        return self._open_rdp_tab(notebook, host)
"""

# 2. Nouvelle méthode dans class Wmain :
_HOOK_RDP_METHOD = """
    def _open_rdp_tab(self, notebook, host):
        \"\"\"Ouvre un onglet RDP (xfreerdp externe) dans le notebook GCM.\"\"\"
        def get_pwd():
            try:
                return decrypt(get_password(), host.password)
            except Exception:
                return ""

        rdp_widget = RdpTab(host, get_pwd)

        sw = Gtk.ScrolledWindow()
        sw.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        sw.add(rdp_widget)
        sw.show_all()

        lbl = Gtk.Label(label=f" {host.name} ")
        notebook.append_page(sw, lbl)
        notebook.set_tab_reorderable(sw, True)
        notebook.set_current_page(notebook.get_n_pages() - 1)

        rdp_widget.connect_rdp()
        return sw
"""

# 3. Dialogue d'édition host — ComboBox Protocol :
_HOOK_EDIT_DIALOG = """
    # Dans la méthode de construction du formulaire host :

    cmb_protocol = Gtk.ComboBoxText()
    for p in ("ssh", "telnet", "rdp", "local"):
        cmb_protocol.append_text(p)
    cmb_protocol.set_active(
        ["ssh", "telnet", "rdp", "local"].index(
            getattr(host, 'protocol', 'ssh') if host else 'ssh'
        )
    )

    def _on_proto_changed(cmb):
        proto = cmb.get_active_text()
        defaults = {"ssh": "22", "telnet": "23", "rdp": "3389", "local": ""}
        current_port = entry_port.get_text()
        if current_port in ("22", "23", "3389", ""):
            entry_port.set_text(defaults.get(proto, ""))

    cmb_protocol.connect("changed", _on_proto_changed)

    # À la validation :
    host.protocol = cmb_protocol.get_active_text()
"""

# 4. Classe Host — champ protocol :
_HOST_PATCH = """
    # Dans Host.__init__() :
    self.protocol = "ssh"

    # Dans Host.clone() :
    newhost.protocol = self.protocol

    # Dans writeConfig (boucle hosts) :
    config.set(section, 'protocol', getattr(host, 'protocol', 'ssh'))

    # Dans readConfig (boucle hosts) :
    host.protocol = config.get(section, 'protocol') if config.has_option(section, 'protocol') else 'ssh'
"""

# 5. Import libvirt v2 — détection Windows automatique :
_HOOK_LIBVIRT_WINDOWS = """
    # Dans _libvirt_fetch_hosts(), après xml = _libvirt_ssh_run(...dumpxml...):
    is_windows = bool(re.search(
        r'win|w(?:2k|2019|2022|2016|2012|srv|dc|server)',
        vm_name, re.IGNORECASE
    ))
    protocol = "rdp" if is_windows else "ssh"
    port     = 3389  if is_windows else 22
    vm_user  = "Administrator" if is_windows else ssh_user

    # Puis dans le dict results.append({...}) :
    #   "protocol": protocol,
    #   "port":     port,
    #   "user":     vm_user,
"""


if __name__ == "__main__":
    print(__doc__)
    rdp = shutil.which("xfreerdp") or shutil.which("xfreerdp3")
    print(f"\nxfreerdp détecté : {rdp or 'NON TROUVÉ — sudo apt install freerdp2-x11'}")
