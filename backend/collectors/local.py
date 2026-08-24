"""
Collector Local — Recursos do homelab
psutil: CPU, RAM, disco
libvirt: VMs KVM (nome, estado, vCPU, RAM alocada)
Docker: containers em execução (se disponível)
"""

import os
import subprocess
from datetime import datetime, timezone


def collect_local() -> dict:
    return {
        "resources": _get_resources(),
        "vms": _get_vms(),
        "containers": _get_containers(),
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def _get_resources() -> dict:
    try:
        import psutil

        cpu_pct = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count(logical=False)
        cpu_count_logical = psutil.cpu_count(logical=True)

        ram = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # Temperatura (se disponível — nem todos os sistemas expõem)
        temps = {}
        try:
            raw = psutil.sensors_temperatures()
            if raw:
                for name, entries in raw.items():
                    if entries:
                        temps[name] = round(entries[0].current, 1)
        except Exception:
            pass

        # Uptime
        uptime_sec = int(datetime.now().timestamp() - psutil.boot_time())
        uptime_str = _fmt_uptime(uptime_sec)

        return {
            "cpu": {
                "pct": round(cpu_pct, 1),
                "free_pct": round(100 - cpu_pct, 1),
                "cores_physical": cpu_count,
                "cores_logical": cpu_count_logical,
            },
            "ram": {
                "total_gb": round(ram.total / 1024**3, 1),
                "used_gb": round(ram.used / 1024**3, 1),
                "free_gb": round(ram.available / 1024**3, 1),
                "pct": round(ram.percent, 1),
            },
            "disk": {
                "total_gb": round(disk.total / 1024**3, 1),
                "used_gb": round(disk.used / 1024**3, 1),
                "free_gb": round(disk.free / 1024**3, 1),
                "pct": round(disk.percent, 1),
            },
            "temps": temps,
            "uptime": uptime_str,
            "error": None,
        }
    except ImportError:
        return {"error": "psutil não instalado"}
    except Exception as e:
        return {"error": str(e)}


def _get_vms() -> list:
    """Lista VMs KVM via libvirt, com fallback para virsh subprocess."""
    try:
        import libvirt

        conn = libvirt.openReadOnly("qemu:///system")
        if conn is None:
            return _get_vms_virsh()

        vms = []
        for dom_id in conn.listDomainsID():
            dom = conn.lookupByID(dom_id)
            info = dom.info()
            vms.append(_parse_vm(dom, info, running=True))

        for name in conn.listDefinedDomains():
            dom = conn.lookupByName(name)
            info = dom.info()
            vms.append(_parse_vm(dom, info, running=False))

        conn.close()
        return vms

    except ImportError:
        return _get_vms_virsh()
    except Exception:
        return _get_vms_virsh()


def _get_vms_virsh() -> list:
    """Fallback: coleta VMs via virsh subprocess."""
    try:
        # Lista todas as VMs
        r = subprocess.run(
            ["virsh", "-c", "qemu:///system", "list", "--all"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return [{"error": f"virsh: {r.stderr.strip() or 'falha ao listar VMs'}"}]

        vms = []
        lines = r.stdout.strip().splitlines()
        # Ignora as 2 linhas de cabeçalho: "Id  Name  State" e "---..."
        for line in lines[2:]:
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            name = parts[1]
            state_raw = parts[2].strip()
            running = state_raw == "running"

            # Detalhes da VM
            vcpus, ram_mb = 1, 0
            info_r = subprocess.run(
                ["virsh", "-c", "qemu:///system", "dominfo", name],
                capture_output=True, text=True, timeout=5,
            )
            for info_line in info_r.stdout.splitlines():
                if info_line.startswith("CPU(s):"):
                    try:
                        vcpus = int(info_line.split(":")[1].strip())
                    except ValueError:
                        pass
                elif info_line.startswith("Max memory:"):
                    try:
                        ram_kb = int(info_line.split(":")[1].strip().split()[0])
                        ram_mb = ram_kb // 1024
                    except ValueError:
                        pass

            mem_str = f"{ram_mb // 1024} GB" if ram_mb >= 1024 else f"{ram_mb} MB"
            vms.append({
                "name": name,
                "type": "VM",
                "vcpus": vcpus,
                "ram": mem_str,
                "ram_mb": ram_mb,
                "running": running,
                "status": "ligada" if running else "desligada",
                "error": None,
            })
        return vms

    except FileNotFoundError:
        return [{"error": "libvirt indisponível (virsh não encontrado)"}]
    except Exception as e:
        return [{"error": str(e)}]


def _parse_vm(dom, info, running: bool) -> dict:
    """Extrai informações de uma VM libvirt."""
    # info[1] = maxMemory (KB), info[3] = nrVirtCpu
    max_mem_mb = info[1] // 1024
    vcpus = info[3]

    mem_str = (
        f"{max_mem_mb // 1024} GB" if max_mem_mb >= 1024 else f"{max_mem_mb} MB"
    )

    return {
        "name": dom.name(),
        "type": "VM",
        "vcpus": vcpus,
        "ram": mem_str,
        "ram_mb": max_mem_mb,
        "running": running,
        "status": "ligada" if running else "desligada",
        "error": None,
    }


def _get_containers() -> list:
    """Lista containers Docker em execução."""
    containers = []
    try:
        result = subprocess.run(
            [
                "docker", "ps",
                "--format",
                '{"name":"{{.Names}}","image":"{{.Image}}","status":"{{.Status}}","ports":"{{.Ports}}"}',
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []

        import json
        for line in result.stdout.strip().splitlines():
            if line:
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    except FileNotFoundError:
        pass  # Docker não instalado — silencioso
    except Exception:
        pass

    return containers


def _fmt_uptime(seconds: int) -> str:
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    elif hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"
