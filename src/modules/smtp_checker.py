thonimport logging
import smtplib
import socket
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def _get_mx_hosts_via_dnspython(domain: str, timeout: int) -> List[str]:
    try:
        import dns.resolver  # type: ignore

        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        answers = resolver.resolve(domain, "MX")
        hosts: List[str] = []
        for rdata in answers:
            host = str(rdata.exchange).rstrip(".")
            hosts.append(host)
        return hosts
    except Exception as exc:  # noqa: BLE001
        logger.debug("Failed to resolve MX hosts via dnspython for %s: %s", domain, exc)
        return []

def _guess_mx_host_from_domain(domain: str) -> List[str]:
    # Simple heuristic: try common prefixes
    return [f"mail.{domain}", f"mx.{domain}", domain]

def _probe_smtp_host(host: str, timeout: int) -> Dict:
    try:
        logger.debug("Probing SMTP server %s", host)
        with smtplib.SMTP(host=host, port=25, timeout=timeout) as server:
            code, msg = server.noop()
            if 200 <= code < 400:
                return {
                    "status": "ok",
                    "message": f"SMTP server {host} responded with code {code}.",
                }
            return {
                "status": "unreachable",
                "message": f"SMTP server {host} responded with code {code}.",
            }
    except (socket.timeout, smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError) as exc:
        logger.debug("SMTP timeout/disconnect from %s: %s", host, exc)
        return {
            "status": "unreachable",
            "message": f"SMTP server {host} is unreachable or disconnected.",
        }
    except Exception as exc:  # noqa: BLE001
        logger.debug("Unexpected SMTP error for %s: %s", host, exc)
        return {
            "status": "unknown",
            "message": f"Unexpected SMTP error while connecting to {host}: {exc}",
        }

def check_smtp_server(domain: str, timeout: int = 8) -> Dict:
    """
    Check whether the domain appears to accept SMTP connections.
    This is a lightweight probe and does *not* send any emails or
    verify specific mailboxes.
    """
    domain = domain.strip().lower()
    if not domain:
        return {
            "status": "unknown",
            "message": "Domain is empty; cannot perform SMTP check.",
        }

    logger.debug("Checking SMTP server for domain %s", domain)

    # Prefer MX records from dnspython, fall back to heuristic hosts
    hosts: List[str] = _get_mx_hosts_via_dnspython(domain, timeout)
    if not hosts:
        hosts = _guess_mx_host_from_domain(domain)

    for host in hosts:
        result = _probe_smtp_host(host, timeout)
        if result["status"] in ("ok", "unreachable"):
            # Conclusive enough
            logger.debug("SMTP probe for %s (%s) result: %s", domain, host, result)
            return result

    # If all attempts resulted in "unknown", reflect that
    return {
        "status": "unknown",
        "message": f"Unable to determine SMTP status for domain {domain}.",
    }