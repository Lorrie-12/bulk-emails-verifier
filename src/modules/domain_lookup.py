thonimport logging
import socket
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

def _resolve_with_dnspython(domain: str, timeout: int) -> Dict:
    """
    Try to resolve MX records using dnspython if available.
    """
    try:
        import dns.resolver  # type: ignore

        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        answers = resolver.resolve(domain, "MX")
        mx_records: List[str] = []
        for rdata in answers:
            # rdata.exchange is a DNS name object; convert to string without trailing dot
            host = str(rdata.exchange).rstrip(".")
            mx_records.append(host)
        return {
            "status": "ok" if mx_records else "invalid",
            "message": "MX records found." if mx_records else "No MX records found.",
            "mx_records": mx_records,
            "method": "dnspython",
        }
    except ImportError:
        logger.debug("dnspython is not installed; falling back to socket DNS lookup.")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("MX lookup failed for %s via dnspython: %s", domain, exc)
        return {
            "status": "invalid",
            "message": f"MX lookup failed: {exc}",
            "mx_records": [],
            "method": "dnspython",
        }

def _resolve_with_socket(domain: str, timeout: int) -> Dict:
    """
    Fallback DNS resolution using the standard library.
    This only checks that the domain has at least one A/AAAA record.
    """
    try:
        socket.setdefaulttimeout(timeout)
        socket.getaddrinfo(domain, None)
        return {
            "status": "ok",
            "message": "Domain resolves via A/AAAA records.",
            "mx_records": [],
            "method": "socket",
        }
    except socket.gaierror as exc:
        logger.warning("DNS resolution failed for %s: %s", domain, exc)
        return {
            "status": "invalid",
            "message": f"Domain does not resolve: {exc}",
            "mx_records": [],
            "method": "socket",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unexpected error during DNS lookup for %s: %s", domain, exc)
        return {
            "status": "invalid",
            "message": f"Unexpected DNS error: {exc}",
            "mx_records": [],
            "method": "socket",
        }

def lookup_domain(domain: str, timeout: int = 5) -> Dict:
    """
    Perform a domain health lookup, preferring MX records when possible.
    Returns a dict with:
      - status: "ok" or "invalid"
      - message: human-readable description
      - mx_records: list of MX hosts (may be empty)
      - method: which method was used ("dnspython" or "socket")
    """
    domain = domain.strip().lower()
    logger.debug("Looking up domain %s with timeout=%s", domain, timeout)

    if not domain:
        return {
            "status": "invalid",
            "message": "Domain name is empty.",
            "mx_records": [],
            "method": "none",
        }

    # First try dnspython MX lookup
    try:
        return _resolve_with_dnspython(domain, timeout)
    except ImportError:
        # Fallback to basic DNS resolution
        return _resolve_with_socket(domain, timeout)