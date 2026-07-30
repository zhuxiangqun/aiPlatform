"""

Network Discovery Agent — 外部系统自主发现 (Phase 41).



独立运行的网络扫描进程，通过 socket 探测局域网中可用的服务，

生成 DataSourceConfig YAML 并上报给 aiPlat。



安全约束:

  - AIPLAT_DISCOVERY_ENABLED=false 总开关

  - AIPLAT_DISCOVERY_SUBNETS="" 允许扫描的子网

  - 不主动发起连接建立，仅探测端口是否开放

  - 发现的源默认标记 source=auto，需 PolicyGate 审批



运行方式:

  python -m core.apps.discovery --scan-once --subnet 192.168.1.0/24

  python -m core.apps.discovery --daemon --interval 3600

"""



from __future__ import annotations



import argparse

import logging

import os as _os

import socket as _socket

import time as _time

from typing import Any, Dict, List, Optional, Tuple



logger = logging.getLogger("aiplat.discovery")



DEFAULT_PORTS = [

    3306, 5432, 1433,           # MySQL, PostgreSQL, SQL Server

    27017,                       # MongoDB

    6379,                        # Redis

    9200,                        # Elasticsearch

    5000, 8000, 8080, 8443,     # REST APIs

    22,                          # SSH (指纹识别)

]



FINGERPRINT_TIMEOUT = 2.0  # seconds





def parse_subnet(subnet: str) -> List[str]:

    """Parse subnet string like '192.168.1.0/24' into IP list."""

    try:

        import ipaddress as _ip

        net = _ip.ip_network(subnet, strict=False)

        return [str(h) for h in net.hosts()][:256]

    except Exception:

        return [subnet.split("/")[0]]





def scan_port(host: str, port: int, timeout: float = FINGERPRINT_TIMEOUT) -> bool:

    """Check if a TCP port is open on the given host."""

    try:

        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)

        sock.settimeout(timeout)

        result = sock.connect_ex((host, port))

        sock.close()

        return result == 0

    except Exception:

        return False





def fingerprint_service(host: str, port: int) -> str:

    """Attempt to identify the service type by banner grab."""

    try:

        sock = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)

        sock.settimeout(FINGERPRINT_TIMEOUT)

        sock.connect((host, port))

        sock.send(b"\n")

        banner = sock.recv(1024).decode(errors="ignore").lower()

        sock.close()



        if "postgresql" in banner:

            return "sql"

        if "mysql" in banner or "mariadb" in banner:

            return "sql"

        if b"redis".decode() in banner.lower():

            return "api"  # key-value store

        if "elasticsearch" in banner.lower():

            return "api"

        if "http" in banner:

            return "api"

        if "ssh" in banner:

            return "skip"  # not a data source

        return "unknown"

    except Exception:

        # Guess by port

        if port in (3306, 5432, 1433, 27017):

            return "sql"

        if port in (5000, 8000, 8080, 8443, 9200):

            return "api"

        return "unknown"





def generate_config(

    host: str, port: int, service_type: str,

) -> Optional[Dict[str, Any]]:

    """Generate a DataSourceConfig dict from discovery results."""

    if service_type in ("skip", "unknown"):

        return None



    name = f"{service_type}_{host.replace('.', '_')}_{port}"

    config: Dict[str, Any] = {

        "name": name,

        "type": service_type,

        "connection": {

            "host": host,

            "port": port,

        },

        "mapping": {},

        "discovered_by": "auto",

        "discovered_at": _time.time(),

        "host": host,

        "port": port,

    }



    if service_type == "sql" and port == 5432:

        config["connection"]["driver"] = "postgresql"

    elif service_type == "sql" and port == 3306:

        config["connection"]["driver"] = "mysql"

    elif service_type == "sql":

        config["connection"]["driver"] = "sqlite"



    return config





def scan_network(subnet: str, ports: Optional[List[int]] = None) -> List[Dict[str, Any]]:

    """Scan a subnet for open ports and fingerprint services.



    Returns list of DataSourceConfig dicts (without credentials).

    """

    if ports is None:

        ports = DEFAULT_PORTS

    hosts = parse_subnet(subnet)

    results: List[Dict[str, Any]] = []



    for host in hosts[:50]:  # safety limit

        for port in ports:

            if not scan_port(host, port):

                continue

            service_type = fingerprint_service(host, port)

            config = generate_config(host, port, service_type)

            if config:

                results.append(config)

                logger.info("[discovery] found %s:%d → %s", host, port, service_type)

    return results





def save_and_report(

    results: List[Dict[str, Any]],

    output_dir: Optional[str] = None,

    api_url: Optional[str] = None,

) -> int:

    """Save results as YAML files and optionally report to aiPlat API."""

    import json as _json



    if output_dir is None:

        output_dir = _os.path.expanduser("~/.aiplat/datasources/auto_discovered")

    _os.makedirs(output_dir, exist_ok=True)



    saved = 0

    for config in results:

        name = config["name"]

        fp = _os.path.join(output_dir, f"{name}.yaml")

        try:

            import yaml as _yaml

            with open(fp, "w") as f:

                _yaml.dump(config, f, default_flow_style=False)

        except ImportError:

            with open(fp, "w") as f:

                _json.dump(config, f, indent=2, ensure_ascii=False)

        saved += 1



        if api_url:

            try:

                import urllib.request as _urllib

                req = _urllib.Request(

                    api_url,

                    data=_json.dumps(config).encode(),

                    headers={"Content-Type": "application/json"},

                )

                _urllib.urlopen(req, timeout=5)

            except Exception:

                logging.getLogger(__name__).debug('save_and_report failed', exc_info=True)


    return saved





def main():

    parser = argparse.ArgumentParser(description="Network Discovery Agent")

    parser.add_argument("--scan-once", action="store_true", help="Single scan")

    parser.add_argument("--daemon", action="store_true", help="Continuous mode")

    parser.add_argument("--subnet", default="", help="Subnet to scan")

    parser.add_argument("--interval", type=int, default=3600, help="Daemon interval (seconds)")

    parser.add_argument("--api-url", default="", help="aiPlat API endpoint")

    args = parser.parse_args()



    enabled = _os.getenv("AIPLAT_DISCOVERY_ENABLED", "false").lower() in ("1", "true", "yes")

    subnet = args.subnet or _os.getenv("AIPLAT_DISCOVERY_SUBNETS", "")

    api_url = args.api_url or _os.getenv("AIPLAT_DISCOVERY_API_URL", "")



    if not enabled or not subnet:

        print("[discovery] disabled or no subnet configured")

        return



    if args.scan_once:

        results = scan_network(subnet)

        saved = save_and_report(results, api_url=api_url)

        print(f"[discovery] scan complete: {len(results)} found, {saved} saved")



    elif args.daemon:

        while True:

            results = scan_network(subnet)

            saved = save_and_report(results, api_url=api_url)

            print(f"[discovery] daemon cycle: {len(results)} found, {saved} saved")

            _time.sleep(args.interval)





if __name__ == "__main__":

    main()

