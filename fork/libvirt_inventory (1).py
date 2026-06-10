#!/usr/bin/env python3
"""
libvirt_inventory.py — v2 (avec nmap)
Récupère les connexions virt-manager via dconf, se connecte en SSH aux hyperviseurs,
liste les VMs avec leurs MAC adresses et résout les IPs via ARP/DHCP leases + nmap -sP.
"""

import subprocess
import re
import sys
import json
import logging
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

try:
    import paramiko
except ImportError:
    print("Dépendance manquante : pip install paramiko")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger(__name__)

@dataclass
class Interface:
    mac: str
    ip: Optional[str] = None
    source_network: Optional[str] = None

@dataclass
class VM:
    name: str
    uuid: str
    state: str
    interfaces: list[Interface] = field(default_factory=list)

@dataclass
class Hypervisor:
    uri: str
    host: str
    user: str
    port: int
    transport: str
    vms: list[VM] = field(default_factory=list)

def get_libvirt_uris() -> list[str]:
    try:
        result = subprocess.run(["dconf", "read", "/org/virt-manager/virt-manager/connections/uris"], capture_output=True, text=True, check=True)
        raw = result.stdout.strip()
        if not raw or raw == "@as []":
            log.warning("Aucune URI trouvée dans dconf."); return []
        uris = re.findall(r"'([^']+)'", raw)
        log.info(f"{len(uris)} URI(s) trouvée(s) : {uris}")
        return uris
    except FileNotFoundError:
        log.error("dconf introuvable."); return []
    except subprocess.CalledProcessError as e:
        log.error(f"Erreur dconf : {e.stderr}"); return []

def parse_libvirt_uri(uri: str) -> Optional[Hypervisor]:
    parsed = urlparse(uri)
    scheme = parsed.scheme
    transport = scheme.split("+")[1] if "+" in scheme else ("tcp" if parsed.hostname else "local")
    return Hypervisor(uri=uri, host=parsed.hostname or "localhost", user=parsed.username or "", port=parsed.port or 22, transport=transport)

def ssh_connect(host, user, port=22, password=None, timeout=10):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = dict(hostname=host, port=port, timeout=timeout, look_for_keys=True, allow_agent=True)
    if user: kwargs["username"] = user
    if password: kwargs.update(password=password, look_for_keys=False, allow_agent=False)
    try:
        client.connect(**kwargs); return client
    except Exception as e:
        log.error(f"Connexion échouée {host} : {e}"); return None

def ssh_run(client, cmd, timeout=30):
    _, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace").strip()
    err = stderr.read().decode(errors="replace").strip()
    if err: log.debug(f"stderr: {err}")
    return out

def get_vms(client):
    out = ssh_run(client, "virsh list --all --name")
    names = [n for n in out.splitlines() if n.strip()]
    vms = []
    for name in names:
        uuid = ssh_run(client, f"virsh domuuid {name}").strip()
        state = ssh_run(client, f"virsh domstate {name}").strip()
        vms.append(VM(name=name, uuid=uuid, state=state))
    log.info(f"  {len(vms)} VM(s) trouvée(s)")
    return vms

def get_interfaces(client, vm):
    xml = ssh_run(client, f"virsh dumpxml {vm.name}")
    interfaces = []
    for block in re.findall(r"<interface.*?</interface>", xml, re.DOTALL):
        mac_m = re.search(r"<mac address=['\"]([^'\"]+)['\"]", block)
        net_m = re.search(r"<source (?:network|bridge|dev)=['\"]([^'\"]+)['\"]", block)
        if mac_m:
            interfaces.append(Interface(mac=mac_m.group(1), source_network=net_m.group(1) if net_m else None))
    return interfaces

def get_host_subnets(client):
    out = ssh_run(client, "ip -o -f inet addr show")
    subnets, seen = [], set()
    for line in out.splitlines():
        m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/(\d+)", line)
        if not m: continue
        ip_str, prefix = m.group(1), int(m.group(2))
        if ip_str.startswith("127.") or ip_str.startswith("169.254."): continue
        ip_parts = list(map(int, ip_str.split(".")))
        mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        net_int = 0
        for part in ip_parts: net_int = (net_int << 8) | part
        net_int &= mask
        net_parts = [(net_int >> (8 * i)) & 0xFF for i in reversed(range(4))]
        cidr = f"{'.'.join(map(str, net_parts))}/{prefix}"
        if cidr not in seen:
            seen.add(cidr); subnets.append(cidr)
            log.info(f"    Sous-réseau : {cidr}")
    return subnets

def nmap_ping_scan(client, subnets):
    result = {}
    if not subnets: return result
    if not ssh_run(client, "which nmap 2>/dev/null"):
        log.warning("  nmap non disponible."); return result
    nmap_ver = ssh_run(client, "nmap --version 2>/dev/null | head -1")
    ver_m = re.search(r"Nmap version (\d+)", nmap_ver)
    flag = "-sn" if ver_m and int(ver_m.group(1)) >= 6 else "-sP"
    for cidr in subnets:
        log.info(f"  nmap {flag} {cidr}…")
        xml_out = ssh_run(client, f"nmap {flag} {cidr} -oX - --host-timeout 5s 2>/dev/null", timeout=300)
        if not xml_out: continue
        count = 0
        for host_block in re.findall(r"<host\b.*?</host>", xml_out, re.DOTALL):
            ip_m  = re.search(r'<address addr="([^"]+)" addrtype="ipv4"', host_block)
            mac_m = re.search(r'<address addr="([^"]+)" addrtype="mac"',  host_block)
            if ip_m and mac_m:
                result[mac_m.group(1).lower()] = ip_m.group(1); count += 1
        log.info(f"    {count} hôte(s) avec MAC sur {cidr}")
    return result

def build_arp_table(client):
    arp = {}
    for line in ssh_run(client, "ip neigh show 2>/dev/null || arp -n 2>/dev/null").splitlines():
        m = re.search(r"(\d+\.\d+\.\d+\.\d+).*?([0-9a-f]{2}(?::[0-9a-f]{2}){5})", line, re.I)
        if m: arp[m.group(2).lower()] = m.group(1)
    return arp

def build_dhcp_table(client):
    leases = {}
    for net in ssh_run(client, "virsh net-list --name").splitlines():
        net = net.strip()
        if not net: continue
        for line in ssh_run(client, f"virsh net-dhcp-leases {net} 2>/dev/null").splitlines():
            parts = line.split()
            if len(parts) >= 4:
                mac_c = parts[1] if ":" in parts[1] else None
                ip_c  = parts[3].split("/")[0]
                if mac_c and re.match(r"\d+\.\d+\.\d+\.\d+", ip_c):
                    leases[mac_c.lower()] = ip_c
    return leases

def resolve_ips(client, vms):
    for vm in vms:
        if vm.state != "running": continue
        for method in ("agent", "arp"):
            out = ssh_run(client, f"virsh domifaddr {vm.name} --source {method} 2>/dev/null")
            for iface in vm.interfaces:
                if iface.ip: continue
                for line in out.splitlines():
                    if iface.mac.lower() in line.lower():
                        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                        if m: iface.ip = m.group(1); break
    subnets = get_host_subnets(client)
    nmap_table = nmap_ping_scan(client, subnets)
    dhcp = build_dhcp_table(client)
    arp  = build_arp_table(client)
    combined = {**arp, **dhcp, **nmap_table}
    log.info(f"  Table MAC→IP fusionnée : {len(combined)} entrées")
    for vm in vms:
        for iface in vm.interfaces:
            if iface.ip: continue
            iface.ip = combined.get(iface.mac.lower())
            if iface.ip: log.info(f"    {vm.name} / {iface.mac} → {iface.ip}")

def print_report(hypervisors):
    print("\n" + "═"*60 + "\n  INVENTAIRE LIBVIRT\n" + "═"*60)
    for hv in hypervisors:
        print(f"\n🖥  Hyperviseur : {hv.host}  ({hv.uri})")
        for vm in hv.vms:
            print(f"\n  {'▶' if vm.state=='running' else '■'} {vm.name}  [{vm.state}]  uuid={vm.uuid}")
            for iface in vm.interfaces:
                net = f"  réseau={iface.source_network}" if iface.source_network else ""
                print(f"      MAC {iface.mac}  →  {iface.ip or 'IP inconnue'}{net}")
    print("\n" + "═"*60)

def export_json(hypervisors, path="inventory.json"):
    data = [{"host": hv.host, "uri": hv.uri, "vms": [{"name": vm.name, "uuid": vm.uuid, "state": vm.state, "interfaces": [{"mac": i.mac, "ip": i.ip, "network": i.source_network} for i in vm.interfaces]} for vm in hv.vms]} for hv in hypervisors]
    with open(path, "w") as f: json.dump(data, f, indent=2, ensure_ascii=False)
    log.info(f"Inventaire exporté → {path}")

def main():
    uris = get_libvirt_uris()
    # uris = ["qemu+ssh://root@proxmox01/system"]  # override manuel
    if not uris: log.error("Aucune URI trouvée."); sys.exit(1)
    hypervisors = []
    for uri in uris:
        hv = parse_libvirt_uri(uri)
        if not hv or hv.transport == "local": continue
        log.info(f"Traitement de {hv.host}…")
        client = ssh_connect(hv.host, hv.user, hv.port)
        if not client: continue
        try:
            hv.vms = get_vms(client)
            for vm in hv.vms: vm.interfaces = get_interfaces(client, vm)
            resolve_ips(client, hv.vms)
        finally:
            client.close()
        hypervisors.append(hv)
    print_report(hypervisors)
    export_json(hypervisors)

if __name__ == "__main__":
    main()
